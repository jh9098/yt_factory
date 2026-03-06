from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .app_logic import PreviewFlowApp
from .data import Node
from .dialogs import NodeDialog, PromptEditorDialog


class PreviewFlowGUI:
    def __init__(self, app: PreviewFlowApp, master: tk.Misc | None = None):
        self.app = app
        self._owns_root = master is None
        self.root = master if master is not None else tk.Tk()
        if self._owns_root:
            self.root.title("HiddenTube Preview Flow GUI v3")
            self.root.geometry("1560x960")

        self.session_var = tk.StringVar(value=str(self.app.session_path))
        self.output_var = tk.StringVar(value=str(self.app.output_path))
        self.project_var = tk.StringVar()

        self.tree: Optional[ttk.Treeview] = None
        self.data_text: Optional[tk.Text] = None
        self.log_text: Optional[tk.Text] = None
        self.summary_label: Optional[ttk.Label] = None
        self.project_combo: Optional[ttk.Combobox] = None

        self._build_ui()
        self.refresh_all()

        if self._owns_root:
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

        ttk.Label(path_frame, text="프로젝트").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.project_combo = ttk.Combobox(path_frame, textvariable=self.project_var, state="readonly")
        self.project_combo.grid(row=2, column=1, sticky="ew", padx=6, pady=(6, 0))
        self.project_combo.bind("<<ComboboxSelected>>", self.switch_project)
        project_btn = ttk.Frame(path_frame)
        project_btn.grid(row=2, column=2, pady=(6, 0))
        ttk.Button(project_btn, text="생성", command=self.create_project).pack(side="left")
        ttk.Button(project_btn, text="이름변경", command=self.rename_project).pack(side="left", padx=4)
        ttk.Button(project_btn, text="삭제", command=self.delete_project).pack(side="left")

        top_btn_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        top_btn_frame.grid(row=1, column=0, sticky="ew")

        for text, cmd in [
            ("세션 불러오기", self.load_session),
            ("세션 저장", self.save_session),
            ("프롬프트 템플릿 편집", self.open_prompt_editor),
            ("다음 실행 노드 열기", self.open_next_runnable_node),
            ("세션 초기화", self.reset_session),
            ("새로고침", self.refresh_all),
        ]:
            ttk.Button(top_btn_frame, text=text, command=cmd).pack(side="left", padx=(0, 6))

        ttk.Separator(top_btn_frame, orient="vertical").pack(side="left", fill="y", padx=4)
        ttk.Button(top_btn_frame, text="노드 추가", command=self.add_node).pack(side="left", padx=(6, 0))
        ttk.Button(top_btn_frame, text="선택 노드 삭제", command=self.delete_selected_node).pack(side="left", padx=(6, 0))

        ttk.Separator(top_btn_frame, orient="vertical").pack(side="left", fill="y", padx=4)
        ttk.Button(top_btn_frame, text="노드셋 저장", command=self.save_node_set).pack(side="left", padx=(6, 0))
        ttk.Button(top_btn_frame, text="노드셋 불러오기", command=self.load_node_set).pack(side="left", padx=(6, 0))
        ttk.Button(top_btn_frame, text="노드셋 삭제", command=self.delete_node_set).pack(side="left", padx=(6, 0))

        ttk.Button(top_btn_frame, text="프롬프트셋 저장", command=self.save_prompt_set).pack(side="left", padx=(12, 0))
        ttk.Button(top_btn_frame, text="프롬프트셋 불러오기", command=self.load_prompt_set).pack(side="left", padx=(6, 0))
        ttk.Button(top_btn_frame, text="프롬프트셋 삭제", command=self.delete_prompt_set).pack(side="left", padx=(6, 0))

        main_paned = ttk.Panedwindow(self.root, orient="horizontal")
        main_paned.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

        left_frame = ttk.Frame(main_paned)
        right = ttk.Panedwindow(main_paned, orient="vertical")
        main_paned.add(left_frame, weight=1)
        main_paned.add(right, weight=2)

        left_frame.rowconfigure(1, weight=1)
        left_frame.columnconfigure(0, weight=1)
        self.summary_label = ttk.Label(left_frame, text="", font=("Malgun Gothic", 10, "bold"))
        self.summary_label.grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.tree = ttk.Treeview(left_frame, columns=("status", "key", "name", "runnable"), show="headings")
        self.tree.grid(row=1, column=0, sticky="nsew")
        for col, title, width in [
            ("status", "상태", 70),
            ("key", "키", 180),
            ("name", "노드 이름", 260),
            ("runnable", "실행가능", 80),
        ]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor="center" if col != "name" else "w")
        self.tree.bind("<Double-1>", lambda _: self.open_selected_node())

        btn = ttk.Frame(left_frame)
        btn.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(btn, text="선택 노드 열기", command=self.open_selected_node).pack(side="left")
        ttk.Button(btn, text="완료해제", command=self.uncomplete_selected_node).pack(side="left", padx=4)
        ttk.Button(btn, text="데이터삭제", command=self.clear_selected_node_data).pack(side="left", padx=4)

        data_frame = ttk.Labelframe(right, text="현재 프로젝트 데이터(JSON)")
        self.data_text = tk.Text(data_frame, wrap="none", font=("Consolas", 10))
        self.data_text.pack(fill="both", expand=True)
        right.add(data_frame, weight=3)

        log_frame = ttk.Labelframe(right, text="로그")
        self.log_text = tk.Text(log_frame, wrap="word", height=10, font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True)
        right.add(log_frame, weight=1)

    def _project_display_values(self) -> list[str]:
        return [f"{name} ({pid})" for pid, name in self.app.list_projects()]

    def _parse_project_id(self, display: str) -> str:
        return display.split("(")[-1].rstrip(")").strip()

    def select_session_file(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            self.session_var.set(path)
            self.app.session_path = Path(path)

    def select_output_file(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            self.output_var.set(path)
            self.app.output_path = Path(path)

    def load_session(self) -> None:
        self.app.session_path = Path(self.session_var.get())
        self.app.load()
        self.refresh_all()
        self.log("세션 로드 완료")

    def save_session(self) -> None:
        self.app.session_path = Path(self.session_var.get())
        self.app.output_path = Path(self.output_var.get())
        self.app.save()
        self.log("세션 저장 완료")

    def switch_project(self, event=None) -> None:
        if not self.project_combo:
            return
        project_id = self._parse_project_id(self.project_var.get())
        self.app.switch_project(project_id)
        self.refresh_all()

    def create_project(self) -> None:
        name = simpledialog.askstring("프로젝트 생성", "새 프로젝트 이름")
        if not name:
            return
        self.app.create_project(name)
        self.refresh_all()

    def rename_project(self) -> None:
        name = simpledialog.askstring("프로젝트 이름변경", "새 이름", initialvalue=self.app.current_project["name"])
        if not name:
            return
        self.app.rename_current_project(name)
        self.refresh_all()

    def delete_project(self) -> None:
        pid = self.app.current_project_id
        if not messagebox.askyesno("확인", "현재 프로젝트를 삭제할까요?"):
            return
        try:
            self.app.delete_project(pid)
            self.refresh_all()
        except Exception as exc:
            messagebox.showerror("오류", str(exc))

    def add_node(self) -> None:
        key = simpledialog.askstring("노드 추가", "노드 key (영문/숫자/_) ")
        if not key:
            return
        name = simpledialog.askstring("노드 추가", "노드 이름") or key
        depends = simpledialog.askstring("노드 추가", "의존 key(쉼표구분, 선택)", initialvalue="") or ""
        prompt_key = simpledialog.askstring("노드 추가", "프롬프트 key(선택)", initialvalue=key) or None
        deps = [d.strip() for d in depends.split(",") if d.strip()]
        node = Node(key=key.strip(), name=name.strip(), depends_on=deps, state_key=key.strip(), prompt_key=prompt_key)
        try:
            self.app.add_node(node)
            self.refresh_all()
        except Exception as exc:
            messagebox.showerror("오류", str(exc))

    def get_selected_node(self) -> Optional[Node]:
        if not self.tree:
            return None
        selected = self.tree.selection()
        if not selected:
            return None
        key = self.tree.item(selected[0], "tags")[0]
        return self.app.get_node(key)

    def delete_selected_node(self) -> None:
        node = self.get_selected_node()
        if not node:
            return
        if not messagebox.askyesno("확인", f"{node.key} 노드를 삭제할까요?"):
            return
        self.app.delete_node(node.key)
        self.refresh_all()

    def open_prompt_editor(self) -> None:
        PromptEditorDialog(self, self.app)

    def open_selected_node(self) -> None:
        node = self.get_selected_node()
        if not node:
            messagebox.showwarning("안내", "노드를 선택하세요")
            return
        if not self.app.can_run(node) and not self.app.is_completed(node.key):
            messagebox.showwarning("안내", "선행 노드가 완료되지 않았습니다.")
            return
        NodeDialog(self, self.app, node)

    def open_next_runnable_node(self) -> None:
        for node in self.app.get_nodes():
            if self.app.can_run(node) and not self.app.is_completed(node.key):
                NodeDialog(self, self.app, node)
                return
        messagebox.showinfo("안내", "실행 가능한 노드가 없습니다.")

    def uncomplete_selected_node(self) -> None:
        node = self.get_selected_node()
        if not node:
            return
        self.app.unmark_completed(node.key)
        self.app.save()
        self.refresh_all()

    def clear_selected_node_data(self) -> None:
        node = self.get_selected_node()
        if not node:
            return
        self.app.current_project["data"].pop(node.key, None)
        self.app.unmark_completed(node.key)
        self.app.save()
        self.refresh_all()

    def reset_session(self) -> None:
        if messagebox.askyesno("확인", "현재 프로젝트 데이터를 초기화할까요?"):
            self.app.reset_session()
            self.refresh_all()

    def _select_name_dialog(self, title: str, candidates: list[str]) -> Optional[str]:
        if not candidates:
            messagebox.showinfo("안내", "저장된 항목이 없습니다.")
            return None
        return simpledialog.askstring(title, f"이름 입력\n가능: {', '.join(candidates)}")

    def save_node_set(self) -> None:
        name = simpledialog.askstring("노드셋 저장", "노드셋 이름")
        if name:
            self.app.save_node_set(name)
            self.log(f"노드셋 저장: {name}")

    def load_node_set(self) -> None:
        name = self._select_name_dialog("노드셋 불러오기", self.app.list_node_sets())
        if name:
            self.app.load_node_set(name)
            self.refresh_all()

    def delete_node_set(self) -> None:
        name = self._select_name_dialog("노드셋 삭제", self.app.list_node_sets())
        if name:
            self.app.delete_node_set(name)

    def save_prompt_set(self) -> None:
        name = simpledialog.askstring("프롬프트셋 저장", "프롬프트셋 이름")
        if name:
            self.app.save_prompt_set(name)

    def load_prompt_set(self) -> None:
        name = self._select_name_dialog("프롬프트셋 불러오기", self.app.list_prompt_sets())
        if name:
            self.app.load_prompt_set(name)
            self.refresh_all()

    def delete_prompt_set(self) -> None:
        name = self._select_name_dialog("프롬프트셋 삭제", self.app.list_prompt_sets())
        if name:
            self.app.delete_prompt_set(name)

    def refresh_all(self) -> None:
        if self.project_combo:
            values = self._project_display_values()
            self.project_combo["values"] = values
            for v in values:
                if self.app.current_project_id in v:
                    self.project_var.set(v)
                    break
        self.refresh_node_tree()
        self.refresh_data_view()
        self.refresh_summary()

    def refresh_summary(self) -> None:
        if self.summary_label:
            completed = len(self.app.current_project.get("completed_nodes", []))
            total = len(self.app.get_nodes())
            self.summary_label.config(text=f"프로젝트: {self.app.current_project['name']} | 진행: {completed}/{total}")

    def refresh_node_tree(self) -> None:
        if not self.tree:
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        for node in self.app.get_nodes():
            done = "✅" if self.app.is_completed(node.key) else "⬜"
            runnable = "예" if self.app.can_run(node) and not self.app.is_completed(node.key) else ""
            self.tree.insert("", "end", values=(done, node.key, node.name, runnable), tags=(node.key,))

    def refresh_data_view(self) -> None:
        if self.data_text:
            text = json.dumps(self.app.current_project.get("data", {}), ensure_ascii=False, indent=2)
            self.data_text.delete("1.0", "end")
            self.data_text.insert("1.0", text)

    def log(self, message: str) -> None:
        if self.log_text:
            self.log_text.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
            self.log_text.see("end")

    def on_close(self) -> None:
        try:
            self.app.save()
        except Exception:
            pass
        self.root.destroy()

    def run(self) -> None:
        if self._owns_root:
            self.root.mainloop()
