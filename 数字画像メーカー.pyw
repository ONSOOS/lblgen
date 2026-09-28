"""数字画像メーカー：枠付きの数字・文字画像をまとめて作るアプリ"""
import json
import os
import queue
import sys
import datetime
import platform
import threading
import tkinter as tk
import webbrowser
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

import PIL
from PIL import Image, ImageTk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import suji_core as core  # noqa: E402
import updater  # noqa: E402
from shape_lib import ShapeLibrary  # noqa: E402
from app_info import APP_NAME, AUTHOR, COMPANY, COPYRIGHT, GITHUB_REPO, VERSION  # noqa: E402
from help_text import USAGE  # noqa: E402

FROZEN = getattr(sys, "frozen", False)
APP_DIR = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
RES_DIR = getattr(sys, "_MEIPASS", APP_DIR)  # exe に同梱したファイルの場所
# exe 版の設定は %APPDATA%\SujiMaker に保存（更新やアンインストールで消えない）
CONF_DIR = os.path.join(os.environ.get("APPDATA", APP_DIR), "SujiMaker") if FROZEN else APP_DIR
os.makedirs(CONF_DIR, exist_ok=True)
SETTINGS = os.path.join(CONF_DIR, "settings.json")
_OLD_SETTINGS = os.path.join(APP_DIR, "settings.json")  # 1.0.0 より前の exe は exe の隣に保存していた
if not os.path.exists(SETTINGS) and os.path.exists(_OLD_SETTINGS):
    try:
        import shutil
        shutil.copy(_OLD_SETTINGS, SETTINGS)
    except Exception:
        pass
PREFS = os.path.join(CONF_DIR, "prefs.json")
SHAPES_DIR = os.path.join(CONF_DIR, "shapes")  # 登録した形の保存先
REG_PREFIX = "登録："
PREVIEW = 170  # プレビュー1枚の大きさ(px)

