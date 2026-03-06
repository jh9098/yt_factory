from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .data import DEFAULT_PROMPTS, NODES, NODE_MAP, OUTPUT_FILE, SESSION_FILE, TOKEN_PATTERN
from .resolver import TokenResolver

class PreviewFlowApp:
    def __init__(self, session_path: Path, output_path: Path):
        self.session_path = session_path
        self.output_path = output_path
        self.token_resolver = TokenResolver(NODE_MAP)

        self.state: Dict[str, Any] = {
            "meta": {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
            "prompts": DEFAULT_PROMPTS.copy(),
            "data": {},
            "completed_nodes": [],
        }

    # ---------- persistence ----------
    def load(self) -> None:
        if not self.session_path.exists():
            return

        raw = json.loads(self.session_path.read_text(encoding="utf-8"))
        self.state.update(raw)

        if "prompts" not in self.state:
            self.state["prompts"] = DEFAULT_PROMPTS.copy()

        for k, v in DEFAULT_PROMPTS.items():
            self.state["prompts"].setdefault(k, v)

        self.state.setdefault("data", {})
        self.state.setdefault("completed_nodes", [])
        self.state.setdefault("meta", {})

    def save(self) -> None:
        self.state["meta"]["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.session_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def reset_session(self) -> None:
        self.state = {
            "meta": {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
            "prompts": DEFAULT_PROMPTS.copy(),
            "data": {},
            "completed_nodes": [],
        }
        self.save()
        if self.output_path.exists():
            self.output_path.unlink()

    # ---------- node status ----------
    def is_completed(self, node_key: str) -> bool:
        return node_key in self.state["completed_nodes"]

    def mark_completed(self, node_key: str) -> None:
        if node_key not in self.state["completed_nodes"]:
            self.state["completed_nodes"].append(node_key)

    def unmark_completed(self, node_key: str) -> None:
        if node_key in self.state["completed_nodes"]:
            self.state["completed_nodes"].remove(node_key)

    def can_run(self, node: Node) -> bool:
        return all(self.is_completed(dep) for dep in node.depends_on)

    def get_previous_nodes(self, current_node_key: str) -> List[Node]:
        result = []
        for node in NODES:
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
        return self.state["data"].get(node_key, None)

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

        template = template_override if template_override is not None else self.state["prompts"][node.prompt_key]

        def replace_token(match: re.Match) -> str:
            token_expr = match.group(1).strip()
            value = self.token_resolver.resolve_token(token_expr, self.state.get("data", {}))
            return self.token_resolver.stringify_value(value)

        return TOKEN_PATTERN.sub(replace_token, template)

    def save_output_file_if_ffmpeg(self) -> None:
        if "ffmpeg_json" not in self.state["data"]:
            return
        self.output_path.write_text(
            json.dumps(self.state["data"]["ffmpeg_json"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
