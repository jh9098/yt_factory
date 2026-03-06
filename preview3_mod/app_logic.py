from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from .data import DEFAULT_PROMPTS, NODES, Node, TOKEN_PATTERN
from .resolver import TokenResolver


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _node_to_dict(node: Node) -> Dict[str, Any]:
    return {
        "key": node.key,
        "name": node.name,
        "depends_on": list(node.depends_on),
        "state_key": node.state_key,
        "prompt_key": node.prompt_key,
    }


def _dict_to_node(raw: Dict[str, Any]) -> Node:
    return Node(
        key=str(raw.get("key", "")).strip(),
        name=str(raw.get("name", "")).strip(),
        depends_on=list(raw.get("depends_on", [])),
        state_key=raw.get("state_key"),
        prompt_key=raw.get("prompt_key"),
    )


class PreviewFlowApp:
    def __init__(self, session_path: Path, output_path: Path):
        self.session_path = session_path
        self.output_path = output_path
        self.state: Dict[str, Any] = self._create_default_state()
        self.token_resolver = TokenResolver(self.get_node_map())

    def _create_default_project(self, name: str = "기본 프로젝트") -> Dict[str, Any]:
        return {
            "name": name,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "nodes": [_node_to_dict(node) for node in NODES],
            "prompts": deepcopy(DEFAULT_PROMPTS),
            "data": {},
            "completed_nodes": [],
            "node_sets": {},
            "prompt_sets": {},
        }

    def _create_default_state(self) -> Dict[str, Any]:
        project_id = "project_default"
        return {
            "meta": {"created_at": _now_iso(), "updated_at": _now_iso()},
            "active_project_id": project_id,
            "projects": {
                project_id: self._create_default_project(),
            },
        }

    def _migrate_legacy_state(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        if "projects" in raw and "active_project_id" in raw:
            return raw

        state = self._create_default_state()
        project = state["projects"][state["active_project_id"]]
        project["prompts"] = raw.get("prompts", deepcopy(DEFAULT_PROMPTS))
        for k, v in DEFAULT_PROMPTS.items():
            project["prompts"].setdefault(k, v)

        project["data"] = raw.get("data", {})
        project["completed_nodes"] = raw.get("completed_nodes", [])
        project["nodes"] = [_node_to_dict(node) for node in NODES]
        return state

    # ---------- persistence ----------
    def load(self) -> None:
        if not self.session_path.exists():
            return
        raw = json.loads(self.session_path.read_text(encoding="utf-8"))
        self.state = self._migrate_legacy_state(raw)
        self._ensure_state_integrity()

    def _ensure_state_integrity(self) -> None:
        self.state.setdefault("meta", {})
        self.state.setdefault("projects", {})
        if not self.state["projects"]:
            default = self._create_default_state()
            self.state["projects"] = default["projects"]
            self.state["active_project_id"] = default["active_project_id"]

        active_id = self.state.get("active_project_id")
        if active_id not in self.state["projects"]:
            self.state["active_project_id"] = next(iter(self.state["projects"].keys()))

        for project in self.state["projects"].values():
            project.setdefault("name", "프로젝트")
            project.setdefault("created_at", _now_iso())
            project.setdefault("updated_at", _now_iso())
            project.setdefault("nodes", [_node_to_dict(node) for node in NODES])
            project.setdefault("prompts", deepcopy(DEFAULT_PROMPTS))
            for k, v in DEFAULT_PROMPTS.items():
                project["prompts"].setdefault(k, v)
            project.setdefault("data", {})
            project.setdefault("completed_nodes", [])
            project.setdefault("node_sets", {})
            project.setdefault("prompt_sets", {})
        self.token_resolver = TokenResolver(self.get_node_map())

    def save(self) -> None:
        self.state["meta"]["updated_at"] = _now_iso()
        self.current_project["updated_at"] = _now_iso()
        self.session_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- project ----------
    @property
    def current_project_id(self) -> str:
        return self.state["active_project_id"]

    @property
    def current_project(self) -> Dict[str, Any]:
        return self.state["projects"][self.current_project_id]

    def list_projects(self) -> List[Tuple[str, str]]:
        return [(pid, p["name"]) for pid, p in self.state["projects"].items()]

    def create_project(self, name: str) -> str:
        new_id = f"project_{uuid4().hex[:8]}"
        self.state["projects"][new_id] = self._create_default_project(name=name)
        self.state["active_project_id"] = new_id
        self.token_resolver = TokenResolver(self.get_node_map())
        self.save()
        return new_id

    def switch_project(self, project_id: str) -> None:
        if project_id not in self.state["projects"]:
            raise KeyError("존재하지 않는 프로젝트입니다.")
        self.state["active_project_id"] = project_id
        self.token_resolver = TokenResolver(self.get_node_map())

    def rename_current_project(self, new_name: str) -> None:
        self.current_project["name"] = new_name.strip()
        self.save()

    def delete_project(self, project_id: str) -> None:
        if project_id not in self.state["projects"]:
            return
        if len(self.state["projects"]) == 1:
            raise ValueError("마지막 프로젝트는 삭제할 수 없습니다.")
        del self.state["projects"][project_id]
        if self.state["active_project_id"] == project_id:
            self.state["active_project_id"] = next(iter(self.state["projects"].keys()))
        self.token_resolver = TokenResolver(self.get_node_map())
        self.save()

    # ---------- node ----------
    def get_nodes(self) -> List[Node]:
        return [_dict_to_node(raw) for raw in self.current_project.get("nodes", [])]

    def get_node_map(self) -> Dict[str, Node]:
        return {node.key: node for node in self.get_nodes() if node.key}

    def get_node(self, node_key: str) -> Optional[Node]:
        return self.get_node_map().get(node_key)

    def add_node(self, node: Node) -> None:
        if not node.key:
            raise ValueError("노드 key는 필수입니다.")
        node_map = self.get_node_map()
        if node.key in node_map:
            raise ValueError(f"이미 존재하는 key입니다: {node.key}")
        self.current_project["nodes"].append(_node_to_dict(node))
        if node.prompt_key:
            self.current_project["prompts"].setdefault(node.prompt_key, "")
        self.token_resolver = TokenResolver(self.get_node_map())
        self.save()

    def delete_node(self, node_key: str) -> None:
        project = self.current_project
        project["nodes"] = [n for n in project["nodes"] if n.get("key") != node_key]
        project["completed_nodes"] = [k for k in project.get("completed_nodes", []) if k != node_key]
        project.get("data", {}).pop(node_key, None)
        for raw in project["nodes"]:
            deps = list(raw.get("depends_on", []))
            raw["depends_on"] = [dep for dep in deps if dep != node_key]
        self.token_resolver = TokenResolver(self.get_node_map())
        self.save()

    # ---------- node/prompt set ----------
    def save_node_set(self, name: str) -> None:
        self.current_project["node_sets"][name] = {
            "name": name,
            "saved_at": _now_iso(),
            "nodes": deepcopy(self.current_project["nodes"]),
        }
        self.save()

    def load_node_set(self, name: str) -> None:
        node_set = self.current_project["node_sets"].get(name)
        if not node_set:
            raise KeyError("노드셋이 없습니다.")
        self.current_project["nodes"] = deepcopy(node_set["nodes"])
        self.current_project["completed_nodes"] = [
            k for k in self.current_project["completed_nodes"] if k in self.get_node_map()
        ]
        data = self.current_project["data"]
        for key in list(data.keys()):
            if key not in self.get_node_map():
                data.pop(key, None)
        self.token_resolver = TokenResolver(self.get_node_map())
        self.save()

    def delete_node_set(self, name: str) -> None:
        self.current_project["node_sets"].pop(name, None)
        self.save()

    def list_node_sets(self) -> List[str]:
        return sorted(self.current_project.get("node_sets", {}).keys())

    def save_prompt_set(self, name: str) -> None:
        self.current_project["prompt_sets"][name] = {
            "name": name,
            "saved_at": _now_iso(),
            "prompts": deepcopy(self.current_project["prompts"]),
        }
        self.save()

    def load_prompt_set(self, name: str) -> None:
        prompt_set = self.current_project["prompt_sets"].get(name)
        if not prompt_set:
            raise KeyError("프롬프트셋이 없습니다.")
        self.current_project["prompts"] = deepcopy(prompt_set["prompts"])
        for k, v in DEFAULT_PROMPTS.items():
            self.current_project["prompts"].setdefault(k, v)
        self.save()

    def delete_prompt_set(self, name: str) -> None:
        self.current_project["prompt_sets"].pop(name, None)
        self.save()

    def list_prompt_sets(self) -> List[str]:
        return sorted(self.current_project.get("prompt_sets", {}).keys())

    # ---------- session ----------
    def reset_session(self) -> None:
        project = self.current_project
        project["data"] = {}
        project["completed_nodes"] = []
        project["prompts"] = deepcopy(DEFAULT_PROMPTS)
        self.save()
        if self.output_path.exists():
            self.output_path.unlink()

    # ---------- node status ----------
    def is_completed(self, node_key: str) -> bool:
        return node_key in self.current_project["completed_nodes"]

    def mark_completed(self, node_key: str) -> None:
        if node_key not in self.current_project["completed_nodes"]:
            self.current_project["completed_nodes"].append(node_key)

    def unmark_completed(self, node_key: str) -> None:
        if node_key in self.current_project["completed_nodes"]:
            self.current_project["completed_nodes"].remove(node_key)

    def can_run(self, node: Node) -> bool:
        return all(self.is_completed(dep) for dep in node.depends_on)

    def get_previous_nodes(self, current_node_key: str) -> List[Node]:
        result: List[Node] = []
        for node in self.get_nodes():
            if node.key == current_node_key:
                break
            result.append(node)
        return result

    # ---------- helpers ----------
    @staticmethod
    def _to_pretty_json_or_text(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)

    @staticmethod
    def _safe_parse_json(raw: str) -> Any:
        raw = raw.strip()
        if not raw:
            return ""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def _get_node_value(self, node_key: str) -> Any:
        return self.current_project["data"].get(node_key, None)

    def get_prompt(self, key: str) -> str:
        return self.current_project["prompts"].get(key, "")

    def set_prompt(self, key: str, value: str) -> None:
        self.current_project["prompts"][key] = value

    def get_prompt_keys(self) -> List[str]:
        keys = set(self.current_project["prompts"].keys())
        for node in self.get_nodes():
            if node.prompt_key:
                keys.add(node.prompt_key)
        return sorted(keys)

    def extract_tokens(self, template: str) -> List[str]:
        raw_tokens = TOKEN_PATTERN.findall(template)
        result: List[str] = []
        seen = set()
        for token in raw_tokens:
            normalized = token.strip()
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result

    def validate_template_tokens(
        self,
        current_node_key: str,
        template_text: str,
        require_completed: bool = True,
        require_value: bool = True,
    ) -> Tuple[bool, str]:
        tokens = self.extract_tokens(template_text)
        if not tokens:
            return True, ""

        for token_expr in tokens:
            ok, msg = self.token_resolver.validate_token(
                token_expr=token_expr,
                current_node_key=current_node_key,
                app=self,
                require_completed=require_completed,
                require_value=require_value,
            )
            if not ok:
                return False, msg
        return True, ""

    def render_prompt(self, node: Node, template_override: Optional[str] = None) -> str:
        if not node.prompt_key:
            return ""
        template = template_override if template_override is not None else self.get_prompt(node.prompt_key)

        def replace_token(match: re.Match[str]) -> str:
            token_expr = match.group(1).strip()
            value = self.token_resolver.resolve_token(token_expr, self.current_project.get("data", {}))
            return self.token_resolver.stringify_value(value)

        return TOKEN_PATTERN.sub(replace_token, template)

    def save_output_file_if_ffmpeg(self) -> None:
        if "ffmpeg_json" not in self.current_project["data"]:
            return
        self.output_path.write_text(
            json.dumps(self.current_project["data"]["ffmpeg_json"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
