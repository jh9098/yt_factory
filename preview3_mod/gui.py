from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .dialogs import NodeDialog, PromptEditorDialog
from .ui_components import DragManager

class PreviewFlowGUI:
    def __init__(self, app: PreviewFlowApp):
        self.app = app
        self.root = tk.Tk()
        self.root.title("HiddenTube Preview Flow GUI v3")
        self.root.geometry("1520x960")
        self.root.minsize(1300, 840)

        self.session_var = tk.StringVar(value=str(self.app.session_path))
        self.output_var = tk.StringVar(value=str(self.app.output_path))

        self.tree: Optional[ttk.Treeview] = None
        self.data_text: Optional[tk.Text] = None
        self.log_text: Optional[tk.Text] = None
        self.summary_label: Optional[ttk.Label] = None
        self.search_tool_window: Optional[tk.Toplevel] = None

        self._build_ui()
        self.refresh_all()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        path_frame = ttk.Frame(self.root, padding=10)
        path_frame.grid(row=0, column=0, sticky="ew")
        path_frame.columnconfigure(1, weight=1)

        ttk.Label(path_frame, text="세션 파일").grid(row=0, column=0, sticky="w")
        ttk.Entry(path_frame, textvariable=self.session_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(path_frame, text="선택", command=self.select_session_file).grid(row=0, column=2)

        ttk.Label(path_frame, text="출력 파일").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(path_frame, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        ttk.Button(path_frame, text="선택", command=self.select_output_file).grid(row=1, column=2, pady=(6, 0))

        top_btn_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        top_btn_frame.grid(row=1, column=0, sticky="ew")

        ttk.Button(top_btn_frame, text="세션 불러오기", command=self.load_session).pack(side="left")
        ttk.Button(top_btn_frame, text="세션 저장", command=self.save_session).pack(side="left", padx=(6, 0))
        ttk.Button(top_btn_frame, text="프롬프트 템플릿 편집", command=self.open_prompt_editor).pack(side="left", padx=(12, 0))
        ttk.Button(top_btn_frame, text="다음 실행 노드 열기", command=self.open_next_runnable_node).pack(side="left", padx=(12, 0))
        ttk.Button(top_btn_frame, text="세션 초기화", command=self.reset_session).pack(side="left", padx=(12, 0))
        ttk.Button(top_btn_frame, text="새로고침", command=self.refresh_all).pack(side="left", padx=(6, 0))
        ttk.Button(top_btn_frame, text="YouTube 검색 도구", command=self.open_search_tool).pack(side="left", padx=(12, 0))

        main_paned = ttk.Panedwindow(self.root, orient="horizontal")
        main_paned.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

        left_frame = ttk.Frame(main_paned)
        right_paned = ttk.Panedwindow(main_paned, orient="vertical")

        main_paned.add(left_frame, weight=1)
        main_paned.add(right_paned, weight=2)

        left_frame.rowconfigure(1, weight=1)
        left_frame.columnconfigure(0, weight=1)

        self.summary_label = ttk.Label(left_frame, text="", font=("Malgun Gothic", 10, "bold"))
        self.summary_label.grid(row=0, column=0, sticky="w", pady=(0, 8))

        columns = ("status", "name", "runnable")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=18)
        self.tree.grid(row=1, column=0, sticky="nsew")

        self.tree.heading("status", text="상태")
        self.tree.heading("name", text="노드")
        self.tree.heading("runnable", text="실행가능")

        self.tree.column("status", width=80, anchor="center")
        self.tree.column("name", width=420, anchor="w")
        self.tree.column("runnable", width=90, anchor="center")

        tree_scroll = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        tree_scroll.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=tree_scroll.set)

        left_btn_frame = ttk.Frame(left_frame)
        left_btn_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        ttk.Button(left_btn_frame, text="선택 노드 열기", command=self.open_selected_node).pack(side="left")
        ttk.Button(left_btn_frame, text="선택 노드 완료해제", command=self.uncomplete_selected_node).pack(side="left", padx=(8, 0))
        ttk.Button(left_btn_frame, text="선택 노드 데이터삭제", command=self.clear_selected_node_data).pack(side="left", padx=(8, 0))

        self.tree.bind("<Double-1>", lambda e: self.open_selected_node())

        data_frame = ttk.Labelframe(right_paned, text="현재 데이터(JSON)")
        self.data_text = tk.Text(data_frame, wrap="none", undo=False, font=("Consolas", 10))
        self.data_text.pack(fill="both", expand=True)

        data_x = ttk.Scrollbar(data_frame, orient="horizontal", command=self.data_text.xview)
        data_y = ttk.Scrollbar(data_frame, orient="vertical", command=self.data_text.yview)
        self.data_text.configure(xscrollcommand=data_x.set, yscrollcommand=data_y.set)
        data_x.pack(fill="x", side="bottom")
        data_y.pack(fill="y", side="right")

        log_frame = ttk.Labelframe(right_paned, text="로그")
        self.log_text = tk.Text(log_frame, wrap="word", height=10, undo=False, font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True)

        right_paned.add(data_frame, weight=3)
        right_paned.add(log_frame, weight=1)

    # ---------- file path ----------
    def select_session_file(self) -> None:
        path = filedialog.asksaveasfilename(
            title="세션 파일 선택",
            defaultextension=".json",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")],
            initialfile=Path(self.session_var.get()).name,
        )
        if path:
            self.session_var.set(path)
            self.app.session_path = Path(path)
            self.log(f"[경로 변경] 세션 파일: {path}")

    def select_output_file(self) -> None:
        path = filedialog.asksaveasfilename(
            title="출력 파일 선택",
            defaultextension=".json",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")],
            initialfile=Path(self.output_var.get()).name,
        )
        if path:
            self.output_var.set(path)
            self.app.output_path = Path(path)
            self.log(f"[경로 변경] 출력 파일: {path}")

    # ---------- actions ----------
    def load_session(self) -> None:
        self.app.session_path = Path(self.session_var.get())
        self.app.output_path = Path(self.output_var.get())
        try:
            self.app.load()
            self.refresh_all()
            self.log("[완료] 세션 불러오기")
            messagebox.showinfo("완료", "세션을 불러왔습니다.")
        except Exception as exc:
            self.log(f"[오류] 세션 불러오기 실패: {exc}")
            messagebox.showerror("오류", f"세션 불러오기 실패:\n{exc}")

    def save_session(self) -> None:
        self.app.session_path = Path(self.session_var.get())
        self.app.output_path = Path(self.output_var.get())
        try:
            self.app.save()
            self.refresh_all()
            self.log("[완료] 세션 저장")
            messagebox.showinfo("완료", "세션을 저장했습니다.")
        except Exception as exc:
            self.log(f"[오류] 세션 저장 실패: {exc}")
            messagebox.showerror("오류", f"세션 저장 실패:\n{exc}")

    def reset_session(self) -> None:
        if not messagebox.askyesno("확인", "정말 세션을 초기화할까요?"):
            return
        try:
            self.app.reset_session()
            self.refresh_all()
            self.log("[완료] 세션 초기화")
            messagebox.showinfo("완료", "세션을 초기화했습니다.")
        except Exception as exc:
            self.log(f"[오류] 세션 초기화 실패: {exc}")
            messagebox.showerror("오류", f"세션 초기화 실패:\n{exc}")

    def open_prompt_editor(self) -> None:
        PromptEditorDialog(self, self.app)

    def get_selected_node(self) -> Optional[Node]:
        if self.tree is None:
            return None
        selected = self.tree.selection()
        if not selected:
            return None
        item_id = selected[0]
        tags = self.tree.item(item_id, "tags")
        if not tags:
            return None
        return NODE_MAP.get(tags[0])

    def open_selected_node(self) -> None:
        node = self.get_selected_node()
        if node is None:
            messagebox.showwarning("안내", "노드를 선택하세요.")
            return

        if not self.app.can_run(node) and not self.app.is_completed(node.key):
            deps = ", ".join(node.depends_on) if node.depends_on else "-"
            messagebox.showwarning("안내", f"선행 노드가 완료되지 않았습니다.\n필요: {deps}")
            return

        NodeDialog(self, self.app, node)

    def open_next_runnable_node(self) -> None:
        for node in NODES:
            if self.app.can_run(node) and not self.app.is_completed(node.key):
                NodeDialog(self, self.app, node)
                return
        messagebox.showinfo("안내", "실행 가능한 다음 노드가 없습니다.")

    def uncomplete_selected_node(self) -> None:
        node = self.get_selected_node()
        if node is None:
            messagebox.showwarning("안내", "노드를 선택하세요.")
            return

        self.app.unmark_completed(node.key)
        self.app.save()
        self.refresh_all()
        self.log(f"[완료해제] {node.name}")
        messagebox.showinfo("완료", f"{node.name} 완료 상태를 해제했습니다.")

    def clear_selected_node_data(self) -> None:
        node = self.get_selected_node()
        if node is None:
            messagebox.showwarning("안내", "노드를 선택하세요.")
            return

        if node.state_key and node.state_key in self.app.state["data"]:
            if not messagebox.askyesno("확인", f"{node.name} 데이터를 삭제할까요?"):
                return
            del self.app.state["data"][node.state_key]

        self.app.unmark_completed(node.key)
        self.app.save()
        self.refresh_all()
        self.log(f"[데이터 삭제] {node.name}")
        messagebox.showinfo("완료", f"{node.name} 데이터를 삭제했습니다.")

    def open_search_tool(self) -> None:
        if self.search_tool_window and self.search_tool_window.winfo_exists():
            self.search_tool_window.lift()
            self.search_tool_window.focus_force()
            return

        try:
            from search_yt_4 import App as SearchYTApp

            self.search_tool_window = tk.Toplevel(self.root)
            self.search_tool_window.title("YouTube 자막 추출 & 키워드 검색")
            self.search_tool_window.geometry("1280x980")
            search_app = SearchYTApp(master=self.search_tool_window)
            self.search_tool_window.protocol(
                "WM_DELETE_WINDOW",
                lambda: self._close_search_tool(search_app),
            )
            self.log("[도구] YouTube 검색 도구 창을 열었습니다.")
        except Exception as exc:
            self.log(f"[오류] YouTube 검색 도구 열기 실패: {exc}")
            messagebox.showerror("오류", f"YouTube 검색 도구를 열지 못했습니다.\n{exc}")

    def _close_search_tool(self, _search_app) -> None:
        if self.search_tool_window and self.search_tool_window.winfo_exists():
            self.search_tool_window.destroy()
        self.search_tool_window = None

    # ---------- refresh ----------
    def refresh_all(self) -> None:
        self.refresh_node_tree()
        self.refresh_data_view()
        self.refresh_summary()

    def refresh_summary(self) -> None:
        if self.summary_label is None:
            return
        completed = len(self.app.state.get("completed_nodes", []))
        total = len(NODES)
        self.summary_label.config(
            text=f"진행 상태: {completed}/{total} 완료 | 세션: {self.app.session_path.name}"
        )

    def refresh_node_tree(self) -> None:
        if self.tree is None:
            return

        for item in self.tree.get_children():
            self.tree.delete(item)

        for node in NODES:
            done = "✅" if self.app.is_completed(node.key) else "⬜"
            runnable = "예" if self.app.can_run(node) and not self.app.is_completed(node.key) else ""

            self.tree.insert(
                "",
                "end",
                values=(done, node.name, runnable),
                tags=(node.key,),
            )

    def refresh_data_view(self) -> None:
        if self.data_text is None:
            return
        text = json.dumps(self.app.state.get("data", {}), ensure_ascii=False, indent=2)
        self.data_text.delete("1.0", "end")
        self.data_text.insert("1.0", text)

    def log(self, message: str) -> None:
        if self.log_text is None:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")

    def on_close(self) -> None:
        try:
            self.app.session_path = Path(self.session_var.get())
            self.app.output_path = Path(self.output_var.get())
            self.app.save()
        except Exception:
            pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
