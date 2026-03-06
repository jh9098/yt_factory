#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""preview3 + search_yt_4 통합 GUI 진입점."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from preview3_mod.app_logic import PreviewFlowApp
from preview3_mod.data import OUTPUT_FILE, SESSION_FILE
from preview3_mod.gui import PreviewFlowGUI
from search_yt_4_mod.ui import App as SearchApp


def main() -> int:
    root = tk.Tk()
    root.title("HiddenTube 통합 도구")
    root.geometry("1640x980")
    root.minsize(1280, 760)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)

    preview_tab = ttk.Frame(notebook)
    search_tab = ttk.Frame(notebook)
    notebook.add(preview_tab, text="Preview Flow")
    notebook.add(search_tab, text="YouTube 검색/자막")

    preview_app = PreviewFlowApp(Path(SESSION_FILE), Path(OUTPUT_FILE))
    try:
        preview_app.load()
    except Exception:
        pass

    preview_gui = PreviewFlowGUI(preview_app, master=preview_tab)
    preview_gui.log("통합 GUI에서 Preview Flow 탭 로드 완료")

    SearchApp(master=search_tab, script_transfer_callback=preview_gui.receive_script_from_extract)

    def on_close() -> None:
        preview_gui.on_close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