PAD_LABELS = {"": "なし（7）", "0": "0で埋める（07）", " ": "空白で埋める（ゼロサプレス）"}
VALIGN_LABELS = {"ref": "数字の高さで揃える", "ink": "文字ごとに上下中央"}
LIST_PRESETS = {
    "A〜Z": [chr(c) for c in range(ord("A"), ord("Z") + 1)],
    "a〜z": [chr(c) for c in range(ord("a"), ord("z") + 1)],
    "あ〜ん": list("あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"),
    "ア〜ン": list("アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"),
    "曜日": list("月火水木金土日"),
    "Ⅰ〜Ⅻ": list("ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ"),
}
COLOR_PRESETS = {
    "白背景": dict(fill_transparent=False, fill_color="#FFFFFF", bg_transparent=False, bg_color="#FFFFFF"),
    "すべて透過": dict(fill_transparent=True, bg_transparent=True),
    "外側だけ透過": dict(fill_transparent=False, fill_color="#FFFFFF", bg_transparent=True),
    "白抜き（塗りつぶし）": dict(fill_transparent=False, text_color="#FFFFFF", bg_transparent=True),
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  {VERSION}")
        self.minsize(980, 620)
        try:
            self.iconbitmap(os.path.join(RES_DIR, "icon.ico"))
        except Exception:
            pass
        self.prefs = {"auto_check": True, "last_check": ""}
        try:
            with open(PREFS, encoding="utf-8") as f:
                self.prefs.update(json.load(f))
        except Exception:
            pass
        self.fonts = {}
        self.v = {}
        self.q = queue.Queue()
        self.cancel_flag = False
        self.running = False
        self._after = None
        self._photos = []

        p = dict(core.DEFAULTS)
        try:
            with open(SETTINGS, encoding="utf-8") as f:
                p.update(json.load(f))
        except Exception:
            pass

        self.lib = ShapeLibrary(SHAPES_DIR)
        self._build_menu()
        self._build()
        self.set_params(p)
        threading.Thread(target=self._load_fonts, daemon=True).start()
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close)
        # 起動時の更新確認（1日1回、exe 版のみ）
        today = datetime.date.today().isoformat()
        if FROZEN and GITHUB_REPO and self.prefs["auto_check"] and self.prefs["last_check"] != today:
            self.after(3000, lambda: self.check_update(silent=True))

    # ------------------------------------------------------------ メニュー
    def _build_menu(self):
        mb = tk.Menu(self)
        fm = tk.Menu(mb, tearoff=False)
        fm.add_command(label="設定を保存…", command=self._save_preset)
        fm.add_command(label="設定を読み込む…", command=self._load_preset)
        fm.add_separator()
        fm.add_command(label="終了", command=self._close)
        mb.add_cascade(label="ファイル", menu=fm)
        hm = tk.Menu(mb, tearoff=False)
        hm.add_command(label="使い方", command=self.show_usage, accelerator="F1")
        hm.add_separator()
        hm.add_command(label="更新を確認…", command=lambda: self.check_update(silent=False))
        self.auto_check_var = tk.BooleanVar(value=self.prefs["auto_check"])
        hm.add_checkbutton(label="起動時に更新を確認する", variable=self.auto_check_var, command=self._toggle_auto_check)
        if GITHUB_REPO:
            hm.add_command(label="配布ページを開く",
                           command=lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases"))
        hm.add_separator()
        hm.add_command(label="バージョン情報", command=self.show_about)
        mb.add_cascade(label="ヘルプ", menu=hm)
        self.configure(menu=mb)
        self.bind("<F1>", lambda e: self.show_usage())

    def _save_prefs(self):
        try:
            with open(PREFS, "w", encoding="utf-8") as f:
                json.dump(self.prefs, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _toggle_auto_check(self):
        self.prefs["auto_check"] = self.auto_check_var.get()
        self._save_prefs()

    def _dialog(self, title, w=None, h=None):
        d = tk.Toplevel(self)
        d.title(title)
        d.transient(self)
        try:
            d.iconbitmap(os.path.join(RES_DIR, "icon.ico"))
        except Exception:
            pass
        if w and h:
            d.geometry(f"{w}x{h}+{self.winfo_rootx() + 60}+{self.winfo_rooty() + 40}")
        return d

    def show_usage(self):
        if getattr(self, "_usage_win", None) and self._usage_win.winfo_exists():
            self._usage_win.lift()
            return
        d = self._usage_win = self._dialog(f"{APP_NAME} の使い方", 760, 640)
        fr = ttk.Frame(d)
        fr.pack(fill="both", expand=True, padx=8, pady=8)
        sb = ttk.Scrollbar(fr)
        sb.pack(side="right", fill="y")
        t = tk.Text(fr, wrap="word", font=("Yu Gothic UI", 10), yscrollcommand=sb.set, padx=12, pady=10,
                    relief="flat", spacing1=2, spacing3=2)
        t.pack(side="left", fill="both", expand=True)
        sb.configure(command=t.yview)
        t.tag_configure("h1", font=("Yu Gothic UI", 15, "bold"), spacing1=6, spacing3=6)
        t.tag_configure("h2", font=("Yu Gothic UI", 12, "bold"), foreground="#0b5394", spacing1=12, spacing3=4)
        for line in USAGE.strip().splitlines():
            if line.startswith("# "):
                t.insert("end", line[2:] + "\n", "h1")
            elif line.startswith("## "):
                t.insert("end", line[3:] + "\n", "h2")
            else:
                t.insert("end", line + "\n")
        t.configure(state="disabled")
        ttk.Button(d, text="閉じる", command=d.destroy).pack(pady=(0, 8))

    def show_about(self):
        d = self._dialog("バージョン情報")
        d.resizable(False, False)
        fr = ttk.Frame(d, padding=20)
        fr.pack()
        try:
            ic = Image.open(os.path.join(RES_DIR, "icon.ico"))
            self._about_icon = ImageTk.PhotoImage(ic.convert("RGBA").resize((64, 64), Image.LANCZOS))
            ttk.Label(fr, image=self._about_icon).grid(row=0, column=0, rowspan=4, sticky="n", padx=(0, 16))
        except Exception:
            pass
        ttk.Label(fr, text=APP_NAME, font=("Yu Gothic UI", 16, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Label(fr, text=f"バージョン {VERSION}").grid(row=1, column=1, sticky="w")
        ttk.Label(fr, text=f"作者：{AUTHOR}\n{COPYRIGHT}\nAll rights reserved.", justify="left").grid(
            row=2, column=1, sticky="w", pady=(10, 0))
        ttk.Label(fr, foreground="#666", justify="left", text=(
            f"\n実行環境：Python {platform.python_version()} / Pillow {PIL.__version__} / "
            f"{platform.system()} {platform.release()}\n"
            "文字の描画には、このPCにインストールされているフォントを使います。\n"
            "作成した画像の利用条件は、使用したフォントのライセンスに従ってください。")
        ).grid(row=3, column=1, sticky="w")
        if GITHUB_REPO:
            url = f"https://github.com/{GITHUB_REPO}"
            lk = ttk.Label(fr, text=url, foreground="#0b5394", cursor="hand2")
            lk.grid(row=4, column=1, sticky="w", pady=(6, 0))
            lk.bind("<Button-1>", lambda e: webbrowser.open(url))
        ttk.Button(fr, text="OK", command=d.destroy).grid(row=5, column=1, sticky="e", pady=(14, 0))
        d.grab_set()

    # ------------------------------------------------------------ 更新
    def check_update(self, silent=False):
        def work():
            try:
                self.q.put(("upd_checked", updater.check(), silent))
            except Exception as e:
                self.q.put(("upd_error", str(e), silent))
        if not silent:
            self.status.configure(text="更新を確認しています…")
        threading.Thread(target=work, daemon=True).start()

    def _on_update_checked(self, info, silent):
        self.prefs["last_check"] = datetime.date.today().isoformat()
        self._save_prefs()
        if not silent:
            self.status.configure(text="")
        if not info["newer"]:
            if not silent:
                messagebox.showinfo("更新の確認", f"お使いのバージョン {VERSION} は最新です。", parent=self)
            return
        d = self._dialog("新しいバージョンがあります", 560, 420)
        fr = ttk.Frame(d, padding=14)
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text=f"新しいバージョン {info['version']} があります（現在 {VERSION}）",
                  font=("Yu Gothic UI", 12, "bold")).pack(anchor="w")
        ttk.Label(fr, text="変更内容：").pack(anchor="w", pady=(10, 2))
        t = tk.Text(fr, height=10, wrap="word", font=("Yu Gothic UI", 10))
        t.insert("1.0", info["notes"] or "（説明はありません）")
        t.configure(state="disabled")
        t.pack(fill="both", expand=True)
        pb = ttk.Progressbar(fr, mode="determinate")
        pb.pack(fill="x", pady=(10, 0))
        msg = ttk.Label(fr, text="")
        msg.pack(anchor="w")
        bf = ttk.Frame(fr)
        bf.pack(fill="x", pady=(8, 0))
        state = {"cancel": False}

        def start():
            if self.running:
                messagebox.showinfo("更新", "画像の作成中です。終わってから更新してください。", parent=d)
                return
            if not info["asset_url"]:
                webbrowser.open(info["page"])
                return
            go.configure(state="disabled")
            msg.configure(text="ダウンロードしています…")

            def work():
                try:
                    path = updater.download(
                        info, progress=lambda n, tot: self.q.put(("upd_prog", pb, msg, n, tot)),
                        cancel=lambda: state["cancel"])
                    self.q.put(("upd_ready", d, path, info["kind"]))
                except Exception as e:
                    self.q.put(("upd_fail", d, go, msg, str(e)))
            threading.Thread(target=work, daemon=True).start()

        def close():
            state["cancel"] = True
            d.destroy()
        go = ttk.Button(bf, text="ダウンロードして更新", command=start)
        go.pack(side="right")
        ttk.Button(bf, text="あとで", command=close).pack(side="right", padx=6)
        ttk.Button(bf, text="配布ページを開く", command=lambda: webbrowser.open(info["page"])).pack(side="left")
        d.protocol("WM_DELETE_WINDOW", close)

    # ------------------------------------------------------------ 画面
    def _var(self, key, kind=tk.StringVar):
        v = kind()
        v.trace_add("write", lambda *_: self.schedule_preview())
        self.v[key] = v
        return v

    def _row(self, parent, r, label, widget, note=""):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=(10, 6), pady=4)
        widget.grid(row=r, column=1, sticky="we", pady=4)
        if note:
            ttk.Label(parent, text=note, foreground="#666").grid(row=r, column=2, sticky="w", padx=6)

    def _spin(self, parent, key, lo, hi, inc=1.0, width=8):
        return ttk.Spinbox(parent, textvariable=self._var(key), from_=lo, to=hi, increment=inc, width=width)

    def _build(self):
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True)
        left = ttk.Frame(main)
        left.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        right = ttk.Frame(main)
        right.pack(side="right", fill="y", padx=8, pady=8)

        nb = ttk.Notebook(left)
        nb.pack(fill="both", expand=True)

        # --- 内容
        t = ttk.Frame(nb)
        nb.add(t, text="内容")
        mode = self._var("mode")
        mf = ttk.Frame(t)
        ttk.Radiobutton(mf, text="数字の範囲", value="range", variable=mode, command=self._mode_changed).pack(side="left")
        ttk.Radiobutton(mf, text="文字のリスト", value="list", variable=mode, command=self._mode_changed).pack(side="left", padx=12)
        self._row(t, 0, "種類", mf)
        self.range_frame = rf = ttk.LabelFrame(t, text="数字の範囲")
        rf.grid(row=1, column=0, columnspan=3, sticky="we", padx=10, pady=6)
        self._row(rf, 0, "開始", self._spin(rf, "start", 0, 99999))
        self._row(rf, 1, "終了", self._spin(rf, "end", 0, 99999))
        self._row(rf, 2, "間隔", self._spin(rf, "step", 1, 9999))
        self._row(rf, 3, "桁数", self._spin(rf, "digits", 1, 6), "この桁数に満たない数字を埋めます")
        self.pad_cb = ttk.Combobox(rf, values=list(PAD_LABELS.values()), state="readonly", width=28)
        self.pad_cb.bind("<<ComboboxSelected>>", lambda e: self.schedule_preview())
        self._row(rf, 4, "桁の埋め方", self.pad_cb)
        self._row(rf, 5, "前に付ける文字", ttk.Entry(rf, textvariable=self._var("prefix"), width=12), "例：No.")
        self._row(rf, 6, "後ろに付ける文字", ttk.Entry(rf, textvariable=self._var("suffix"), width=12), "例：番")

        self.list_frame = lf = ttk.LabelFrame(t, text="文字のリスト（1行に1つ、またはカンマ区切り）")
        lf.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=10, pady=6)
        t.rowconfigure(2, weight=1)
        t.columnconfigure(1, weight=1)
        self.items_text = tk.Text(lf, height=8, width=40, font=("Yu Gothic UI", 11))
        self.items_text.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        self.items_text.bind("<<Modified>>", self._items_modified)
        bf = ttk.Frame(lf)
        bf.pack(side="right", fill="y", padx=6)
        ttk.Label(bf, text="入力例：").pack(anchor="w")
        for name, vals in LIST_PRESETS.items():
            ttk.Button(bf, text=name, width=10, command=lambda vs=vals: self._set_items("\n".join(vs))).pack(pady=1)
        self.count_label = ttk.Label(t, text="")
        self.count_label.grid(row=3, column=0, columnspan=3, sticky="w", padx=10, pady=4)

        # --- 文字
        t = ttk.Frame(nb)
        nb.add(t, text="文字")
        t.columnconfigure(1, weight=1)
        ff = ttk.Frame(t)
        self.font_filter = tk.StringVar()
        self.font_filter.trace_add("write", lambda *_: self._filter_fonts())
        ttk.Entry(ff, textvariable=self.font_filter, width=14).pack(side="left")
        ttk.Label(ff, text="で絞り込み").pack(side="left", padx=(2, 8))
        ttk.Button(ff, text="ファイルから選ぶ…", command=self._pick_font_file).pack(side="left")
        self._row(t, 0, "フォント検索", ff)
        self.font_cb = ttk.Combobox(t, state="readonly", width=46, values=["（フォント一覧を読み込み中…）"])
        self.font_cb.bind("<<ComboboxSelected>>", self._font_selected)
        self._row(t, 1, "フォント", self.font_cb)
        self.font_file_label = ttk.Label(t, text="", foreground="#666")
        self.font_file_label.grid(row=2, column=1, columnspan=2, sticky="w")
        self._row(t, 3, "文字の高さ（%）", self._spin(t, "text_height", 5, 95, 1), "数字「0」の高さ ÷ 画像の短辺")
        self._row(t, 4, "文字の最大幅（%）", self._spin(t, "max_width", 5, 100, 1), "これより広い文字は縮めて収めます")
        self._row(t, 5, "縮小の下限（%）", self._spin(t, "min_scale", 0, 100, 1),
                  "ここまでは縦横同じ比率で縮小し、それでも入らない分は横だけ縮めます")
        self._row(t, 6, "太さ補正（%）", self._spin(t, "bold", 0, 30, 0.5), "文字を太らせます（細いフォント向け）")
        self.valign_cb = ttk.Combobox(t, values=list(VALIGN_LABELS.values()), state="readonly", width=24)
        self.valign_cb.bind("<<ComboboxSelected>>", lambda e: self.schedule_preview())
        self._row(t, 7, "上下位置の基準", self.valign_cb, "数字なら「数字の高さ」がおすすめ")
        self._row(t, 8, "位置調整 横（%）", self._spin(t, "offset_x", -50, 50, 0.5), "＋で右へ")
        self._row(t, 9, "位置調整 縦（%）", self._spin(t, "offset_y", -50, 50, 0.5), "＋で下へ")

        # --- 枠
        t = ttk.Frame(nb)
        nb.add(t, text="枠")
        t.columnconfigure(1, weight=1)
        ttk.Checkbutton(t, text="枠線を描く", variable=self._var("frame_on", tk.BooleanVar)).grid(
            row=0, column=1, sticky="w", pady=4)
        ttk.Label(t, text="外すと線だけを消します（枠の内側の色は残ります）", foreground="#666").grid(
            row=0, column=2, sticky="w", padx=6)
        self.shape_cb = ttk.Combobox(t, state="readonly", width=28, height=24)
        self.shape_cb.bind("<<ComboboxSelected>>", self._shape_changed)
        self._row(t, 1, "形", self.shape_cb, "変えると文字の高さ・最大幅・縦位置をその形のおすすめ値にします")
        rb = ttk.Frame(t)
        ttk.Button(rb, text="形を登録…", command=self._register_shape).pack(side="left")
        ttk.Button(rb, text="登録した形の管理…", command=self._manage_shapes).pack(side="left", padx=4)
        self._row(t, 2, "", rb, "好きな形の画像に名前を付けて「形」の一覧に追加できます")
        self._row(t, 3, "線の太さ（%）", self._spin(t, "line_width", 0, 40, 0.5), "画像の短辺に対する割合")
        self._row(t, 4, "外側の余白（%）", self._spin(t, "margin", 0, 40, 0.5))
        self._row(t, 5, "角の丸み（%）", self._spin(t, "radius", 0, 50, 1), "角丸正方形・角丸長方形のみ")
        sf = ttk.Frame(t)
        ttk.Entry(sf, textvariable=self._var("shape_image"), width=40).pack(side="left", fill="x", expand=True)
        ttk.Button(sf, text="参照…", command=self._pick_shape_image).pack(side="left", padx=4)
        self._row(t, 6, "形の画像", sf)
        ttk.Label(t, foreground="#666", justify="left", text=(
            "「任意の形状（画像から）」のときに使います（登録せずにその場で使う場合）。\n"
            "透過PNGなら不透明な部分、それ以外の画像なら白地の上の黒い部分を形とみなし、\n"
            "縦横比を保ったまま枠の範囲に収めて、その輪郭に枠線を引きます。\n\n"
            "「登録：」で始まる形は、登録した形です。星・ハート・吹き出し・盾・五角形・ホームベースを見本として登録してあります。\n"
            "円・正方形・角丸正方形は、画像が長方形でも短辺に合わせた正方形の枠を中央に描きます。\n"
            "楕円・長方形・角丸長方形の縦横比は「出力」タブの幅と高さで決まります。")
        ).grid(row=7, column=0, columnspan=3, sticky="w", padx=10, pady=6)
        self._refresh_shapes()

        # --- 色
        t = ttk.Frame(nb)
        nb.add(t, text="色")
        t.columnconfigure(1, weight=1)
        self._color_row(t, 0, "文字の色", "text_color")
        self._color_row(t, 1, "枠線の色", "frame_color")
        self._color_row(t, 2, "枠の内側の色", "fill_color", "fill_transparent")
        self._color_row(t, 3, "枠の外側の色", "bg_color", "bg_transparent")
        pf = ttk.Frame(t)
        for name, vals in COLOR_PRESETS.items():
            ttk.Button(pf, text=name, command=lambda vs=vals: self._apply_color_preset(vs)).pack(side="left", padx=2)
        self._row(t, 4, "よく使う組み合わせ", pf)
        cf = ttk.Frame(t)
        for name, col in (("黒", "#000000"), ("赤", "#E60012"), ("青", "#0068B7"), ("緑", "#009944")):
            ttk.Button(cf, text=name, width=5,
                       command=lambda c=col: self._apply_color_preset(dict(text_color=c, frame_color=c))).pack(side="left", padx=2)
        self._row(t, 5, "文字と枠を同じ色に", cf)
        ttk.Label(t, text="透過は PNG・TIFF・WEBP で有効です（JPEG・BMP・PDF は白で塗ります）",
                  foreground="#666").grid(row=6, column=0, columnspan=3, sticky="w", padx=10, pady=8)

        # --- 出力
        t = ttk.Frame(nb)
        nb.add(t, text="出力")
        t.columnconfigure(1, weight=1)
        self._row(t, 0, "幅（px）", self._spin(t, "width", 16, 10000, 100))
        self._row(t, 1, "高さ（px）", self._spin(t, "height", 16, 10000, 100))
        self._row(t, 2, "解像度（dpi）", self._spin(t, "dpi", 72, 2400, 50))
        self.mm_label = ttk.Label(t, text="", foreground="#666")
        self.mm_label.grid(row=3, column=1, sticky="w")
        self.fmt_cb = ttk.Combobox(t, values=list(core.FORMATS), state="readonly", width=10, textvariable=self._var("fmt"))
        self._row(t, 4, "画像形式", self.fmt_cb)
        self._row(t, 5, "JPEG の品質", self._spin(t, "jpeg_quality", 50, 100, 1))
        of = ttk.Frame(t)
        ttk.Entry(of, textvariable=self._var("out_dir"), width=50).pack(side="left", fill="x", expand=True)
        ttk.Button(of, text="参照…", command=self._pick_dir).pack(side="left", padx=4)
        self._row(t, 6, "保存先フォルダ", of)
        self._row(t, 7, "ファイル名", ttk.Entry(t, textvariable=self._var("filename"), width=30))
        ttk.Label(t, foreground="#666", justify="left", text=(
            "{text} … 画像の中の文字　　{index} … 通し番号（1から）　　{n} … 数字\n"
            "{n:03d} のように書くと 007 のように0埋めします。例：丸_黒_{n:03d}_透過")
        ).grid(row=8, column=1, columnspan=2, sticky="w")
        self.name_label = ttk.Label(t, text="", foreground="#666")
        self.name_label.grid(row=9, column=1, columnspan=2, sticky="w", pady=4)

        # --- 下部ボタン
        bottom = ttk.Frame(left)
        bottom.pack(fill="x", pady=(8, 0))
        ttk.Button(bottom, text="設定を保存…", command=self._save_preset).pack(side="left")
        ttk.Button(bottom, text="設定を読み込む…", command=self._load_preset).pack(side="left", padx=4)
        ttk.Button(bottom, text="初期値に戻す", command=lambda: self.set_params(dict(core.DEFAULTS))).pack(side="left")
        self.open_btn = ttk.Button(bottom, text="保存先を開く", command=self._open_dir)
        self.open_btn.pack(side="right")
        self.gen_btn = ttk.Button(bottom, text="画像を作成", command=self._generate)
        self.gen_btn.pack(side="right", padx=4)
        self.progress = ttk.Progressbar(left, mode="determinate")
        self.progress.pack(fill="x", pady=(6, 0))
        self.status = ttk.Label(left, text="")
        self.status.pack(anchor="w")

        # --- プレビュー
        ttk.Label(right, text="プレビュー（最初・最長・最後）").pack(anchor="w")
        self.canvas = tk.Canvas(right, width=PREVIEW + 20, height=(PREVIEW + 10) * 3 + 10, highlightthickness=0, bg="#e8e8e8")
        self.canvas.pack(pady=4)
        self.checker = ttk.Checkbutton(right, text="透過部分を市松模様で表示", command=self.schedule_preview)
        self.checker_var = tk.BooleanVar(value=True)
        self.checker.configure(variable=self.checker_var)
        self.checker.pack(anchor="w")
        self.preview_err = ttk.Label(right, text="", foreground="#c00", wraplength=PREVIEW + 20)
        self.preview_err.pack(anchor="w")

    def _color_row(self, parent, r, label, key, tkey=None):
        f = ttk.Frame(parent)
        var = self._var(key)
        sw = tk.Label(f, width=4, relief="solid", bd=1)
        sw.pack(side="left")
        ttk.Entry(f, textvariable=var, width=10).pack(side="left", padx=4)
        ttk.Button(f, text="選ぶ…", command=lambda: self._pick_color(key)).pack(side="left")

        def upd(*_):
            try:
                sw.configure(bg="#%02x%02x%02x" % core._rgb(var.get()))
            except Exception:
                pass
        var.trace_add("write", upd)
        if tkey:
            ttk.Checkbutton(f, text="透明にする", variable=self._var(tkey, tk.BooleanVar)).pack(side="left", padx=10)
        self._row(parent, r, label, f)

    # ------------------------------------------------------------ 値の出し入れ
    def get_params(self):
        p = dict(core.DEFAULTS)
        for k, v in self.v.items():
            val = v.get()
            d = core.DEFAULTS[k]
            if isinstance(d, bool):
                p[k] = bool(val)
            elif isinstance(d, int):
                p[k] = int(float(val))
            elif isinstance(d, float):
                p[k] = float(val)
            else:
                p[k] = val
        p["pad"] = {v: k for k, v in PAD_LABELS.items()}.get(self.pad_cb.get(), "0")
        p["valign"] = {v: k for k, v in VALIGN_LABELS.items()}.get(self.valign_cb.get(), "ref")
        label = self.shape_cb.get()
        reg = self.lib.get(label[len(REG_PREFIX):]) if label.startswith(REG_PREFIX) else None
        if reg:
            p["shape"], p["shape_image"] = "custom", self.lib.path(reg)
        else:
            p["shape"] = {v: k for k, v in core.SHAPES.items()}.get(label, "circle")
        p["items"] = self.items_text.get("1.0", "end").strip()
        p["font_path"], p["font_index"] = self.font_path, self.font_index
        core._rgb(p["text_color"]), core._rgb(p["frame_color"]), core._rgb(p["fill_color"]), core._rgb(p["bg_color"])
        return p

    def set_params(self, p):
        self._loading = True
        for k, v in self.v.items():
            if k in p:
                v.set(p[k])
        self.pad_cb.set(PAD_LABELS.get(p.get("pad", "0"), PAD_LABELS["0"]))
        self.valign_cb.set(VALIGN_LABELS.get(p.get("valign", "ref")))
        shape = p.get("shape", "circle")
        reg = self.lib.find_by_path(p.get("shape_image")) if shape == "custom" else None
        if reg:
            self.shape_cb.set(REG_PREFIX + reg["name"])
        elif shape == "none":  # 古い「枠なし」は、枠線なしの正方形として読み込む
            self.shape_cb.set(core.SHAPES["square"])
            self.v["frame_on"].set(False)
        else:
            self.shape_cb.set(core.SHAPES.get(shape, core.SHAPES["circle"]))
        self._set_items(p.get("items", ""))
        self.font_path, self.font_index = p["font_path"], int(p.get("font_index", 0))
        self._show_font()
        self._loading = False
        self._mode_changed()

    # ------------------------------------------------------------ イベント
    def _mode_changed(self):
        on = self.v["mode"].get() == "range"
        for w in self.range_frame.winfo_children():
            self._set_state(w, on)
        self._set_state(self.items_text, not on)
        self.items_text.configure(bg="#f0f0f0" if on else "white", fg="#999" if on else "black")
        self.schedule_preview()

    def _set_state(self, w, on):
        try:
            w.configure(state=("normal" if on else "disabled"))
        except tk.TclError:
            pass
        if isinstance(w, ttk.Combobox) and on:
            w.configure(state="readonly")
        for c in w.winfo_children():
            self._set_state(c, on)

    def _set_items(self, text):
        st = self.items_text.cget("state")
        self.items_text.configure(state="normal")
        self.items_text.delete("1.0", "end")
        self.items_text.insert("1.0", text)
        self.items_text.configure(state=st)
        self.schedule_preview()

    def _items_modified(self, _):
        self.items_text.edit_modified(False)
        self.schedule_preview()

    def _shape_changed(self, _=None):
        label = self.shape_cb.get()
        if label.startswith(REG_PREFIX):
            reg = self.lib.get(label[len(REG_PREFIX):])
            shape = "custom"
            th, mw, oy = self.lib.recommended(reg) if reg else core.SHAPE_TEXT["custom"]
        else:
            shape = {v: k for k, v in core.SHAPES.items()}[label]
            th, mw, oy = core.SHAPE_TEXT[shape]
            reg = None
        self.v["text_height"].set(th)
        self.v["max_width"].set(mw)
        self.v["offset_y"].set(oy)
        try:
            w, h = int(float(self.v["width"].get())), int(float(self.v["height"].get()))
        except ValueError:
            w = h = 0
        if shape in ("ellipse", "rect", "rrect") and w == h and w > 0:
            self.v["height"].set(round(w * 0.6))  # 正方形のままだと区別できないので横長にする
            self.status.configure(text="横長にするため、高さを幅の60%にしました（「出力」タブで変更できます）")
        elif shape == "custom" and not reg and not self.v["shape_image"].get():
            self._pick_shape_image()
        self.schedule_preview()

    # ------------------------------------------------------------ 形の登録
    def _refresh_shapes(self, select=None):
        self.shape_cb.configure(values=list(core.SHAPES.values()) + [REG_PREFIX + n for n in self.lib.names()])
        if select:
            self.shape_cb.set(select)
        elif self.shape_cb.get().startswith(REG_PREFIX) and not self.lib.get(self.shape_cb.get()[len(REG_PREFIX):]):
            self.shape_cb.set(core.SHAPES["circle"])  # 選んでいた形が削除された
        self.schedule_preview()

    def _ask_shape_file(self, parent):
        return filedialog.askopenfilename(
            parent=parent, title="登録する形の画像を選ぶ",
            filetypes=[("画像", "*.png *.gif *.bmp *.jpg *.jpeg *.tif *.tiff *.webp"), ("すべて", "*.*")])

    def _register_shape(self, parent=None):
        parent = parent or self
        f = self._ask_shape_file(parent)
        if not f:
            return None
        name = simpledialog.askstring("形を登録", "この形の名前：", parent=parent,
                                      initialvalue=os.path.splitext(os.path.basename(f))[0])
        if not name:
            return None
        try:
            it = self.lib.add(name, f)
        except Exception as e:
            messagebox.showerror("形を登録", str(e), parent=parent)
            return None
        self._refresh_shapes(select=REG_PREFIX + it["name"])
        self._shape_changed()
        return it

    def _manage_shapes(self):
        if getattr(self, "_shape_win", None) and self._shape_win.winfo_exists():
            self._shape_win.lift()
            return
        d = self._shape_win = self._dialog("登録した形の管理", 640, 460)
        fr = ttk.Frame(d, padding=10)
        fr.pack(fill="both", expand=True)
        lb = tk.Listbox(fr, width=24, font=("Yu Gothic UI", 11), activestyle="none", exportselection=False)
        lb.pack(side="left", fill="y")
        right = ttk.Frame(fr)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        cv = tk.Canvas(right, width=220, height=220, bg="#e8e8e8", highlightthickness=0)
        cv.pack(anchor="w")
        info = ttk.Label(right, text="", foreground="#666", justify="left")
        info.pack(anchor="w", pady=4)
        bf = ttk.Frame(right)
        bf.pack(anchor="w", fill="x")

        def names():
            lb.delete(0, "end")
            for n in self.lib.names():
                lb.insert("end", n)

        def cur():
            sel = lb.curselection()
            return self.lib.get(lb.get(sel[0])) if sel else None

        def show(_=None):
            cv.delete("all")
            it = cur()
            if not it:
                info.configure(text="")
                return
            try:
                p = dict(self.get_params(), shape="custom", shape_image=self.lib.path(it), width=200, height=200)
                p["text_height"], p["max_width"], p["offset_y"] = self.lib.recommended(it)
                items = core.make_items(p)
                img = core.render(items[0], p) if items else None
                bg = Image.new("RGBA", (200, 200), (255, 255, 255, 255))
                if img:
                    bg.alpha_composite(img)
                self._shape_photo = ImageTk.PhotoImage(bg)
                cv.create_image(10, 10, image=self._shape_photo, anchor="nw")
            except Exception as e:
                cv.create_text(110, 110, text=f"表示できません\n{e}", width=200)
            th, mw, oy = self.lib.recommended(it)
            info.configure(text=f"おすすめの文字：高さ {th}%　最大幅 {mw}%　縦位置 {oy}%")

        def select(name):
            names()
            if name in self.lib.names():
                i = self.lib.names().index(name)
                lb.selection_set(i)
                lb.see(i)
            show()

        def add():
            it = self._register_shape(parent=d)
            if it:
                select(it["name"])

        def rename():
            it = cur()
            if not it:
                return
            new = simpledialog.askstring("名前を変更", "新しい名前：", parent=d, initialvalue=it["name"])
            if not new:
                return
            try:
                was = self.shape_cb.get() == REG_PREFIX + it["name"]
                self.lib.rename(it["name"], new)
            except Exception as e:
                messagebox.showerror("名前を変更", str(e), parent=d)
                return
            self._refresh_shapes(select=REG_PREFIX + it["name"] if was else None)
            select(it["name"])

        def delete():
            it = cur()
            if it and messagebox.askyesno("削除", f"「{it['name']}」を削除しますか？", parent=d):
                self.lib.delete(it["name"])
                self._refresh_shapes()
                select("")

        def save_text():
            it = cur()
            if not it:
                return
            try:
                p = self.get_params()
            except Exception as e:
                messagebox.showerror("おすすめ値", str(e), parent=d)
                return
            self.lib.set_recommended(it["name"], p["text_height"], p["max_width"], p["offset_y"])
            show()

        def use():
            it = cur()
            if it:
                self.shape_cb.set(REG_PREFIX + it["name"])
                self._shape_changed()

        def move(delta):
            it = cur()
            if it:
                self.lib.move(it["name"], delta)
                self._refresh_shapes(select=self.shape_cb.get())
                select(it["name"])

        bf2 = ttk.Frame(right)
        bf2.pack(anchor="w", fill="x")
        for parent, row in ((bf, (("この形を使う", use), ("追加…", add), ("名前を変更…", rename), ("削除", delete))),
                            (bf2, (("▲ 上へ", lambda: move(-1)), ("▼ 下へ", lambda: move(1))))):
            for text, cmd in row:
                ttk.Button(parent, text=text, command=cmd).pack(side="left", padx=(0, 4), pady=2)
        ttk.Button(right, text="今の「文字の高さ・最大幅・縦位置」をこの形のおすすめ値にする",
                   command=save_text).pack(anchor="w", pady=(8, 0))
        ttk.Label(right, foreground="#666", justify="left", wraplength=360, text=(
            "おすすめ値は、「形」の一覧でこの形を選んだときに自動で設定されます。\n"
            "形は設定フォルダに保存されるので、元の画像を消しても使えます。")).pack(anchor="w", pady=(8, 0))
        ttk.Button(d, text="閉じる", command=d.destroy).pack(pady=(0, 8))
        lb.bind("<<ListboxSelect>>", show)
        lb.bind("<Double-Button-1>", lambda e: use())
        cur_label = self.shape_cb.get()
        select(cur_label[len(REG_PREFIX):] if cur_label.startswith(REG_PREFIX) else
               (self.lib.names() or [""])[0])

    def _pick_shape_image(self):
        f = filedialog.askopenfilename(parent=self, title="形の画像を選ぶ",
                                       filetypes=[("画像", "*.png *.gif *.bmp *.jpg *.jpeg *.tif *.tiff *.webp"),
                                                  ("すべて", "*.*")])
        if f:
            self.v["shape_image"].set(os.path.normpath(f))

    def _apply_color_preset(self, vals):
        for k, val in vals.items():
            self.v[k].set(val)
        if vals.get("text_color") == "#FFFFFF" and "fill_color" not in vals:
            self.v["fill_color"].set(self.v["frame_color"].get())

    def _pick_color(self, key):
        c = colorchooser.askcolor(self.v[key].get(), parent=self)[1]
        if c:
            self.v[key].set(c.upper())

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.v["out_dir"].get() or os.path.expanduser("~"), parent=self)
        if d:
            self.v["out_dir"].set(os.path.normpath(d))

    def _open_dir(self):
        d = self.v["out_dir"].get()
        if os.path.isdir(d):
            os.startfile(d)
        else:
            messagebox.showinfo("保存先", "保存先フォルダはまだありません。画像を作成すると作られます。", parent=self)

    # ------------------------------------------------------------ フォント
    def _load_fonts(self):
        self.q.put(("fonts", core.list_fonts()))

    def _filter_fonts(self):
        s = self.font_filter.get().lower()
        self.font_cb.configure(values=[n for n in self.fonts if s in n.lower()] or ["（見つかりません）"])

    def _font_selected(self, _):
        name = self.font_cb.get()
        if name in self.fonts:
            self.font_path, self.font_index = self.fonts[name]
            self._show_font()
            self.schedule_preview()

    def _pick_font_file(self):
        f = filedialog.askopenfilename(parent=self, filetypes=[("フォント", "*.ttf *.otf *.ttc *.otc"), ("すべて", "*.*")])
        if f:
            self.font_path, self.font_index = os.path.normpath(f), 0
            self._show_font()
            self.schedule_preview()

    def _show_font(self):
        name = next((n for n, v in self.fonts.items()
                     if os.path.normcase(v[0]) == os.path.normcase(self.font_path) and v[1] == self.font_index), None)
        self.font_cb.set(name or os.path.basename(self.font_path))
        self.font_file_label.configure(text=f"{self.font_path}（{self.font_index}）")

    # ------------------------------------------------------------ プレビュー
    def schedule_preview(self):
        if getattr(self, "_loading", False):
            return
        if self._after:
            self.after_cancel(self._after)
        self._after = self.after(250, self.update_preview)

    def update_preview(self):
        self._after = None
        self.canvas.delete("all")
        self._photos = []
        try:
            p = self.get_params()
            items = core.make_items(p)
            if not items:
                raise ValueError("作る文字がありません")
            names = core.file_names(items, p)
        except Exception as e:
            self.preview_err.configure(text=f"設定を確認してください：{e}")
            self.count_label.configure(text="")
            return
        self.preview_err.configure(text="")
        self.count_label.configure(text=f"{len(items)} 枚作成します")
        W, H = p["width"], p["height"]
        self.mm_label.configure(text=f"印刷サイズ：{W / p['dpi'] * 25.4:.1f} × {H / p['dpi'] * 25.4:.1f} mm")
        self.name_label.configure(text="ファイル名の例：" + "、".join(os.path.basename(n) for n in names[:3])
                                  + (" …" if len(names) > 3 else ""))
        longest = max(items, key=lambda it: len(it["text"]))
        picks = []
        for it in (items[0], longest, items[-1]):
            if it not in picks:
                picks.append(it)
        scale = PREVIEW / max(W, H)
        y = 10
        for it in picks:
            try:
                img = core.render(it, p, scale)
            except Exception as e:
                self.preview_err.configure(text=f"描画できません：{e}")
                return
            bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
            if self.checker_var.get():
                c = 8
                for yy in range(0, img.height, c):
                    for xx in range(0, img.width, c):
                        if (xx // c + yy // c) % 2:
                            bg.paste((204, 204, 204, 255), (xx, yy, xx + c, yy + c))
            bg.alpha_composite(img)
            ph = ImageTk.PhotoImage(bg)
            self._photos.append(ph)
            self.canvas.create_image(10 + (PREVIEW - img.width) // 2, y, image=ph, anchor="nw")
            y += PREVIEW + 10

    # ------------------------------------------------------------ 生成
    def _generate(self):
        if self.running:
            self.cancel_flag = True
            return
        try:
            p = self.get_params()
            items = core.make_items(p)
            names = core.file_names(items, p)
        except Exception as e:
            messagebox.showerror("設定エラー", str(e), parent=self)
            return
        if not items:
            messagebox.showerror("設定エラー", "作る文字がありません", parent=self)
            return
        exist = sum(os.path.exists(n) for n in names)
        if exist and not messagebox.askyesno(
                "上書きの確認", f"保存先に同じ名前のファイルが {exist} 個あります。上書きしますか？", parent=self):
            return
        self._save_settings(p)
        self.running, self.cancel_flag = True, False
        self.gen_btn.configure(text="中止")
        self.progress.configure(maximum=len(items), value=0)
        self.status.configure(text="作成中…")

        def work():
            try:
                done = core.generate(p, progress=lambda i, n: self.q.put(("prog", i, n)),
                                     cancel=lambda: self.cancel_flag)
                self.q.put(("done", len(done), len(items), p["out_dir"]))
            except Exception as e:
                self.q.put(("error", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "fonts":
                    self.fonts = msg[1]
                    self._filter_fonts()
                    self._show_font()
                elif msg[0] == "prog":
                    self.progress.configure(value=msg[1])
                    self.status.configure(text=f"作成中… {msg[1]} / {msg[2]}")
                elif msg[0] == "upd_checked":
                    self._on_update_checked(msg[1], msg[2])
                elif msg[0] == "upd_error":
                    self.status.configure(text="")
                    if not msg[2]:
                        messagebox.showerror("更新の確認", f"更新を確認できませんでした。\n{msg[1]}", parent=self)
                elif msg[0] == "upd_prog":
                    _, pb, lab, n, tot = msg
                    if pb.winfo_exists():
                        pb.configure(maximum=tot or 1, value=n)
                        lab.configure(text=f"ダウンロードしています… {n / 1048576:.1f} / {tot / 1048576:.1f} MB")
                elif msg[0] == "upd_fail":
                    _, d, go, lab, err = msg
                    if d.winfo_exists():
                        lab.configure(text="")
                        go.configure(state="normal")
                        messagebox.showerror("更新", err, parent=d)
                elif msg[0] == "upd_ready":
                    _, d, path, kind = msg
                    if messagebox.askokcancel(
                            "更新", "ダウンロードと確認が終わりました。アプリを終了して更新します。\n"
                            "更新が終わると自動で起動し直します。", parent=d):
                        try:
                            updater.install(path, kind)
                        except Exception as e:
                            messagebox.showerror("更新", str(e), parent=d)
                        else:
                            self._close()
                            return
                elif msg[0] in ("done", "error"):
                    self.running = False
                    self.gen_btn.configure(text="画像を作成")
                    if msg[0] == "done":
                        _, n, total, d = msg
                        self.status.configure(text=f"{n} / {total} 枚を作成しました：{d}"
                                              + ("（中止しました）" if n < total else ""))
                    else:
                        self.status.configure(text="エラーで止まりました")
                        messagebox.showerror("エラー", msg[1], parent=self)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    # ------------------------------------------------------------ 設定ファイル
    def _save_settings(self, p=None):
        try:
            p = p or self.get_params()
            with open(SETTINGS, "w", encoding="utf-8") as f:
                json.dump(p, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _save_preset(self):
        try:
            p = self.get_params()
        except Exception as e:
            messagebox.showerror("設定エラー", str(e), parent=self)
            return
        f = filedialog.asksaveasfilename(parent=self, initialdir=APP_DIR, defaultextension=".json",
                                         filetypes=[("設定ファイル", "*.json")])
        if f:
            with open(f, "w", encoding="utf-8") as fp:
                json.dump(p, fp, ensure_ascii=False, indent=2)

    def _load_preset(self):
        f = filedialog.askopenfilename(parent=self, initialdir=APP_DIR, filetypes=[("設定ファイル", "*.json")])
        if f:
            p = dict(core.DEFAULTS)
            with open(f, encoding="utf-8") as fp:
                p.update(json.load(fp))
            self.set_params(p)

    def _close(self):
        self._save_settings()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
