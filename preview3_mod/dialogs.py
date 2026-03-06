from __future__ import annotations

import json
import traceback
from typing import Any, Callable, Optional

import tkinter as tk
from tkinter import messagebox, ttk

from .data import NODE_MAP
from .resolver import NodeFieldExplorer, TokenResolver
from .ui_components import DragManager, TokenPanel

class PromptEditorDialog(tk.Toplevel):
    def __init__(self, master: "PreviewFlowGUI", app: PreviewFlowApp):
        super().__init__(master.root)
        self.master_gui = master
        self.app = app
        self.drag_manager = DragManager(self)

        self.title("프롬프트 템플릿 편집")
        self.geometry("1360x840")
        self.minsize(1180, 760)

        self.prompt_keys = [k for k in DEFAULT_PROMPTS.keys()]
        self.current_key = tk.StringVar(value=self.prompt_keys[0])

        self.current_node_key = self.current_key.get()
        self.text_widget: Optional[tk.Text] = None
        self.token_panel: Optional[TokenPanel] = None

        self._build_ui()
        self._load_current_prompt()

        self.transient(master.root)
        self.grab_set()
        self.focus()

    def destroy(self) -> None:
        try:
            if self.text_widget is not None:
                self.drag_manager.unregister_text_target(self.text_widget)
        except Exception:
            pass
        super().destroy()

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=10)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=4)
        container.columnconfigure(1, weight=2)
        container.rowconfigure(1, weight=1)

        top = ttk.Frame(container)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        ttk.Label(top, text="프롬프트 키").pack(side="left")

        combo = ttk.Combobox(
            top,
            values=self.prompt_keys,
            state="readonly",
            textvariable=self.current_key,
            width=36,
        )
        combo.pack(side="left", padx=(8, 0))
        combo.bind("<<ComboboxSelected>>", self._on_prompt_key_changed)

        ttk.Button(top, text="기본값 복원", command=self._restore_default).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="참조 검증", command=self._validate_current_template).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="저장", command=self._save_prompt).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="닫기", command=self.destroy).pack(side="right")

        editor_frame = ttk.Labelframe(container, text="프롬프트 템플릿")
        editor_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        editor_frame.rowconfigure(0, weight=1)
        editor_frame.columnconfigure(0, weight=1)

        self.text_widget = tk.Text(editor_frame, wrap="word", undo=True, font=("Consolas", 10))
        self.text_widget.grid(row=0, column=0, sticky="nsew")

        yscroll = ttk.Scrollbar(editor_frame, orient="vertical", command=self.text_widget.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.text_widget.configure(yscrollcommand=yscroll.set)

        self.drag_manager.register_text_target(self.text_widget)
        self.drag_manager.set_default_insert_callback(self._insert_token)

        right_frame = ttk.Labelframe(container, text="참조 칩 패널")
        right_frame.grid(row=1, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)

        info = ttk.Label(
            right_frame,
            text=(
                "칩 클릭 또는 드래그로 토큰을 삽입합니다.\n"
                "지원 형식:\n"
                "{{node_key}}, {{node_key.field}}, {{node_key.list[0].field}}"
            ),
            justify="left",
        )
        info.grid(row=0, column=0, sticky="w", padx=8, pady=8)

        self.token_panel = TokenPanel(
            right_frame,
            app=self.app,
            drag_manager=self.drag_manager,
            insert_callback=self._insert_token,
            current_node_key_getter=lambda: self.current_node_key,
        )
        self.token_panel.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

    def _on_prompt_key_changed(self, event=None) -> None:
        self.current_node_key = self.current_key.get()
        self._load_current_prompt()

    def _load_current_prompt(self) -> None:
        if self.text_widget is None:
            return

        key = self.current_key.get()
        self.current_node_key = key
        text = self.app.state["prompts"].get(key, "")

        self.text_widget.delete("1.0", "end")
        self.text_widget.insert("1.0", text)

        if self.token_panel is not None:
            self.token_panel.refresh()

    def _insert_token(self, token: str) -> None:
        if self.text_widget is None:
            return
        self.text_widget.insert("insert", token)
        self.text_widget.focus_set()

    def _validate_current_template(self) -> None:
        if self.text_widget is None:
            return

        raw = self.text_widget.get("1.0", "end-1c")
        ok, msg = self.app.validate_template_tokens(
            current_node_key=self.current_node_key,
            template_text=raw,
            require_completed=False,
            require_value=False,
        )
        if ok:
            messagebox.showinfo("검증 완료", "프롬프트 참조 형식이 올바릅니다.")
        else:
            messagebox.showerror("검증 실패", msg)

    def _save_prompt(self) -> None:
        if self.text_widget is None:
            return

        key = self.current_key.get()
        new_value = self.text_widget.get("1.0", "end-1c").strip()
        if not new_value:
            messagebox.showwarning("경고", "프롬프트가 비어 있습니다.")
            return

        ok, msg = self.app.validate_template_tokens(
            current_node_key=key,
            template_text=new_value,
            require_completed=False,
            require_value=False,
        )
        if not ok:
            messagebox.showerror("오류", msg)
            return

        self.app.state["prompts"][key] = new_value
        self.app.save()
        self.master_gui.log(f"[완료] 프롬프트 저장: {key}")
        messagebox.showinfo("완료", f"{key} 프롬프트를 저장했습니다.")

    def _restore_default(self) -> None:
        key = self.current_key.get()
        self.app.state["prompts"][key] = DEFAULT_PROMPTS[key]
        self.app.save()
        self._load_current_prompt()
        self.master_gui.log(f"[복원] 기본 프롬프트 복원: {key}")
        messagebox.showinfo("완료", f"{key} 프롬프트를 기본값으로 복원했습니다.")

class NodeDialog(tk.Toplevel):
    def __init__(self, master: "PreviewFlowGUI", app: PreviewFlowApp, node: Node):
        super().__init__(master.root)
        self.master_gui = master
        self.app = app
        self.node = node
        self.drag_manager = DragManager(self)

        self.title(node.name)
        self.geometry("1460x900")
        self.minsize(1260, 780)

        self.content_text: Optional[tk.Text] = None
        self.prompt_text: Optional[tk.Text] = None
        self.response_text: Optional[tk.Text] = None
        self.rendered_text: Optional[tk.Text] = None
        self.token_panel: Optional[TokenPanel] = None

        self._build_ui()
        self._load_initial_data()

        self.transient(master.root)
        self.grab_set()
        self.focus()

    def destroy(self) -> None:
        try:
            for widget in [self.prompt_text, self.response_text, self.rendered_text, self.content_text]:
                if isinstance(widget, tk.Text):
                    self.drag_manager.unregister_text_target(widget)
        except Exception:
            pass
        super().destroy()

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=10)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=4)
        container.columnconfigure(1, weight=2)
        container.rowconfigure(0, weight=1)

        if self.node.key == "content_input":
            self._build_content_input_ui(container)
        else:
            self._build_prompt_node_ui(container)

    def _build_content_input_ui(self, parent: ttk.Frame) -> None:
        frame = ttk.Labelframe(parent, text="내용입력")
        frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.content_text = tk.Text(frame, wrap="word", undo=True, font=("Consolas", 11))
        self.content_text.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        yscroll = ttk.Scrollbar(frame, orient="vertical", command=self.content_text.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.content_text.configure(yscrollcommand=yscroll.set)

        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        ttk.Button(btn_frame, text="저장", command=self._save_content_input).pack(side="left")
        ttk.Button(btn_frame, text="닫기", command=self.destroy).pack(side="right")

    def _build_prompt_node_ui(self, parent: ttk.Frame) -> None:
        left_paned = ttk.Panedwindow(parent, orient="vertical")
        left_paned.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        prompt_frame = ttk.Labelframe(left_paned, text="프롬프트 템플릿")
        prompt_frame.rowconfigure(0, weight=1)
        prompt_frame.columnconfigure(0, weight=1)

        self.prompt_text = tk.Text(prompt_frame, wrap="word", undo=True, font=("Consolas", 10))
        self.prompt_text.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        prompt_scroll = ttk.Scrollbar(prompt_frame, orient="vertical", command=self.prompt_text.yview)
        prompt_scroll.grid(row=0, column=1, sticky="ns")
        self.prompt_text.configure(yscrollcommand=prompt_scroll.set)

        rendered_frame = ttk.Labelframe(left_paned, text="실제 실행용 렌더링 결과")
        rendered_frame.rowconfigure(0, weight=1)
        rendered_frame.columnconfigure(0, weight=1)

        self.rendered_text = tk.Text(rendered_frame, wrap="word", undo=False, font=("Consolas", 10))
        self.rendered_text.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        rendered_scroll = ttk.Scrollbar(rendered_frame, orient="vertical", command=self.rendered_text.yview)
        rendered_scroll.grid(row=0, column=1, sticky="ns")
        self.rendered_text.configure(yscrollcommand=rendered_scroll.set)

        response_frame = ttk.Labelframe(left_paned, text="외부 LLM 응답 붙여넣기")
        response_frame.rowconfigure(0, weight=1)
        response_frame.columnconfigure(0, weight=1)

        self.response_text = tk.Text(response_frame, wrap="word", undo=True, font=("Consolas", 10))
        self.response_text.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        response_scroll = ttk.Scrollbar(response_frame, orient="vertical", command=self.response_text.yview)
        response_scroll.grid(row=0, column=1, sticky="ns")
        self.response_text.configure(yscrollcommand=response_scroll.set)

        left_paned.add(prompt_frame, weight=2)
        left_paned.add(rendered_frame, weight=2)
        left_paned.add(response_frame, weight=2)

        self.drag_manager.register_text_target(self.prompt_text)
        self.drag_manager.set_default_insert_callback(self._insert_token_to_prompt)

        right_frame = ttk.Labelframe(parent, text="참조 칩 패널")
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)

        top_info = ttk.Label(
            right_frame,
            text=(
                "칩 클릭 또는 드래그로 프롬프트에 삽입합니다.\n"
                "전체 노드 / 하위 필드 / 중첩 필드를 지원합니다."
            ),
            justify="left",
        )
        top_info.grid(row=0, column=0, sticky="w", padx=8, pady=8)

        self.token_panel = TokenPanel(
            right_frame,
            app=self.app,
            drag_manager=self.drag_manager,
            insert_callback=self._insert_token_to_prompt,
            current_node_key_getter=lambda: self.node.key,
        )
        self.token_panel.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        ttk.Button(btn_frame, text="프롬프트 갱신", command=self._reload_prompt_from_saved).pack(side="left")
        ttk.Button(btn_frame, text="토큰 검증", command=self._validate_prompt_tokens).pack(side="left", padx=(6, 0))
        ttk.Button(btn_frame, text="렌더링 미리보기", command=self._render_prompt_preview).pack(side="left", padx=(6, 0))
        ttk.Button(btn_frame, text="렌더링 결과 복사", command=self._copy_rendered_prompt).pack(side="left", padx=(6, 0))
        ttk.Button(btn_frame, text="응답 저장", command=self._save_prompt_response).pack(side="left", padx=(12, 0))

        if self.node.key == "ffmpeg_json":
            ttk.Button(btn_frame, text="출력 파일 저장", command=self._save_ffmpeg_output_file).pack(side="left", padx=(12, 0))

        ttk.Button(btn_frame, text="닫기", command=self.destroy).pack(side="right")

    def _insert_token_to_prompt(self, token: str) -> None:
        if self.prompt_text is None:
            return
        self.prompt_text.insert("insert", token)
        self.prompt_text.focus_set()

    def _load_initial_data(self) -> None:
        data = self.app.state["data"]

        if self.node.key == "content_input" and self.content_text is not None:
            existing = self.app._to_pretty_json_or_text(data.get("content_input", ""))
            self.content_text.delete("1.0", "end")
            self.content_text.insert("1.0", existing)
            return

        if self.prompt_text is not None and self.node.prompt_key:
            prompt = self.app.state["prompts"].get(self.node.prompt_key, "")
            self.prompt_text.delete("1.0", "end")
            self.prompt_text.insert("1.0", prompt)

        if self.response_text is not None and self.node.state_key:
            existing_result = data.get(self.node.state_key, "")
            pretty = self.app._to_pretty_json_or_text(existing_result)
            self.response_text.delete("1.0", "end")
            self.response_text.insert("1.0", pretty)

        if self.token_panel is not None:
            self.token_panel.refresh()

        self._render_prompt_preview()

    def _reload_prompt_from_saved(self) -> None:
        if self.prompt_text is None or not self.node.prompt_key:
            return

        prompt = self.app.state["prompts"].get(self.node.prompt_key, "")
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", prompt)
        self.master_gui.log(f"[프롬프트 갱신] {self.node.name}")
        self._render_prompt_preview()

    def _validate_prompt_tokens(self) -> bool:
        if self.prompt_text is None:
            return False

        raw_prompt = self.prompt_text.get("1.0", "end-1c")
        ok, msg = self.app.validate_template_tokens(
            current_node_key=self.node.key,
            template_text=raw_prompt,
            require_completed=True,
            require_value=True,
        )
        if not ok:
            messagebox.showerror("오류", msg)
            return False

        messagebox.showinfo("검증 완료", "참조한 상위 노드 상태와 필드 경로가 모두 정상입니다.")
        return True

    def _render_prompt_preview(self) -> None:
        if self.prompt_text is None or self.rendered_text is None:
            return

        raw_prompt = self.prompt_text.get("1.0", "end-1c")
        ok, msg = self.app.validate_template_tokens(
            current_node_key=self.node.key,
            template_text=raw_prompt,
            require_completed=True,
            require_value=True,
        )

        self.rendered_text.delete("1.0", "end")

        if not ok:
            self.rendered_text.insert("1.0", f"[렌더링 불가]\n{msg}")
            return

        try:
            rendered = self.app.render_prompt(self.node, template_override=raw_prompt)
        except Exception as exc:
            self.rendered_text.insert("1.0", f"[렌더링 불가]\n{exc}")
            return

        self.rendered_text.insert("1.0", rendered)

    def _copy_rendered_prompt(self) -> None:
        if self.rendered_text is None:
            return

        raw_prompt = self.prompt_text.get("1.0", "end-1c") if self.prompt_text else ""
        ok, msg = self.app.validate_template_tokens(
            current_node_key=self.node.key,
            template_text=raw_prompt,
            require_completed=True,
            require_value=True,
        )
        if not ok:
            messagebox.showerror("오류", msg)
            return

        text = self.rendered_text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.master_gui.log(f"[복사] 렌더링 프롬프트: {self.node.name}")
        messagebox.showinfo("완료", "렌더링 결과를 클립보드에 복사했습니다.")

    def _save_content_input(self) -> None:
        if self.content_text is None:
            return

        content = self.content_text.get("1.0", "end-1c").strip()
        if not content:
            messagebox.showwarning("경고", "내용입력이 비어 있습니다.")
            return

        self.app.state["data"]["content_input"] = content
        self.app.mark_completed("content_input")
        self.app.save()

        self.master_gui.refresh_all()
        self.master_gui.log("[완료] 내용입력 저장")
        messagebox.showinfo("완료", "내용입력을 저장했습니다.")

    def _save_prompt_response(self) -> None:
        if self.prompt_text is None or self.response_text is None or self.node.state_key is None:
            return

        raw_prompt = self.prompt_text.get("1.0", "end-1c")
        ok, msg = self.app.validate_template_tokens(
            current_node_key=self.node.key,
            template_text=raw_prompt,
            require_completed=True,
            require_value=True,
        )
        if not ok:
            messagebox.showerror("오류", msg)
            return

        raw_response = self.response_text.get("1.0", "end-1c").strip()
        if not raw_response:
            messagebox.showwarning("경고", "응답 내용이 비어 있습니다.")
            return

        parsed = self.app._safe_parse_json(raw_response)

        self.app.state["data"][self.node.state_key] = parsed
        self.app.mark_completed(self.node.key)
        self.app.save()

        if self.node.key == "ffmpeg_json":
            try:
                self.app.save_output_file_if_ffmpeg()
            except Exception:
                pass

        if self.token_panel is not None:
            self.token_panel.refresh()

        self.master_gui.refresh_all()
        self.master_gui.log(f"[완료] 노드 결과 저장: {self.node.name}")
        messagebox.showinfo("완료", f"{self.node.name} 결과를 저장했습니다.")

    def _save_ffmpeg_output_file(self) -> None:
        if "ffmpeg_json" not in self.app.state["data"]:
            messagebox.showwarning("안내", "먼저 ffmpeg_json 노드 응답을 저장하세요.")
            return
        try:
            self.app.save_output_file_if_ffmpeg()
            self.master_gui.log(f"[저장] 출력 파일: {self.app.output_path}")
            messagebox.showinfo("완료", f"출력 파일로 저장했습니다.\n{self.app.output_path}")
        except Exception as exc:
            messagebox.showerror("오류", f"출력 파일 저장 실패:\n{exc}")
