from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import tkinter as tk
from tkinter import ttk

from .data import GroupState, TokenMeta
from .resolver import NodeFieldExplorer

class DragManager:
    def __init__(self, root: tk.Misc):
        self.root = root
        self.dragging = False
        self.drag_token: Optional[str] = None
        self.drag_source_widget: Optional[tk.Widget] = None
        self.ghost: Optional[tk.Toplevel] = None
        self.start_x_root = 0
        self.start_y_root = 0
        self.threshold = 6
        self.drop_targets: List[tk.Text] = []
        self.default_insert_callback: Optional[Callable[[str], None]] = None

    def register_text_target(self, text_widget: tk.Text) -> None:
        if text_widget not in self.drop_targets:
            self.drop_targets.append(text_widget)

    def unregister_text_target(self, text_widget: tk.Text) -> None:
        if text_widget in self.drop_targets:
            self.drop_targets.remove(text_widget)

    def set_default_insert_callback(self, callback: Callable[[str], None]) -> None:
        self.default_insert_callback = callback

    def begin_candidate(self, widget: tk.Widget, token_value: str, event: tk.Event) -> None:
        self.dragging = False
        self.drag_token = token_value
        self.drag_source_widget = widget
        self.start_x_root = event.x_root
        self.start_y_root = event.y_root

    def on_motion(self, event: tk.Event) -> None:
        if not self.drag_token:
            return

        dx = abs(event.x_root - self.start_x_root)
        dy = abs(event.y_root - self.start_y_root)

        if not self.dragging and (dx >= self.threshold or dy >= self.threshold):
            self._start_drag_visual(event.x_root, event.y_root)

        if self.dragging:
            self._move_ghost(event.x_root, event.y_root)

    def on_release(self, event: tk.Event) -> bool:
        if not self.drag_token:
            self.cancel_drag()
            return False

        inserted = False
        if self.dragging:
            inserted = self._drop_at(event.x_root, event.y_root)

        self.cancel_drag()
        return inserted

    def _start_drag_visual(self, x_root: int, y_root: int) -> None:
        self.dragging = True
        if self.ghost is not None:
            try:
                self.ghost.destroy()
            except Exception:
                pass

        self.ghost = tk.Toplevel(self.root)
        self.ghost.overrideredirect(True)
        self.ghost.attributes("-topmost", True)
        try:
            self.ghost.attributes("-alpha", 0.92)
        except Exception:
            pass

        label = tk.Label(
            self.ghost,
            text=self.drag_token,
            bg="#2b2f36",
            fg="white",
            bd=1,
            relief="solid",
            padx=8,
            pady=4,
            font=("Malgun Gothic", 9, "bold"),
        )
        label.pack()
        self._move_ghost(x_root, y_root)

    def _move_ghost(self, x_root: int, y_root: int) -> None:
        if self.ghost is None:
            return
        self.ghost.geometry(f"+{x_root + 12}+{y_root + 12}")

    def _resolve_text_target(self, x_root: int, y_root: int) -> Optional[tk.Text]:
        widget = self.root.winfo_containing(x_root, y_root)
        while widget is not None:
            if isinstance(widget, tk.Text):
                return widget
            widget = widget.master
        return None

    def _drop_at(self, x_root: int, y_root: int) -> bool:
        text_widget = self._resolve_text_target(x_root, y_root)
        if text_widget is None:
            return False

        try:
            local_x = x_root - text_widget.winfo_rootx()
            local_y = y_root - text_widget.winfo_rooty()
            index = text_widget.index(f"@{local_x},{local_y}")
            text_widget.mark_set("insert", index)
            text_widget.insert(index, self.drag_token)
            text_widget.focus_set()
            return True
        except Exception:
            try:
                text_widget.insert("insert", self.drag_token)
                text_widget.focus_set()
                return True
            except Exception:
                if self.default_insert_callback is not None:
                    self.default_insert_callback(self.drag_token)
                    return True
        return False

    def cancel_drag(self) -> None:
        self.dragging = False
        self.drag_token = None
        self.drag_source_widget = None
        if self.ghost is not None:
            try:
                self.ghost.destroy()
            except Exception:
                pass
        self.ghost = None

class TokenChip(tk.Label):
    def __init__(
        self,
        master: tk.Misc,
        token_meta: TokenMeta,
        insert_callback: Callable[[str], None],
        drag_manager: Optional[DragManager] = None,
        **kwargs: Any,
    ):
        self.token_meta = token_meta
        self.insert_callback = insert_callback
        self.drag_manager = drag_manager

        bg = "#2f5bea" if token_meta.is_whole_node else "#e8edf6"
        fg = "white" if token_meta.is_whole_node else "#1f2937"
        active_bg = "#2447b9" if token_meta.is_whole_node else "#d6dfef"
        bd_color = "#1d4ed8" if token_meta.is_whole_node else "#b8c2d6"

        super().__init__(
            master,
            text=token_meta.display,
            bg=bg,
            fg=fg,
            bd=1,
            relief="solid",
            padx=10,
            pady=4,
            cursor="hand2",
            font=("Malgun Gothic", 9, "bold" if token_meta.is_whole_node else "normal"),
            **kwargs,
        )

        self.normal_bg = bg
        self.normal_fg = fg
        self.active_bg = active_bg
        self.border_color = bd_color
        self.configure(highlightthickness=0)

        self._pressed = False
        self._drag_inserted = False

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_enter(self, event=None) -> None:
        self.configure(bg=self.active_bg)

    def _on_leave(self, event=None) -> None:
        if not self._pressed:
            self.configure(bg=self.normal_bg)

    def _on_press(self, event: tk.Event) -> None:
        self._pressed = True
        self._drag_inserted = False
        self.configure(bg=self.active_bg)

        if self.drag_manager is not None:
            self.drag_manager.begin_candidate(self, self.token_meta.token, event)

    def _on_motion(self, event: tk.Event) -> None:
        if self.drag_manager is not None:
            self.drag_manager.on_motion(event)

    def _on_release(self, event: tk.Event) -> None:
        inserted_by_drag = False
        if self.drag_manager is not None:
            inserted_by_drag = self.drag_manager.on_release(event)

        if not inserted_by_drag:
            self.insert_callback(self.token_meta.token)

        self._pressed = False
        self.configure(bg=self.normal_bg)

