from __future__ import annotations

import datetime as dt
import os
import re
import threading
import tkinter as tk
from typing import Callable, Optional
from tkinter import filedialog, messagebox, scrolledtext, ttk

from tkcalendar import DateEntry

from .api import (
    FALLBACK_CHANNELS,
    HttpError,
    _compute_window_iso,
    _fmt_hhmmss,
    _format_views,
    _resolve_api_key,
    _to_iso_utc_datetime,
    extract_text_and_title,
    search_via_channel_uploads_fallback,
    search_youtube_videos_api,
)
from .scoring import format_percent, format_ratio
from .storage import (
    OUTPUT_DIR_DEFAULT,
    add_channel_to_store,
    load_channel_store,
    remove_channels_from_store,
    sanitize_filename,
)


class App(tk.Frame):
    def __init__(self, master=None, script_transfer_callback: Optional[Callable[[str, str], None]] = None):
        self._owns_root = master is None
        self.window = master if master is not None else tk.Tk()
        super().__init__(self.window)

        host_window = self.winfo_toplevel()
        if self._owns_root:
            host_window.title("YouTube 자막 추출 & 키워드 검색")

            # ==== 바깥 창 크기 조절 허용 + 기본값/최소값 ====
            host_window.resizable(True, True)     # 창 테두리 드래그로 가로/세로 리사이즈 허용
            host_window.geometry("1280x980")      # 시작 크기
            host_window.minsize(900, 700)         # 최소 크기(원하면 조정)
        self.pack(fill="both", expand=True)
        # self.maxsize(1920, 1200)     # (선택) 최대 크기 제한하려면 주석 해제

        self.cookie_path = ""
        self.output_dir = OUTPUT_DIR_DEFAULT
        self.script_transfer_callback = script_transfer_callback

        # 결과/상태
        self.result_rows = []; self.result_state = {}; self.iid_seq = 0; self.iid_meta = {}
        self.sort_state = {}; self.current_sort_col = None; self.select_all_state = False
        self.log_visible = True
        self._editing = None  # 인라인 편집 상태

        # 채널 저장소 캐시
        self.channel_store = load_channel_store()

        self._build_styles()
        self._build_layout_with_panes()

        self._safe_log("[INFO] 검색 결과에서 선택한 채널만 저장소에 저장할 수 있습니다. (자동 저장 없음)")
        if not _resolve_api_key():
            self._safe_log("[WARN] API_KEY가 비어있습니다. 코드 상단(API_KEY) 문자열에 직접 키를 넣으세요.")

    # ---------- 스타일 ----------
    def _build_styles(self):
        style = ttk.Style()
        try: style.theme_use('clam')
        except Exception: pass
        style.configure("TLabel", font=("맑은 고딕", 10))
        style.configure("TButton", font=("맑은 고딕", 10))
        style.configure("Treeview", rowheight=26, font=("맑은 고딕", 10))
        style.configure("Treeview.Heading", font=("맑은 고딕", 10, "bold"))

    # ---------- 레이아웃 (PanedWindow 기반) ----------
    def _build_layout_with_panes(self):
        # 상단 쿠키 바 영역(고정)
        top_bar = ttk.Frame(self)
        top_bar.pack(fill="x", padx=10, pady=8)
        ttk.Label(top_bar, text="쿠키 파일:").pack(side="left")
        self.lbl_cookie = ttk.Label(top_bar, text="(미선택)", foreground="#666")
        self.lbl_cookie.pack(side="left", padx=(6,10))
        ttk.Button(top_bar, text="쿠키 선택…", command=self.select_cookie).pack(side="left")
        ttk.Button(top_bar, text="쿠키 해제", command=self.clear_cookie).pack(side="left", padx=(6,0))

        # 메인 수평 분할: 좌(자막 추출) | 우(키워드 검색)
        self.hpane = ttk.Panedwindow(self, orient="horizontal")
        self.hpane.pack(fill="both", expand=True, padx=10, pady=(2,10))

        # 좌측 프레임 (자막 추출)
        self.left_frame = ttk.LabelFrame(self.hpane, text="자막 추출")
        self.hpane.add(self.left_frame, weight=1)  # 가중치 1

        ttk.Label(self.left_frame, text="유튜브 URL을 줄바꿈으로 여러 개 입력:").pack(anchor="w", padx=10, pady=(10,6))
        self.txt_urls = scrolledtext.ScrolledText(self.left_frame, height=12, wrap="word", font=("맑은 고딕", 10))
        self.txt_urls.pack(fill="both", expand=True, padx=10, pady=(0,10))

        btns_left = ttk.Frame(self.left_frame)
        btns_left.pack(fill="x", padx=10, pady=(0,10))
        self.btn_start = ttk.Button(btns_left, text="추출 시작", command=self.on_start_extract); self.btn_start.pack(side="left")
        self.btn_open_folder = ttk.Button(btns_left, text="폴더 열기", command=self.open_output_folder); self.btn_open_folder.pack(side="left", padx=(8,0))
        self.btn_clear_urls = ttk.Button(btns_left, text="전체삭제", command=self.clear_all_urls); self.btn_clear_urls.pack(side="left", padx=(8,0))

        # 우측 프레임 (키워드 검색)
        self.right_frame = ttk.LabelFrame(self.hpane, text="키워드 검색 (공식 API)")
        self.hpane.add(self.right_frame, weight=2)  # 가중치 2 (우측을 넓게)

        ttk.Label(self.right_frame, text="키워드를 줄바꿈으로 여러 개 입력:").pack(anchor="w", padx=10, pady=(10,6))
        self.txt_keywords = scrolledtext.ScrolledText(self.right_frame, height=8, wrap="word", font=("맑은 고딕", 10))
        self.txt_keywords.pack(fill="both", expand=True, padx=10, pady=(0,10))

        # 옵션 박스
        opts = ttk.LabelFrame(self.right_frame, text="검색 옵션")
        opts.pack(fill="x", padx=10, pady=(0,10))

        # 1행
        row1 = ttk.Frame(opts); row1.pack(fill="x", padx=6, pady=4)
        ttk.Label(row1, text="최대 결과 (1~50):").pack(side="left")
        self.spin_limit = ttk.Spinbox(row1, from_=1, to=50, width=6)
        self.spin_limit.set("50"); self.spin_limit.pack(side="left", padx=(6,12))
        ttk.Label(row1, text="정렬:").pack(side="left")
        self.var_sort = tk.StringVar(value="views")
        self.cmb_sort = ttk.Combobox(row1, textvariable=self.var_sort, width=10, state="readonly", values=["views","date"])
        self.cmb_sort.pack(side="left", padx=(6,10))
        ttk.Label(row1, text="views=조회수순, date=최신순", foreground="#666").pack(side="left")

        # 2행
        row2 = ttk.Frame(opts); row2.pack(fill="x", padx=6, pady=4)
        ttk.Label(row2, text="기간:").pack(side="left")
        self.var_time = tk.StringVar(value="any")
        self.cmb_time = ttk.Combobox(row2, textvariable=self.var_time, state="readonly", width=12, values=["any","day","week","month","custom"])
        self.cmb_time.pack(side="left", padx=(6,10))
        ttk.Label(row2, text="any=전체, day=24시간, week=1주, month=1개월, custom=직접입력").pack(side="left")
        self.cmb_time.bind("<<ComboboxSelected>>", self._on_time_change)

        # 3행
        row3 = ttk.Frame(opts); row3.pack(fill="x", padx=6, pady=4)
        ttk.Label(row3, text="API 길이:").pack(side="left")
        self.var_duration = tk.StringVar(value="any")
        self.cmb_duration = ttk.Combobox(row3, textvariable=self.var_duration, state="readonly", width=12, values=["any","short","medium","long"])
        self.cmb_duration.pack(side="left", padx=(6,10))
        ttk.Label(row3, text="short<4분, medium 4~20분, long>20분", foreground="#666").pack(side="left")

        # custom 기간
        self.custom_frame = ttk.Frame(opts)
        self.custom_frame.pack(fill="x", padx=6, pady=(0,6))
        ttk.Label(self.custom_frame, text="시작일:").pack(side="left")
        self.date_from = DateEntry(self.custom_frame, width=12, date_pattern="yyyy-mm-dd")
        self.date_from.pack(side="left", padx=(4,8))
        ttk.Label(self.custom_frame, text="시:").pack(side="left")
        self.spin_from_hour = ttk.Spinbox(self.custom_frame, from_=0, to=23, width=3); self.spin_from_hour.set("00"); self.spin_from_hour.pack(side="left")
        ttk.Label(self.custom_frame, text="분:").pack(side="left")
        self.spin_from_min = ttk.Spinbox(self.custom_frame, from_=0, to=59, width=3); self.spin_from_min.set("00"); self.spin_from_min.pack(side="left", padx=(2,12))
        ttk.Label(self.custom_frame, text="종료일:").pack(side="left")
        self.date_to = DateEntry(self.custom_frame, width=12, date_pattern="yyyy-mm-dd")
        self.date_to.pack(side="left", padx=(4,8))
        ttk.Label(self.custom_frame, text="시:").pack(side="left")
        self.spin_to_hour = ttk.Spinbox(self.custom_frame, from_=0, to=23, width=3); self.spin_to_hour.set("23"); self.spin_to_hour.pack(side="left")
        ttk.Label(self.custom_frame, text="분:").pack(side="left")
        self.spin_to_min = ttk.Spinbox(self.custom_frame, from_=0, to=59, width=3); self.spin_to_min.set("59"); self.spin_to_min.pack(side="left")
        self._toggle_custom_dates()

        # 로컬 필터
        localf = ttk.LabelFrame(self.right_frame, text="결과 필터(로컬)")
        localf.pack(fill="x", padx=10, pady=(0,10))
        fr_a = ttk.Frame(localf); fr_a.pack(fill="x", padx=6, pady=4)
        ttk.Label(fr_a, text="최소 조회수:").pack(side="left")
        self.spin_min_views = ttk.Spinbox(fr_a, from_=0, to=10_000_000_000, width=10)
        self.spin_min_views.set("100"); self.spin_min_views.pack(side="left", padx=(6,20))
        ttk.Label(fr_a, text="길이(초) 최소:").pack(side="left")
        self.ent_len_min = ttk.Entry(fr_a, width=10); self.ent_len_min.pack(side="left", padx=(4,12))
        ttk.Label(fr_a, text="길이(초) 최대:").pack(side="left")
        self.ent_len_max = ttk.Entry(fr_a, width=10); self.ent_len_max.pack(side="left", padx=(4,0))

        # 채널 제한 + 저장소 관리
        fr_b = ttk.Frame(opts); fr_b.pack(fill="x", padx=6, pady=4)
        ttk.Label(fr_b, text="채널ID(복수, 쉼표·공백 가능):").pack(side="left")
        self.ent_channel = ttk.Entry(fr_b); self.ent_channel.pack(side="left", fill="x", expand=True, padx=(6,10))
        ttk.Button(fr_b, text="채널ID 불러오기…", command=self.open_channel_picker).pack(side="left")
        ttk.Button(fr_b, text="저장소 관리…", command=self.open_channel_manager).pack(side="left", padx=(6,0))

        self.lbl_store_count = ttk.Label(self.right_frame, text=self._store_count_text(), foreground="#666")
        self.lbl_store_count.pack(anchor="w", padx=10, pady=(0,6))

        # 검색 실행 버튼
        self.btn_search = ttk.Button(self.right_frame, text="검색 실행", command=self.on_start_search)
        self.btn_search.pack(anchor="w", padx=10, pady=(0,10))

        # --- 하단 수직 분할: 결과 | 로그 ---
        self.vpane = ttk.Panedwindow(self, orient="vertical")
        self.vpane.pack(fill="both", expand=True, padx=10, pady=(0,10))

        # 결과 상자
        self.results_box = ttk.LabelFrame(self.vpane, text="검색 결과 (더블클릭=편집, Enter=저장, Esc=취소) - 드래그로 높이 조절 가능")
        self.vpane.add(self.results_box, weight=3)

        tools = ttk.Frame(self.results_box); tools.pack(fill="x", padx=8, pady=(8,2))
        ttk.Button(tools, text="결과 채널 저장…", command=self.open_result_channels_saver).pack(side="left")
        ttk.Label(tools, text="(검색 결과 채널 중 선택한 것만 저장소에 추가)", foreground="#666").pack(side="left", padx=(8,0))

        cols = ("sel","date","kw","channel","subs","views","vs_ratio","hit_grade","like_rate","comment_rate","length","title","url")
        self.tree = ttk.Treeview(self.results_box, columns=cols, show="headings", height=12)
        self._heading_texts = {"sel":"선택","date":"업로드일","kw":"키워드","channel":"채널","subs":"구독자수","views":"조회수","vs_ratio":"V/S","hit_grade":"판독","like_rate":"좋아요율","comment_rate":"댓글율","length":"길이","title":"제목","url":"URL"}
        for c in cols: self.tree.heading(c, text=self._heading_texts[c])
        self.tree.column("sel", width=70, anchor="center")
        self.tree.column("date", width=160, anchor="center")
        self.tree.column("kw", width=160, anchor="w")
        self.tree.column("channel", width=220, anchor="w")
        self.tree.column("subs", width=110, anchor="e")
        self.tree.column("views", width=110, anchor="e")
        self.tree.column("vs_ratio", width=90, anchor="e")
        self.tree.column("hit_grade", width=80, anchor="center")
        self.tree.column("like_rate", width=90, anchor="e")
        self.tree.column("comment_rate", width=90, anchor="e")
        self.tree.column("length", width=100, anchor="center")
        self.tree.column("title", width=500, anchor="w")
        self.tree.column("url", width=300, anchor="w")

        vsb = ttk.Scrollbar(self.results_box, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self.results_box, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.pack(fill="both", expand=True, padx=8, pady=(0,4))
        vsb.place(in_=self.tree, relx=1.0, rely=0, relheight=1.0, x=0, y=0, anchor="ne")
        hsb.pack(fill="x", padx=8, pady=(0,8))

        self.tree.tag_configure("even", background="#f7f7f9"); self.tree.tag_configure("odd", background="#ffffff")
        self.tree.bind("<Button-1>", self._on_tree_click)         # 체크박스/정렬
        self.tree.bind("<Double-1>", self._on_tree_double_click)  # 인라인 편집

        # 로그 영역(하단)
        self.log_frame = ttk.LabelFrame(self.vpane, text="로그 (드래그로 높이 조절 가능)")
        self.vpane.add(self.log_frame, weight=1)

        self.progress = ttk.Progressbar(self.log_frame, mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=(10,6))

        toggle_wrap = ttk.Frame(self.log_frame); toggle_wrap.pack(fill="x", padx=10, pady=(0,6))
        ttk.Label(toggle_wrap, text="Tip: 아래/위 경계선을 드래그하여 로그 높이를 조절하세요.", foreground="#666").pack(side="left")

        self.txt_log = scrolledtext.ScrolledText(self.log_frame, height=12, wrap="word", font=("Consolas", 10), state="normal")
        self.txt_log.pack(fill="both", expand=True, padx=10, pady=(0,10))

        # 초기 분할선 위치 조정(사용자 화면에 따라 한번 배치 후 자유롭게 변경 가능)
        self.after(50, self._place_initial_sashes)

    def _place_initial_sashes(self):
        try:
            # 좌우 분할선: 좌측 약 38% 정도
            total = self.hpane.winfo_width()
            if total <= 0: total = 1280
            self.hpane.sashpos(0, int(total * 0.2))

            # 상하 분할선: 결과 70% / 로그 30%
            total_h = self.vpane.winfo_height()
            if total_h <= 0: total_h = 600
            self.vpane.sashpos(0, int(total_h * 0.7))
        except Exception:
            pass

    # ---------- 채널 저장소 표시/갱신 ----------
    def _store_count_text(self):
        try:
            n = len(self.channel_store.get("channels", []))
            return f"저장소: {n}개 채널"
        except Exception:
            return "저장소: 0개 채널"

    def _refresh_store_cache(self):
        self.channel_store = load_channel_store()
        self.lbl_store_count.configure(text=self._store_count_text())

    # ---------- 결과에서 채널 선택 저장 ----------
    def _unique_channels_from_results(self):
        """현재 결과 테이블에서 채널ID->채널명 맵을 추출"""
        uniq = {}
        for iid, meta in self.iid_meta.items():
            ch_id = meta.get("channel_id") or ""
            if not ch_id: continue
            channel_name = self.tree.set(iid, "channel") or ""
            if ch_id not in uniq:
                uniq[ch_id] = channel_name
        pairs = [(v or "", k) for k, v in uniq.items()]
        pairs.sort(key=lambda x: (x[0] or "").lower())
        return pairs

    def open_result_channels_saver(self):
        pairs = self._unique_channels_from_results()
        if not pairs:
            messagebox.showinfo("결과 채널 저장", "현재 결과에서 저장할 채널을 찾지 못했습니다.")
            return
        win = tk.Toplevel(self); win.title("결과 채널 저장"); win.geometry("420x520"); win.grab_set()

        frm = ttk.Frame(win); frm.pack(fill="both", expand=True, padx=10, pady=8)
        ttk.Label(frm, text="채널명 검색:").pack(anchor="w")
        ent_find = ttk.Entry(frm); ent_find.pack(fill="x", pady=(0,6))

        list_frame = ttk.Frame(frm); list_frame.pack(fill="both", expand=True)
        lb = tk.Listbox(list_frame, selectmode="extended", activestyle="dotbox")
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")

        display_items = pairs[:]
        picker_map = []
        def refresh_list(pattern=""):
            lb.delete(0, tk.END); picker_map.clear()
            p = (pattern or "").strip().lower()
            for title, cid in display_items:
                if (not p) or (p in (title or "").lower()):
                    lb.insert(tk.END, title or "(제목없음)")
                    picker_map.append(cid)
        refresh_list()
        ent_find.bind("<KeyRelease>", lambda e: refresh_list(ent_find.get()))

        btns = ttk.Frame(frm); btns.pack(fill="x", pady=(8,0))
        def on_save_selected():
            sel = lb.curselection()
            ids = [picker_map[i] for i in sel]
            if not ids:
                messagebox.showwarning("선택 없음","저장할 채널을 선택하세요.")
                return
            title_by_id = {cid: title for (title, cid) in display_items}
            for cid in ids:
                add_channel_to_store(cid, title_by_id.get(cid, ""))
            self._refresh_store_cache()
            messagebox.showinfo("저장 완료", f"{len(ids)}개 채널을 저장소에 추가했습니다.")
            win.destroy()
        ttk.Button(btns, text="선택 저장", command=on_save_selected).pack(side="right", padx=(6,0))
        ttk.Button(btns, text="닫기", command=win.destroy).pack(side="right")

    # ---------- 저장소 불러오기 ----------
    def open_channel_picker(self):
        self._refresh_store_cache()
        items = self.channel_store.get("channels", [])
        if not items:
            messagebox.showinfo("채널ID 불러오기", "저장된 채널이 없습니다. 먼저 검색 후 '결과 채널 저장…'으로 추가하세요.")
            return

        win = tk.Toplevel(self); win.title("채널ID 불러오기"); win.geometry("420x520"); win.grab_set()

        frm = ttk.Frame(win); frm.pack(fill="both", expand=True, padx=10, pady=8)
        ttk.Label(frm, text="채널명 검색:").pack(anchor="w")
        ent_find = ttk.Entry(frm); ent_find.pack(fill="x", pady=(0,6))

        list_frame = ttk.Frame(frm); list_frame.pack(fill="both", expand=True)
        lb = tk.Listbox(list_frame, selectmode="extended", activestyle="dotbox")
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")

        display_items = sorted([(c.get("title") or "", c.get("id")) for c in items if c.get("id")], key=lambda x: x[0].lower())
        picker_map = []

        def refresh_list(pattern=""):
            lb.delete(0, tk.END); picker_map.clear()
            p = (pattern or "").strip().lower()
            for title, cid in display_items:
                if (not p) or (p in (title or "").lower()):
                    lb.insert(tk.END, title or "(제목없음)")
                    picker_map.append(cid)
        refresh_list()
        ent_find.bind("<KeyRelease>", lambda e: refresh_list(ent_find.get()))

        btns = ttk.Frame(frm); btns.pack(fill="x", pady=(8,0))
        def on_confirm():
            sel = lb.curselection()
            ids = [picker_map[i] for i in sel]
            if not ids:
                messagebox.showwarning("선택 없음","채널을 선택하세요.")
                return
            exist_s = self.ent_channel.get().strip()
            exist_ids = [x for x in re.split(r'[\s,]+', exist_s) if x]
            merged = []
            seen = set()
            for i in exist_ids + ids:
                if i and i not in seen:
                    seen.add(i); merged.append(i)
            self.ent_channel.delete(0, tk.END)
            self.ent_channel.insert(0, ",".join(merged))
            win.destroy()
        ttk.Button(btns, text="선택 추가", command=on_confirm).pack(side="right", padx=(6,0))
        ttk.Button(btns, text="닫기", command=win.destroy).pack(side="right")

    # ---------- 저장소 관리 ----------
    def open_channel_manager(self):
        self._refresh_store_cache()
        items = self.channel_store.get("channels", [])

        win = tk.Toplevel(self); win.title("채널 저장소 관리"); win.geometry("520x560"); win.grab_set()

        frm = ttk.Frame(win); frm.pack(fill="both", expand=True, padx=10, pady=8)
        top = ttk.Frame(frm); top.pack(fill="x")
        ttk.Label(top, text="채널명 검색:").pack(side="left")
        ent_find = ttk.Entry(top); ent_find.pack(side="left", fill="x", expand=True, padx=(6,0))

        list_frame = ttk.Frame(frm); list_frame.pack(fill="both", expand=True, pady=(6,0))
        lb = tk.Listbox(list_frame, selectmode="extended", activestyle="dotbox")
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")

        data = sorted([(c.get("title") or "", c.get("id")) for c in items if c.get("id")], key=lambda x: x[0].lower())
        idx_to_id = []
        def refresh_list(pattern=""):
            lb.delete(0, tk.END); idx_to_id.clear()
            p = (pattern or "").strip().lower()
            for title, cid in data:
                if (not p) or (p in (title or "").lower()):
                    lb.insert(tk.END, f"{title or '(제목없음)'}")
                    idx_to_id.append(cid)
        refresh_list()
        ent_find.bind("<KeyRelease>", lambda e: refresh_list(ent_find.get()))

        btns = ttk.Frame(frm); btns.pack(fill="x", pady=(8,0))
        def on_add_to_input():
            sel = lb.curselection()
            ids = [idx_to_id[i] for i in sel]
            if not ids:
                messagebox.showwarning("선택 없음","불러올 채널을 선택하세요.")
                return
            exist_s = self.ent_channel.get().strip()
            exist_ids = [x for x in re.split(r'[\s,]+', exist_s) if x]
            merged = []
            seen = set()
            for i in exist_ids + ids:
                if i and i not in seen:
                    seen.add(i); merged.append(i)
            self.ent_channel.delete(0, tk.END)
            self.ent_channel.insert(0, ",".join(merged))

        def on_delete_selected():
            sel = lb.curselection()
            ids = [idx_to_id[i] for i in sel]
            if not ids:
                messagebox.showwarning("선택 없음","삭제할 채널을 선택하세요.")
                return
            if not messagebox.askyesno("삭제 확인", f"{len(ids)}개 채널을 저장소에서 삭제할까요?"):
                return
            remove_channels_from_store(ids)
            self._refresh_store_cache()
            nonlocal_data = load_channel_store().get("channels", [])
            new_data = sorted([(c.get("title") or "", c.get("id")) for c in nonlocal_data if c.get("id")], key=lambda x: x[0].lower())
            nonlocal data; data = new_data
            refresh_list(ent_find.get())

        ttk.Button(btns, text="선택 불러오기", command=on_add_to_input).pack(side="right")
        ttk.Button(btns, text="선택 삭제", command=on_delete_selected).pack(side="right", padx=(6,8))
        ttk.Button(btns, text="닫기", command=win.destroy).pack(side="left")

    # ---------- 공통 UI ----------
    def _on_time_change(self, _=None): self._toggle_custom_dates()
    def _toggle_custom_dates(self):
        if (self.var_time.get() or "any") == "custom": self.custom_frame.pack(fill="x", padx=6, pady=(0,6))
        else: self.custom_frame.forget()

    def _safe_log(self, msg: str):
        def do():
            self.txt_log.configure(state="normal")
            self.txt_log.insert("end", msg.strip()+"\n")
            self.txt_log.see("end")
            self.txt_log.configure(state="normal")
        self.after(0, do)

    def _set_progress(self, value=None, maximum=None):
        def do():
            if maximum is not None: self.progress.configure(maximum=maximum)
            if value is not None: self.progress.configure(value=value)
        self.after(0, do)

    def _set_btns_enabled(self, extracting=None, searching=None):
        def do():
            if extracting is not None: self.btn_start.configure(state=("normal" if extracting else "disabled"))
            if searching is not None: self.btn_search.configure(state=("normal" if searching else "disabled"))
        self.after(0, do)

    # ---------- URL 입력 ----------
    def _append_url_to_input(self, url: str):
        cur = self.txt_urls.get("1.0","end")
        if url not in cur:
            if not cur.endswith("\n"): self.txt_urls.insert("end","\n")
            self.txt_urls.insert("end", url+"\n")
        self.txt_urls.see("end")

    def _remove_url_from_input(self, url: str):
        cur = self.txt_urls.get("1.0","end"); lines = [l for l in cur.splitlines() if l.strip()]
        new_lines = [l for l in lines if l.strip()!=url.strip()]
        self.txt_urls.delete("1.0","end")
        if new_lines: self.txt_urls.insert("1.0","\n".join(new_lines)+"\n")

    def clear_all_urls(self):
        self.txt_urls.delete("1.0","end")
        for iid in self.tree.get_children():
            if self.result_state.get(iid):
                self.result_state[iid] = False
                vals = list(self.tree.item(iid,"values")); vals[0] = "☐"; self.tree.item(iid, values=vals)
        self.select_all_state = False; self._update_select_header_checkbox()

    # ---------- 결과 테이블 ----------
    def _clear_results_table(self):
        self.result_rows.clear(); self.result_state.clear(); self.iid_meta.clear()
        for iid in self.tree.get_children(): self.tree.delete(iid)
        self.select_all_state = False; self._update_select_header_checkbox()

    def _append_results_rows(self, kw: str, items):
        """
        items: [url, title, date_raw, date_fmt, channel_title, view_count, dur_seconds, (opt)channel_id]
        """
        def do():
            for it in items:
                row = (it + [None] * 15)[:15]
                url, title, date_raw, date_fmt, channel, vcount, dur_sec, ch_id, subs, vs_ratio, hit_grade, _like_count, _comment_count, like_rate, comment_rate = row
                self.iid_seq += 1; iid = f"row_{self.iid_seq}"; self.result_state[iid] = False
                self.result_rows.append({
                    "iid":iid,"url":url,"title":title,"date":date_fmt or "-","kw":kw,"channel":channel or "-",
                    "subs":subs,"views":vcount,"vs_ratio":vs_ratio,"hit_grade":hit_grade or "판독불가",
                    "like_rate":like_rate,"comment_rate":comment_rate,"length":_fmt_hhmmss(dur_sec)
                })
                self.iid_meta[iid] = {
                    "dur_sec": int(dur_sec or 0),
                    "views": (int(vcount) if isinstance(vcount,int) else -1),
                    "subs": (int(subs) if isinstance(subs,int) else -1),
                    "vs_ratio": (float(vs_ratio) if isinstance(vs_ratio,(int,float)) else -1.0),
                    "like_rate": (float(like_rate) if isinstance(like_rate,(int,float)) else -1.0),
                    "comment_rate": (float(comment_rate) if isinstance(comment_rate,(int,float)) else -1.0),
                    "date_raw": date_raw or "",
                    "channel_id": ch_id or ""
                }
                tag = "even" if (len(self.tree.get_children()) % 2 == 0) else "odd"
                self.tree.insert("", "end", iid=iid, values=(
                    "☐", date_fmt or "-", kw, channel or "-", _format_views(subs), _format_views(vcount),
                    format_ratio(vs_ratio), hit_grade or "판독불가", format_percent(like_rate), format_percent(comment_rate),
                    _fmt_hhmmss(dur_sec), title, url
                ), tags=(tag,))
        self.after(0, do)

    def _update_row_stripes(self):
        for i, iid in enumerate(self.tree.get_children()):
            self.tree.item(iid, tags=("even",) if i%2==0 else ("odd",))

    def _on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region == "heading":
            col_id = self.tree.identify_column(event.x)
            if col_id == "#1": self._on_header_select_all()
            else:
                col_name = {"#1":"sel","#2":"date","#3":"kw","#4":"channel","#5":"subs","#6":"views","#7":"vs_ratio","#8":"hit_grade","#9":"like_rate","#10":"comment_rate","#11":"length","#12":"title","#13":"url"}.get(col_id,"")
                if col_name: self._sort_by_column(col_name)
            return
        if region != "cell": return
        row_id = self.tree.identify_row(event.y); col_id = self.tree.identify_column(event.x)
        if not row_id or col_id != "#1": return
        checked = self.result_state.get(row_id, False); new_checked = not checked; self.result_state[row_id] = new_checked
        vals = list(self.tree.item(row_id,"values")); vals[0] = "☑" if new_checked else "☐"; self.tree.item(row_id, values=vals)
        url = vals[-1]
        if new_checked: self._append_url_to_input(url)
        else: self._remove_url_from_input(url)
        self._refresh_select_all_state_from_rows()

    # ---------- 더블클릭 인라인 편집 ----------
    def _on_tree_double_click(self, event):
        if self._editing: self._finish_edit_widget()
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell": return
        row_id = self.tree.identify_row(event.y); col_id = self.tree.identify_column(event.x)
        if not row_id or col_id == "#1": return  # 체크박스 제외
        col_index = int(col_id[1:]) - 1
        col_name = self.tree["columns"][col_index]
        editable = {"date","kw","channel","subs","views","vs_ratio","hit_grade","like_rate","comment_rate","length","title","url"}
        if col_name not in editable: return
        bbox = self.tree.bbox(row_id, col_index)
        if not bbox: return
        x, y, w, h = bbox
        cur_val = self.tree.set(row_id, col_name)
        entry = tk.Entry(self.tree, font=("맑은 고딕", 10))
        entry.insert(0, cur_val); entry.select_range(0, tk.END); entry.focus()
        entry.place(x=x, y=y, width=w, height=h)
        entry.bind("<Return>", lambda e: self._commit_edit_cell(row_id, col_name, entry.get()))
        entry.bind("<Escape>", lambda e: self._finish_edit_widget())
        entry.bind("<FocusOut>", lambda e: self._finish_edit_widget())
        self._editing = {"iid": row_id, "col": col_name, "entry": entry}

    def _commit_edit_cell(self, iid, col_name, new_text):
        for r in self.result_rows:
            if r["iid"] == iid:
                disp_text = new_text
                if col_name == "views":
                    try:
                        v = int(str(new_text).replace(",", "").strip())
                        r["views"] = v; self.iid_meta[iid]["views"] = v; disp_text = _format_views(v)
                    except Exception:
                        r["views"] = None; self.iid_meta[iid]["views"] = -1
                elif col_name == "length":
                    try:
                        parts = [int(x) for x in new_text.strip().split(":")]
                        if len(parts) == 2: m, s = parts; sec = m*60 + s
                        elif len(parts) == 3: h, m, s = parts; sec = h*3600 + m*60 + s
                        else: raise ValueError
                        r["length"] = _fmt_hhmmss(sec); self.iid_meta[iid]["dur_sec"] = sec; disp_text = _fmt_hhmmss(sec)
                    except Exception:
                        r["length"] = new_text
                elif col_name == "date":
                    r["date"] = new_text
                    try:
                        for fmt in ("%Y-%m-%d %H:%M:%S","%Y-%m-%d %H:%M"):
                            try:
                                d = dt.datetime.strptime(new_text, fmt)
                                self.iid_meta[iid]["date_raw"] = d.strftime("%Y%m%d%H%M%S"); break
                            except Exception: pass
                    except Exception: pass
                elif col_name == "kw": r["kw"] = new_text
                elif col_name == "channel": r["channel"] = new_text
                elif col_name == "subs":
                    try:
                        v = int(str(new_text).replace(",", "").strip())
                        r["subs"] = v; self.iid_meta[iid]["subs"] = v; disp_text = _format_views(v)
                    except Exception:
                        r["subs"] = None; self.iid_meta[iid]["subs"] = -1
                elif col_name == "vs_ratio":
                    try:
                        v = float(str(new_text).strip())
                        r["vs_ratio"] = v; self.iid_meta[iid]["vs_ratio"] = v; disp_text = format_ratio(v)
                    except Exception:
                        r["vs_ratio"] = None; self.iid_meta[iid]["vs_ratio"] = -1.0
                elif col_name == "hit_grade": r["hit_grade"] = new_text
                elif col_name == "like_rate":
                    t = str(new_text).replace("%", "").strip()
                    try:
                        v = float(t) / (100.0 if "%" in str(new_text) else 1.0)
                        r["like_rate"] = v; self.iid_meta[iid]["like_rate"] = v; disp_text = format_percent(v)
                    except Exception:
                        r["like_rate"] = None; self.iid_meta[iid]["like_rate"] = -1.0
                elif col_name == "comment_rate":
                    t = str(new_text).replace("%", "").strip()
                    try:
                        v = float(t) / (100.0 if "%" in str(new_text) else 1.0)
                        r["comment_rate"] = v; self.iid_meta[iid]["comment_rate"] = v; disp_text = format_percent(v)
                    except Exception:
                        r["comment_rate"] = None; self.iid_meta[iid]["comment_rate"] = -1.0
                elif col_name == "title": r["title"] = new_text
                elif col_name == "url": r["url"] = new_text
                self.tree.set(iid, col_name, disp_text)
                break
        self._finish_edit_widget()

    def _finish_edit_widget(self):
        if self._editing and self._editing.get("entry"):
            try: self._editing["entry"].destroy()
            except Exception: pass
        self._editing = None

    # ---------- 전체선택 ----------
    def _on_header_select_all(self):
        self.select_all_state = not self.select_all_state
        make_checked = self.select_all_state
        urls_current = [l.strip() for l in self.txt_urls.get("1.0","end").splitlines() if l.strip()]
        url_set = set(urls_current)
        for iid in self.tree.get_children():
            self.result_state[iid] = make_checked
            vals = list(self.tree.item(iid,"values"))
            vals[0] = "☑" if make_checked else "☐"; self.tree.item(iid, values=vals)
            url = vals[-1]
            if make_checked: url_set.add(url)
            else: url_set.discard(url)
        self.txt_urls.delete("1.0","end")
        if url_set: self.txt_urls.insert("1.0","\n".join(sorted(url_set))+"\n")
        self._update_select_header_checkbox()

    def _refresh_select_all_state_from_rows(self):
        ch = list(self.tree.get_children())
        self.select_all_state = (all(self.result_state.get(iid, False) for iid in ch) if ch else False)
        self._update_select_header_checkbox()

    def _update_select_header_checkbox(self):
        self.tree.heading("sel", text=("선택 ☑" if self.select_all_state else "선택 ☐"))

    # ---------- 정렬 ----------
    def _clear_heading_arrows(self):
        for key, base_text in self._heading_texts.items():
            if key=="sel": continue
            self.tree.heading(key, text=base_text)
    def _set_heading_arrow(self, col: str, asc: bool):
        base = self._heading_texts.get(col, col); arrow = " ↑" if asc else " ↓"
        self.tree.heading(col, text=base+arrow)
    def _sort_by_column(self, col: str):
        asc = self.sort_state.get(col, True); asc = (not asc if self.current_sort_col==col else True)
        self.sort_state[col] = asc; self.current_sort_col = col
        def key_func(iid):
            vals = self.tree.item(iid,"values")
            if col=="date": return self.iid_meta.get(iid,{}).get("date_raw","")
            if col=="kw": return (vals[2] or "").lower()
            if col=="channel": return (vals[3] or "").lower()
            if col=="subs": return self.iid_meta.get(iid,{}).get("subs",-1)
            if col=="views": return self.iid_meta.get(iid,{}).get("views",-1)
            if col=="vs_ratio": return self.iid_meta.get(iid,{}).get("vs_ratio",-1.0)
            if col=="hit_grade": return (vals[7] or "")
            if col=="like_rate": return self.iid_meta.get(iid,{}).get("like_rate",-1.0)
            if col=="comment_rate": return self.iid_meta.get(iid,{}).get("comment_rate",-1.0)
            if col=="length": return int(self.iid_meta.get(iid,{}).get("dur_sec",0))
            if col=="title": return (vals[11] or "").lower()
            if col=="url": return (vals[12] or "").lower()
            return (vals[0] or "")
        children = list(self.tree.get_children()); children.sort(key=key_func, reverse=not asc)
        for idx, iid in enumerate(children): self.tree.move(iid, "", idx)
        self._update_row_stripes(); self._clear_heading_arrows(); self._set_heading_arrow(col, asc); self._update_select_header_checkbox()

    # ---------- 쿠키 ----------
    def select_cookie(self):
        path = filedialog.askopenfilename(title="쿠키 파일 선택 (Netscape 포맷)", filetypes=[("텍스트 파일","*.txt"),("모든 파일","*.*")])
        if path: self.cookie_path = path; self.lbl_cookie.configure(text=self.cookie_path, foreground="#0a7"); self._safe_log(f"[INFO] 쿠키 사용: {self.cookie_path}")
    def clear_cookie(self):
        self.cookie_path = ""; self.lbl_cookie.configure(text="(미선택)", foreground="#666"); self._safe_log("[INFO] 쿠키 해제")

    # ---------- 자막 추출 ----------
    def on_start_extract(self):
        urls_raw = self.txt_urls.get("1.0","end").strip()
        urls = [u.strip() for u in urls_raw.splitlines() if u.strip()]
        if not urls:
            messagebox.showwarning("안내","유튜브 URL을 한 줄에 하나씩 입력해주세요."); return
        os.makedirs(self.output_dir, exist_ok=True)
        self._set_btns_enabled(extracting=False); self._set_progress(0, maximum=len(urls))
        self._safe_log(f"[START/EXTRACT] 총 {len(urls)}개 URL 처리 시작.")
        threading.Thread(target=self._process_urls, args=(urls,), daemon=True).start()

    def _process_urls(self, urls):
        done = 0
        for url in urls:
            try:
                self._safe_log(f"\n[FETCH] {url}")
                text, title = extract_text_and_title(url, cookie_path=self.cookie_path)
                safe_title = sanitize_filename(title); out_path = os.path.join(self.output_dir, f"{safe_title}.txt")
                if text:
                    with open(out_path,"w",encoding="utf-8-sig") as f: f.write(text)
                    self._safe_log(f"[OK] 저장 완료: {out_path}")
                    self.after(0, lambda t=title, body=text, path=out_path: self._show_script_popup(t, body, path))
                else:
                    self._safe_log(f"[WARN] 자막 없음. (제목: {title})")
            except Exception as e:
                self._safe_log(f"[ERROR] 실패: {e}")
            finally:
                done += 1; self._set_progress(value=done)
        self._safe_log("\n[DONE] 자막 추출 완료."); self._set_btns_enabled(extracting=True)

    def _show_script_popup(self, title: str, text: str, out_path: str) -> None:
        popup = tk.Toplevel(self.window)
        popup.title(f"추출 스크립트: {title}")
        popup.geometry("900x640")
        popup.minsize(720, 520)

        frame = ttk.Frame(popup, padding=10)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        ttk.Label(frame, text=f"제목: {title}", font=("맑은 고딕", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=f"저장 파일: {out_path}", foreground="#666").grid(row=1, column=0, sticky="w", pady=(4, 8))

        text_widget = scrolledtext.ScrolledText(frame, wrap="word", font=("Consolas", 10))
        text_widget.grid(row=2, column=0, sticky="nsew")
        text_widget.insert("1.0", text)

        btns = ttk.Frame(frame)
        btns.grid(row=3, column=0, sticky="ew", pady=(10, 0))

        def copy_script() -> None:
            payload = text_widget.get("1.0", "end-1c")
            popup.clipboard_clear()
            popup.clipboard_append(payload)
            popup.update()
            self._safe_log(f"[복사] 스크립트 복사 완료: {title}")
            messagebox.showinfo("완료", "스크립트를 클립보드에 복사했습니다.")

        def send_to_preview() -> None:
            if self.script_transfer_callback is None:
                messagebox.showwarning("안내", "Preview 전달 콜백이 연결되지 않았습니다.")
                return
            payload = text_widget.get("1.0", "end-1c").strip()
            if not payload:
                messagebox.showwarning("안내", "전달할 스크립트 내용이 비어 있습니다.")
                return
            self.script_transfer_callback(title, payload)
            self._safe_log(f"[전달] Preview로 스크립트 전달: {title}")
            messagebox.showinfo("완료", "Preview 내용입력으로 스크립트를 전달했습니다.")

        ttk.Button(btns, text="클립보드 복사", command=copy_script).pack(side="left")
        ttk.Button(btns, text="Preview로 보내기", command=send_to_preview).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="닫기", command=popup.destroy).pack(side="right")

    # ---------- 키워드 검색 ----------
    def _parse_channel_ids_input(self, s: str):
        """쉼표/공백 분리 → UC로 시작하는 것만 반환."""
        toks = [x.strip() for x in re.split(r'[\s,]+', s or "") if x.strip()]
        return [t for t in toks if t.startswith("UC")]

    def on_start_search(self):
        kws_raw = self.txt_keywords.get("1.0","end").strip()
        keywords = [k.strip() for k in kws_raw.splitlines() if k.strip()]
        if not keywords:
            messagebox.showwarning("안내","키워드를 한 줄에 하나씩 입력해주세요."); return
        try: limit = int(self.spin_limit.get())
        except Exception: limit = 50
        limit = max(1, min(limit, 50))
        time_filter = self.var_time.get() or "any"
        sort_by = self.var_sort.get() or ("date" if time_filter!="any" else "views")
        duration_filter = self.var_duration.get() or "any"

        input_ch = self.ent_channel.get().strip()
        channel_ids_list = self._parse_channel_ids_input(input_ch)

        try: min_views = int(self.spin_min_views.get().replace(",",""))
        except Exception: min_views = 100
        len_min = self.ent_len_min.get().strip(); len_max = self.ent_len_max.get().strip()
        try: len_min = int(len_min) if len_min else None
        except Exception: messagebox.showwarning("형식 오류","길이(초) 최소는 숫자여야 합니다."); return
        try: len_max = int(len_max) if len_max else None
        except Exception: messagebox.showwarning("형식 오류","길이(초) 최대는 숫자여야 합니다."); return
        if (len_min is not None and len_max is not None) and (len_min > len_max):
            messagebox.showwarning("범위 오류","길이(초) 최소가 최대보다 클 수 없습니다."); return

        custom_from_iso = custom_to_iso = ""; cfrom_tag = cto_tag = ""
        if time_filter == "custom":
            cfrom_date = self.date_from.get_date().strftime("%Y-%m-%d"); cto_date = self.date_to.get_date().strftime("%Y-%m-%d")
            try:
                from_hour = int(self.spin_from_hour.get()); from_min = int(self.spin_from_min.get())
                to_hour = int(self.spin_to_hour.get()); to_min = int(self.spin_to_min.get())
            except ValueError:
                messagebox.showwarning("형식 오류","시간/분은 숫자여야 합니다."); return
            cfrom_tag = f"{cfrom_date} {from_hour:02d}:{from_min:02d}"
            cto_tag = f"{cto_date} {to_hour:02d}:{to_min:02d}"
            custom_from_iso = _to_iso_utc_datetime(cfrom_date, from_hour, from_min)
            custom_to_iso = _to_iso_utc_datetime(cto_date, to_hour, to_min)

        os.makedirs(self.output_dir, exist_ok=True)
        self._set_btns_enabled(searching=False); self._set_progress(0, maximum=len(keywords))
        nice_sort = "조회수순" if sort_by=="views" else "최신순"
        nice_time = {"any":"전체","day":"최근 24시간","week":"최근 1주","month":"최근 1개월","custom":f"직접입력({cfrom_tag or '...'} ~ {cto_tag or '...'})"}[time_filter]
        nice_duration = {"any":"전체 길이(API)","short":"짧음(<4분)","medium":"중간(4~20분)","long":"김(>20분)"}[duration_filter]
        local_len = f"길이(초): {len_min if len_min is not None else '-'} ~ {len_max if len_max is not None else '-'}"
        self._clear_results_table()
        self._safe_log(f"[START/SEARCH] {len(keywords)}개 키워드 | 정렬:{nice_sort} | 기간:{nice_time} | API길이:{nice_duration} | 최소조회수≥{min_views} | {local_len} | 최대결과={limit} | 채널갯수={len(channel_ids_list) or '전체'}")

        threading.Thread(
            target=self._process_keywords_api,
            args=(keywords, limit, time_filter, cfrom_tag, cto_tag, duration_filter, sort_by,
                  min_views, len_min, len_max, channel_ids_list, custom_from_iso, custom_to_iso),
            daemon=True
        ).start()

    def _merge_and_trim(self, lists, sort_by, limit):
        """여러 채널 검색결과를 합쳐 중복 제거(url 기준) 후 정렬/상위 limit."""
        merged = []; seen = set()
        for items in lists:
            for it in items:
                url = it[0]
                if url in seen: continue
                seen.add(url); merged.append(it)
        if sort_by == "views":
            merged.sort(key=lambda x: (0 if isinstance(x[5], int) else 1, -(x[5] or 0), x[2] or "00000000"))
        else:
            merged.sort(key=lambda x: x[2] or "00000000", reverse=True)
        return merged[:limit]

    def _filter_items_locally(self, items, min_views, len_min, len_max):
        filtered = []
        for it in items:
            row = (it + [None] * 15)[:15]
            url, title, date_raw, date_fmt, channel, vcount, dur_sec, ch_id, subs, vs_ratio, hit_grade, like_count, comment_count, like_rate, comment_rate = row
            if isinstance(vcount,int) and vcount < min_views: continue
            if (len_min is not None) and (dur_sec < len_min): continue
            if (len_max is not None) and (dur_sec > len_max): continue
            filtered.append([url, title, date_raw, date_fmt, channel, vcount, dur_sec, ch_id, subs, vs_ratio, hit_grade, like_count, comment_count, like_rate, comment_rate])
        return filtered

    def _save_results_to_file(self, kw, items_filtered, time_filter, cfrom_tag, cto_tag, duration_filter, sort_by):
        safe_kw = sanitize_filename(kw)
        tf_tag = time_filter if time_filter!="custom" else f"custom_{(cfrom_tag or 'NA')}_{(cto_tag or 'NA')}"
        base_name = f"{safe_kw}_검색결과_{tf_tag}_{duration_filter}_{('views' if sort_by=='views' else 'date')}"
        out_path = os.path.join(self.output_dir, sanitize_filename(base_name, 200) + ".txt")
        with open(out_path,"w",encoding="utf-8-sig") as f:
            for it in items_filtered:
                url, title, _raw, date_fmt, channel, vcount, dur_sec, _cid, subs, vs_ratio, hit_grade, _lc, _cc, like_rate, comment_rate = (it + [None] * 15)[:15]
                f.write(f"{url} | {date_fmt or '-'} | {kw} | {channel or '-'} | 구독자:{_format_views(subs)} | 조회수:{_format_views(vcount)} | V/S:{format_ratio(vs_ratio)} | 판독:{hit_grade or '판독불가'} | 좋아요율:{format_percent(like_rate)} | 댓글율:{format_percent(comment_rate)} | {title}\n")
            f.write("\n# 길이 정보(참고)\n")
            for it in items_filtered:
                url = it[0]; dur_sec = it[6]
                f.write(f"{url} | length={_fmt_hhmmss(dur_sec)} ({dur_sec}s)\n")
            f.write("\n# URL 목록\n")
            for it in items_filtered:
                f.write(f"{it[0]}\n")
        return out_path

    def _process_keywords_api(self, keywords, limit, time_filter, cfrom_tag, cto_tag,
                              duration_filter, sort_by, min_views, len_min, len_max,
                              channel_ids_list, custom_from_iso, custom_to_iso):
        done = 0
        for kw in keywords:
            try:
                self._safe_log(f"\n[QUERY] '{kw}' 검색 (최대 {limit}개)")
                per_channel_lists = []
                if channel_ids_list:
                    for cid in channel_ids_list:
                        try:
                            per_channel_lists.append(
                                search_youtube_videos_api(
                                    kw, max_results=limit,
                                    time_filter=time_filter, custom_from=custom_from_iso, custom_to=custom_to_iso,
                                    duration_filter=duration_filter, sort_by=sort_by, channel_filter=cid
                                )
                            )
                        except HttpError as e:
                            raise e
                    items = self._merge_and_trim(per_channel_lists, sort_by, limit)
                else:
                    items = search_youtube_videos_api(
                        kw, max_results=limit,
                        time_filter=time_filter, custom_from=custom_from_iso, custom_to=custom_to_iso,
                        duration_filter=duration_filter, sort_by=sort_by, channel_filter=""
                    )

            except HttpError as e:
                emsg = (getattr(e, 'content', b'') or b'').decode('utf-8','ignore')
                if hasattr(e,'resp') and getattr(e.resp,'status',None)==403 and ('quota' in emsg.lower() or 'quota' in str(e).lower()):
                    self._safe_log("[WARN] API 쿼터 초과. 채널 업로드 폴백으로 전환.")
                    api_key = _resolve_api_key()
                    after_iso, before_iso = _compute_window_iso(time_filter, custom_from_iso, custom_to_iso)
                    ch_ids = channel_ids_list[:] if channel_ids_list else FALLBACK_CHANNELS[:]
                    if not ch_ids:
                        items = []
                    else:
                        try:
                            items = search_via_channel_uploads_fallback(
                                api_key, kw, ch_ids, after_iso, before_iso,
                                max_results=limit, sort_by=("views" if sort_by=="views" else "date")
                            )
                        except Exception as e2:
                            self._safe_log(f"[ERROR] 폴백 실패: {e2}"); items = []
                else:
                    self._safe_log(f"[ERROR] API 오류('{kw}'): {e}"); items = []
            except Exception as e:
                self._safe_log(f"[ERROR] 키워드 '{kw}' 처리 실패: {e}"); items = []

            try:
                items_filtered = self._filter_items_locally(items, min_views, len_min, len_max)
                self._append_results_rows(kw, items_filtered)
                out_path = self._save_results_to_file(kw, items_filtered, time_filter, cfrom_tag, cto_tag, duration_filter, sort_by)
                self._safe_log(f"[OK] {len(items_filtered)}개 저장 완료 (원본 {len(items)}개) → {out_path}")
            except Exception as e:
                self._safe_log(f"[ERROR] 결과 저장/반영 실패: {e}")
            finally:
                done += 1; self._set_progress(value=done)

        self._safe_log("\n[DONE] 키워드 검색 완료."); self._set_btns_enabled(searching=True)


    def run(self):
        if self._owns_root:
            self.window.mainloop()

    # ---------- 폴더 열기 ----------
    def open_output_folder(self):
        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.abspath(self.output_dir)
        try:
            if os.name == 'nt': os.startfile(path)
            elif os.name == 'posix':
                import subprocess, platform
                subprocess.call(["open" if platform.system()=="Darwin" else "xdg-open", path])
        except Exception as e:
            messagebox.showerror("오류", f"폴더 열기 실패: {e}\n경로: {path}")

def main():
    app = App()
    app.run()


if __name__ == "__main__":
    main()
