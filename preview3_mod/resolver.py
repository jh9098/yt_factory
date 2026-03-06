from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from .data import TokenMeta

class TokenResolver:
    def __init__(self, node_map: Dict[str, Node]):
        self.node_map = node_map

    @staticmethod
    def stringify_value(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        if value is None:
            return ""
        return str(value)

    def parse_token(self, token_expr: str) -> Tuple[bool, Dict[str, Any], str]:
        expr = token_expr.strip()
        if not expr:
            return False, {}, "빈 토큰입니다."

        first_part_match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)", expr)
        if not first_part_match:
            return False, {}, f"잘못된 토큰 문법입니다: {expr}"

        node_key = first_part_match.group(1)
        if node_key not in self.node_map:
            return False, {}, f"존재하지 않는 노드입니다: {node_key}"

        rest = expr[len(node_key):]
        path: List[Any] = []

        while rest:
            if rest.startswith("."):
                rest = rest[1:]
                seg_match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)", rest)
                if not seg_match:
                    return False, {}, f"잘못된 필드 경로입니다: {expr}"
                field_name = seg_match.group(1)
                path.append(field_name)
                rest = rest[len(field_name):]

                while rest.startswith("["):
                    idx_match = re.match(r"^\[([0-9]+)\]", rest)
                    if not idx_match:
                        return False, {}, f"잘못된 배열 인덱스 문법입니다: {expr}"
                    path.append(int(idx_match.group(1)))
                    rest = rest[len(idx_match.group(0)):]
            elif rest.startswith("["):
                idx_match = re.match(r"^\[([0-9]+)\]", rest)
                if not idx_match:
                    return False, {}, f"잘못된 배열 인덱스 문법입니다: {expr}"
                path.append(int(idx_match.group(1)))
                rest = rest[len(idx_match.group(0)):]
            else:
                return False, {}, f"잘못된 토큰 문법입니다: {expr}"

        return True, {"node_key": node_key, "path": path, "expr": expr}, ""

    def get_value_by_path(self, root_value: Any, path: List[Any], token_expr_for_error: str) -> Any:
        current = root_value
        current_path = ""

        for step in path:
            if isinstance(step, str):
                current_path = f"{current_path}.{step}" if current_path else step
                if not isinstance(current, dict):
                    raise KeyError(f"dict가 아닌 값에서 필드를 참조했습니다: {token_expr_for_error}")
                if step not in current:
                    raise KeyError(f"존재하지 않는 필드입니다: {token_expr_for_error}")
                current = current[step]
            elif isinstance(step, int):
                current_path = f"{current_path}[{step}]"
                if not isinstance(current, list):
                    raise KeyError(f"list가 아닌 값에서 인덱스를 참조했습니다: {token_expr_for_error}")
                if step < 0 or step >= len(current):
                    raise IndexError(f"배열 인덱스가 유효하지 않습니다: {token_expr_for_error}")
                current = current[step]
            else:
                raise KeyError(f"지원하지 않는 경로 타입입니다: {token_expr_for_error}")

        return current

    def resolve_token(self, token_expr: str, state_data: Dict[str, Any]) -> Any:
        ok, parsed, msg = self.parse_token(token_expr)
        if not ok:
            raise ValueError(msg)

        node_key = parsed["node_key"]
        path = parsed["path"]

        if node_key not in state_data:
            raise KeyError(f"참조한 노드 결과가 없습니다: {node_key}")

        root_value = state_data[node_key]
        return self.get_value_by_path(root_value, path, token_expr)

    def validate_token(
        self,
        token_expr: str,
        current_node_key: str,
        app: "PreviewFlowApp",
        require_completed: bool = True,
        require_value: bool = True,
    ) -> Tuple[bool, str]:
        ok, parsed, msg = self.parse_token(token_expr)
        if not ok:
            return False, msg

        node_key = parsed["node_key"]
        allowed_prev = {node.key for node in app.get_previous_nodes(current_node_key)}

        if node_key not in allowed_prev:
            return False, f"{current_node_key} 노드에서는 이전 노드만 참조할 수 있습니다: {token_expr}"

        if require_completed and not app.is_completed(node_key):
            return False, f"완료되지 않은 노드를 참조하고 있습니다: {node_key}"

        if require_value:
            value = app._get_node_value(node_key)
            if value is None or value == "":
                return False, f"참조한 노드의 결과가 비어 있습니다: {node_key}"

        try:
            if require_value:
                self.resolve_token(token_expr, app.current_project.get("data", {}))
            else:
                root_value = app._get_node_value(node_key)
                if root_value not in (None, ""):
                    self.get_value_by_path(root_value, parsed["path"], token_expr)
        except Exception as exc:
            return False, str(exc)

        return True, ""

class NodeFieldExplorer:
    def __init__(self, max_depth: int = 4, include_list_sample: bool = True):
        self.max_depth = max_depth
        self.include_list_sample = include_list_sample

    def build_tokens_for_node(self, node_key: str, node_value: Any) -> List[TokenMeta]:
        tokens: List[TokenMeta] = []

        tokens.append(
            TokenMeta(
                token=f"{{{{{node_key}}}}}",
                display="전체",
                node_key=node_key,
                path=[],
                kind="node",
                depth=0,
                is_whole_node=True,
            )
        )

        self._explore_value(
            node_key=node_key,
            value=node_value,
            tokens=tokens,
            current_path=[],
            depth=1,
        )
        return tokens

    def _token_expr(self, node_key: str, path: List[Any]) -> str:
        expr = node_key
        for p in path:
            if isinstance(p, str):
                expr += f".{p}"
            else:
                expr += f"[{p}]"
        return f"{{{{{expr}}}}}"

    def _display_name(self, path: List[Any], is_whole_node: bool = False) -> str:
        if is_whole_node:
            return "전체"
        if not path:
            return "전체"

        expr = ""
        for i, p in enumerate(path):
            if isinstance(p, str):
                if i == 0:
                    expr += p
                else:
                    expr += f".{p}"
            else:
                expr += f"[{p}]"
        return expr

    def _append_token(
        self,
        tokens: List[TokenMeta],
        node_key: str,
        path: List[Any],
        kind: str,
        depth: int,
    ) -> None:
        tokens.append(
            TokenMeta(
                token=self._token_expr(node_key, path),
                display=self._display_name(path),
                node_key=node_key,
                path=path[:],
                kind=kind,
                depth=depth,
                is_whole_node=False,
            )
        )

    def _explore_value(
        self,
        node_key: str,
        value: Any,
        tokens: List[TokenMeta],
        current_path: List[Any],
        depth: int,
    ) -> None:
        if depth > self.max_depth:
            return

        if isinstance(value, dict):
            for key, sub_value in value.items():
                new_path = current_path + [key]
                self._append_token(tokens, node_key, new_path, "field", depth)
                self._explore_value(node_key, sub_value, tokens, new_path, depth + 1)

        elif isinstance(value, list):
            self._append_token(tokens, node_key, current_path, "list", depth - 1 if depth > 0 else 0)

            if self.include_list_sample and value:
                sample_index = 0
                sample_path = current_path + [sample_index]
                self._append_token(tokens, node_key, sample_path, "list_item", depth)
                self._explore_value(node_key, value[sample_index], tokens, sample_path, depth + 1)