class TokenPanel(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        app: "PreviewFlowApp",
        drag_manager: Optional[DragManager],
        insert_callback: Callable[[str], None],
        current_node_key_getter: Callable[[], str],
        title_text: str = "참조 패널",
    ):
        super().__init__(master)
        self.app = app
        self.drag_manager = drag_manager
        self.insert_callback = insert_callback
        self.current_node_key_getter = current_node_key_getter
        self.title_text = title_text
        self.group_states: Dict[str, GroupState] = {}

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self.inner_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    def destroy(self) -> None:
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        super().destroy()

    def _on_inner_configure(self, event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event=None) -> None:
        try:
            width = self.canvas.winfo_width()
            self.canvas.itemconfigure(self.inner_window, width=width)
        except Exception:
            pass

    def _on_mousewheel(self, event) -> None:
        if not self.winfo_exists():
            return
        try:
            widget_under_mouse = self.winfo_containing(event.x_root, event.y_root)
            if widget_under_mouse is None:
                return
            parent = widget_under_mouse
            inside_self = False
            while parent is not None:
                if parent == self:
                    inside_self = True
                    break
                parent = parent.master
            if not inside_self:
                return
        except Exception:
            return

        delta = -1 * int(event.delta / 120) if event.delta else 0
        if delta != 0:
            self.canvas.yview_scroll(delta, "units")

    def toggle_group(self, node_key: str) -> None:
        state = self.group_states.setdefault(node_key, GroupState(expanded=True))
        state.expanded = not state.expanded
        self.refresh()

    def refresh(self) -> None:
        for child in self.inner.winfo_children():
            child.destroy()

        current_node_key = self.current_node_key_getter()
        previous_nodes = self.app.get_previous_nodes(current_node_key)

        if not previous_nodes:
            ttk.Label(self.inner, text="이전 노드 없음").pack(anchor="w", padx=8, pady=8)
            return

        explorer = NodeFieldExplorer(max_depth=4, include_list_sample=True)

        for node in previous_nodes:
            group_frame = ttk.Frame(self.inner)
            group_frame.pack(fill="x", padx=6, pady=(6, 2))

            state = self.group_states.setdefault(node.key, GroupState(expanded=True))
            arrow = "▼" if state.expanded else "▶"

            header = tk.Frame(group_frame, bg="#f3f4f6", bd=1, relief="solid")
            header.pack(fill="x")

            header_label = tk.Label(
                header,
                text=f"{arrow} {node.key}",
                anchor="w",
                bg="#f3f4f6",
                fg="#111827",
                padx=8,
                pady=6,
                font=("Malgun Gothic", 10, "bold"),
                cursor="hand2",
            )
            header_label.pack(fill="x")

            header_label.bind("<Button-1>", lambda e, k=node.key: self.toggle_group(k))
            header.bind("<Button-1>", lambda e, k=node.key: self.toggle_group(k))

            if not state.expanded:
                continue

            body = ttk.Frame(group_frame)
            body.pack(fill="x", padx=4, pady=(4, 2))

            node_value = self.app._get_node_value(node.key)
            tokens = explorer.build_tokens_for_node(node.key, node_value)

            chip_wrap = tk.Frame(body, bg="white")
            chip_wrap.pack(fill="x", expand=True)

            self._pack_chip_wrap(chip_wrap, tokens)

    def _pack_chip_wrap(self, parent: tk.Frame, tokens: List[TokenMeta]) -> None:
        row = tk.Frame(parent, bg="white")
        row.pack(fill="x", anchor="w")

        parent.update_idletasks()
        max_width = max(parent.winfo_width(), 260)
        used_width = 0

        for token_meta in tokens:
            chip = TokenChip(
                row,
                token_meta=token_meta,
                insert_callback=self.insert_callback,
                drag_manager=self.drag_manager,
            )
            chip.update_idletasks()
            chip_w = max(chip.winfo_reqwidth(), 50) + 8

            if used_width + chip_w > max_width and used_width > 0:
                row = tk.Frame(parent, bg="white")
                row.pack(fill="x", anchor="w", pady=(4, 0))
                used_width = 0

            chip.pack(side="left", padx=4, pady=4, anchor="w")
            used_width += chip_w
