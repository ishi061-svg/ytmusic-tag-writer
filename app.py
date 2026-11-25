"""YouTube Music タグ書き込みアプリ（画面のある版）。

使い方:
  1. YouTube Music のアルバムページの URL を貼る
  2. MP3 が入ったフォルダを選ぶ
  3. 「取得して照合」→ 一覧で「今 → 書き込む内容」を確認（行をダブルクリックで曲を選び直せる）
  4. 「書き込む」
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tkinterdnd2 import DND_FILES, DND_TEXT, TkinterDnD  # ドラッグ＆ドロップを受け取るための追加の部品

import check_images
import core

SKIP = "（書き込まない）"

# ---- 色と文字（白基調＋赤。アイコンの赤とそろえる） ----
RED = "#E2202C"
RED_DARK = "#B8141F"
RED_LIGHT = "#FDE8EA"
BG = "#F5F5F7"        # 画面の地の色
CARD = "#FFFFFF"      # カード（白い箱）の色
BORDER = "#E3E3E8"
TEXT = "#1D1D1F"
SUB = "#6E6E73"       # 補足の文字
YELLOW = "#FFF4D6"    # 並び順で当てはめた行
FONT = "Yu Gothic UI"

# exe にしたときは、同梱したファイルが一時フォルダ（_MEIPASS）に展開される
HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
ICON = HERE / "icon.ico"

# チェックの状態を覚えておく場所（C:\Users\<名前>\AppData\Roaming\ytmusic-tag-writer）
SETTINGS = Path(os.environ.get("APPDATA", Path.home())) / "ytmusic-tag-writer" / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # 保存できなくても、アプリはそのまま使える

try:
    # タスクバーに Python ではなく、このアプリのアイコンを出すための名札
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ishi.ytmusic-tag-writer")
except Exception:
    pass


class App(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("YouTube Music タグ書き込み")
        self.geometry("1560x780")
        self.minsize(1100, 560)
        self.configure(bg=BG)
        if ICON.exists():
            self.iconbitmap(default=str(ICON))  # default= で確認画面などにも同じアイコン
        self.album: core.Album | None = None
        self.rows: list[core.FileRow] = []
        self.setup_style()

        # ---- 上の帯：アイコン＋題名 ----
        head = ttk.Frame(self, style="Card.TFrame", padding=(20, 14))
        head.pack(fill="x")
        png = HERE / "icon.png"
        if png.exists():
            self.logo = tk.PhotoImage(file=str(png)).subsample(11)  # 512px → 約46px
            ttk.Label(head, image=self.logo, style="Card.TLabel").pack(side="left", padx=(0, 14))
        titles = ttk.Frame(head, style="Card.TFrame")
        titles.pack(side="left")
        ttk.Label(titles, text="YouTube Music タグ書き込み", style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text="アルバムの URL から、MP3 に曲の情報とジャケットをまとめて書き込みます",
                  style="Sub.TLabel").pack(anchor="w")
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        body = ttk.Frame(self, padding=(20, 16, 20, 12))
        body.pack(fill="both", expand=True)

        # ---- カード1：入れるもの ----
        c1 = self.card(body, "1", "アルバムとフォルダ")
        c1.columnconfigure(1, weight=1)
        ttk.Label(c1, text="アルバムの URL", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        self.url = tk.StringVar()
        ttk.Entry(c1, textvariable=self.url).grid(row=0, column=1, sticky="we", padx=10, ipady=4)
        lang_box = ttk.Frame(c1, style="Card.TFrame")
        lang_box.grid(row=0, column=2, sticky="e")
        ttk.Label(lang_box, text="言語", style="Field.TLabel").pack(side="left", padx=(0, 6))
        self.lang = tk.StringVar(value="日本語")
        ttk.Combobox(lang_box, textvariable=self.lang, values=["日本語", "英語"], width=7,
                     state="readonly").pack(side="left", ipady=3)

        ttk.Label(c1, text="MP3 のフォルダ", style="Field.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        self.folder = tk.StringVar()
        ttk.Entry(c1, textvariable=self.folder).grid(row=1, column=1, sticky="we", padx=10, ipady=4)
        ttk.Button(c1, text="フォルダを選ぶ…", style="Ghost.TButton",
                   command=self.pick_folder).grid(row=1, column=2, sticky="we")
        ttk.Label(c1, text="フォルダや MP3、ブラウザの URL は、この画面にドラッグ＆ドロップしても入ります",
                  style="Hint.TLabel").grid(row=2, column=1, columnspan=2, sticky="w", padx=10, pady=(2, 0))

        # ---- カード2：書き込む内容と実行ボタン ----
        c2 = self.card(body, "2", "書き込む内容")
        saved = load_settings()
        self.title_on = tk.BooleanVar(value=saved.get("write_title", False))
        self.embed = tk.BooleanVar(value=saved.get("embed_cover", True))
        self.replace = tk.BooleanVar(value=saved.get("replace_cover", False))
        self.backup = tk.BooleanVar(value=saved.get("backup", True))
        checks = ttk.Frame(c2, style="Card.TFrame")
        checks.pack(side="left", fill="x", expand=True)
        ttk.Label(checks, text="いつも書き込む：アルバム名・アーティスト・アルバムアーティスト・トラック番号",
                  style="Hint.TLabel").pack(anchor="w", pady=(0, 6))
        row = ttk.Frame(checks, style="Card.TFrame")
        row.pack(anchor="w")
        for text, var in (("曲名も書き込む", self.title_on),
                          ("ジャケットを埋め込む", self.embed),
                          ("すでに入っているジャケットも置き換える", self.replace),
                          ("書き込む前にバックアップを作る", self.backup)):
            ttk.Checkbutton(row, text=" " + text, variable=var, command=self.on_check).pack(side="left", padx=(0, 24))

        actions = ttk.Frame(c2, style="Card.TFrame")
        actions.pack(side="right")
        self.fetch_btn = ttk.Button(actions, text="① 取得して照合", style="Ghost.TButton", command=self.fetch)
        self.fetch_btn.pack(side="left", padx=(0, 10), ipadx=6)
        self.write_btn = ttk.Button(actions, text="② 書き込む", style="Accent.TButton",
                                    command=self.write, state="disabled")
        self.write_btn.pack(side="left", ipadx=10)

        # ---- お知らせの帯 ----
        self.info = tk.StringVar(value="URL とフォルダを入れて「① 取得して照合」を押してください。")
        ttk.Label(body, textvariable=self.info, style="Info.TLabel", padding=(14, 9)).pack(fill="x", pady=(0, 10))

        # ---- 一覧 ----
        cols = ("file", "how", "song", "title", "album", "artist", "aartist", "track", "cover")
        heads = ("ファイル名", "照合", "対応する曲（YouTube Music）", "曲名 今 → 新", "アルバム名 今 → 新",
                 "アーティスト 今 → 新", "アルバムアーティスト 今 → 新", "トラック番号 今 → 新",
                 "ジャケット")
        widths = (160, 45, 170, 210, 180, 220, 200, 100, 100)

        # 下の説明は、一覧より先に「下側」に置く（一覧が伸びても隠れないように）
        legend = ttk.Frame(body)
        legend.pack(side="bottom", fill="x", pady=(8, 0))
        tk.Label(legend, bg=YELLOW, width=2, relief="flat").pack(side="left", padx=(0, 6))
        ttk.Label(legend, text="曲名で見つからず、並び順で当てはめた行。違っていたら行をダブルクリックして選び直せます",
                  style="Legend.TLabel").pack(side="left")

        frame = tk.Frame(body, bg=BORDER, padx=1, pady=1)  # 1px の枠線
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=cols, show="headings")
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h, anchor="w")
            self.tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("even", background=CARD)
        self.tree.tag_configure("odd", background="#FAFAFB")
        self.tree.tag_configure("order", background=YELLOW)
        self.tree.tag_configure("none", foreground="#A1A1A6")
        self.tree.bind("<Double-1>", self.edit_row)

        self.register_drop(self)

    # ---- 見た目の設定 ----
    def setup_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")  # 色を自由に変えられる見た目の土台
        base = (FONT, 10)
        s.configure(".", font=base, background=BG, foreground=TEXT, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, focuscolor=RED)
        s.configure("TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD)
        s.configure("Card.TLabel", background=CARD)
        s.configure("Title.TLabel", background=CARD, font=(FONT, 16, "bold"))
        s.configure("Sub.TLabel", background=CARD, foreground=SUB, font=(FONT, 10))
        s.configure("CardTitle.TLabel", background=CARD, font=(FONT, 11, "bold"))
        s.configure("Step.TLabel", background=RED, foreground="white", font=(FONT, 9, "bold"),
                    anchor="center", width=2)
        s.configure("Field.TLabel", background=CARD, foreground=TEXT)
        s.configure("Hint.TLabel", background=CARD, foreground=SUB, font=(FONT, 9))
        s.configure("Legend.TLabel", background=BG, foreground=SUB, font=(FONT, 9))
        s.configure("Info.TLabel", background=RED_LIGHT, foreground=RED_DARK, font=(FONT, 10, "bold"))

        s.configure("TEntry", fieldbackground=CARD, padding=6)
        s.map("TEntry", bordercolor=[("focus", RED)], lightcolor=[("focus", RED)])
        s.configure("TCombobox", fieldbackground=CARD, padding=4, arrowcolor=SUB)
        s.map("TCombobox", fieldbackground=[("readonly", CARD)], bordercolor=[("focus", RED)],
              selectbackground=[("readonly", CARD)], selectforeground=[("readonly", TEXT)])
        self.option_add("*TCombobox*Listbox.selectBackground", RED)
        self.option_add("*TCombobox*Listbox.font", base)

        # チェックボックスは、赤い四角に白い ✓ の絵に差し替える
        self.check_imgs = {k: tk.PhotoImage(data=getattr(check_images, k))
                           for k in ("CHECK_ON", "CHECK_OFF", "CHECK_HOVER")}
        if "RedCheck.indicator" not in s.element_names():
            s.element_create("RedCheck.indicator", "image", self.check_imgs["CHECK_OFF"],
                             ("selected", self.check_imgs["CHECK_ON"]),
                             ("active", self.check_imgs["CHECK_HOVER"]), sticky="w")
        s.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
            ("RedCheck.indicator", {"side": "left", "sticky": ""}),
            ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
                ("Checkbutton.label", {"sticky": "nswe"})]})]})])
        s.configure("TCheckbutton", background=CARD, padding=(0, 2), focuscolor=CARD)
        s.map("TCheckbutton", background=[("active", CARD)])

        s.configure("Accent.TButton", background=RED, foreground="white", bordercolor=RED,
                    lightcolor=RED, darkcolor=RED, font=(FONT, 11, "bold"), padding=(14, 8))
        s.map("Accent.TButton",
              background=[("disabled", "#E8E8ED"), ("pressed", RED_DARK), ("active", RED_DARK)],
              foreground=[("disabled", "#A1A1A6")],
              bordercolor=[("disabled", "#E8E8ED")], lightcolor=[("disabled", "#E8E8ED")],
              darkcolor=[("disabled", "#E8E8ED")])
        s.configure("Ghost.TButton", background=CARD, foreground=RED, bordercolor=RED,
                    lightcolor=CARD, darkcolor=CARD, font=(FONT, 10, "bold"), padding=(12, 7))
        s.map("Ghost.TButton", background=[("pressed", RED_LIGHT), ("active", RED_LIGHT)],
              foreground=[("disabled", "#A1A1A6")], bordercolor=[("disabled", BORDER)])

        s.configure("Treeview", background=CARD, fieldbackground=CARD, rowheight=30,
                    borderwidth=0, font=base)
        s.map("Treeview", background=[("selected", RED_LIGHT)], foreground=[("selected", TEXT)])
        s.configure("Treeview.Heading", background="#F0F0F3", foreground=SUB,
                    font=(FONT, 9, "bold"), padding=(6, 6), relief="flat", borderwidth=0)
        s.map("Treeview.Heading", background=[("active", "#E8E8ED")])
        s.configure("Vertical.TScrollbar", background="#E0E0E5", troughcolor=CARD,
                    bordercolor=CARD, arrowcolor=SUB, gripcount=0)

    def card(self, parent, step, title):
        """番号と見出しの付いた白い箱を作り、中身を入れる枠を返す。"""
        outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        outer.pack(fill="x", pady=(0, 12))
        box = ttk.Frame(outer, style="Card.TFrame", padding=(18, 12, 18, 14))
        box.pack(fill="x")
        top = ttk.Frame(box, style="Card.TFrame")
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text=step, style="Step.TLabel").pack(side="left", padx=(0, 8), ipady=1)
        ttk.Label(top, text=title, style="CardTitle.TLabel").pack(side="left")
        inner = ttk.Frame(box, style="Card.TFrame")
        inner.pack(fill="x")
        return inner

    def on_check(self):
        """チェックを変えたら、すぐ覚えて、一覧も描き直す。"""
        save_settings({
            "backup": self.backup.get(),
            "write_title": self.title_on.get(),
            "embed_cover": self.embed.get(),
            "replace_cover": self.replace.get(),
        })
        self.refresh()

    # ---- ドラッグ＆ドロップ ----
    def register_drop(self, widget):
        """画面のどこに落としても受け取れるように、すべての部品に登録する。"""
        widget.drop_target_register(DND_FILES, DND_TEXT)
        widget.dnd_bind("<<Drop>>", self.on_drop)
        for child in widget.winfo_children():
            self.register_drop(child)

    def on_drop(self, event):
        """フォルダや MP3 → フォルダ欄へ。ブラウザから URL → URL 欄へ。"""
        data = (event.data or "").strip()
        if data.startswith("http"):
            self.url.set(data.split()[0])
            self.info.set("URL を入れました。")
            return
        # 空白を含む名前は { } で囲まれて届くので、splitlist で分ける
        paths = [Path(p) for p in self.tk.splitlist(data)]
        for p in paths:
            if p.is_dir():
                self.folder.set(str(p))
                break
            if p.suffix.lower() == ".mp3" and p.is_file():
                self.folder.set(str(p.parent))  # MP3 を落としたら、それが入っているフォルダにする
                break
        else:
            self.info.set("フォルダか MP3 を落としてください。")
            return
        self.info.set(f"フォルダを入れました：{self.folder.get()}")

    # ------------------------------------------------------------
    def pick_folder(self):
        d = filedialog.askdirectory(title="MP3 が入ったフォルダを選ぶ")
        if d:
            self.folder.set(d)

    def fetch(self):
        url, folder = self.url.get().strip(), Path(self.folder.get().strip())
        if not url:
            messagebox.showwarning("URL がありません", "YouTube Music のアルバムページの URL を貼ってください。")
            return
        if not folder.is_dir():
            messagebox.showwarning("フォルダがありません", "MP3 が入ったフォルダを選んでください。")
            return
        lang = "ja" if self.lang.get() == "日本語" else "en"
        self.fetch_btn.configure(state="disabled")
        self.write_btn.configure(state="disabled")
        self.info.set("YouTube Music から情報を取得しています…")

        def work():
            try:
                album = core.fetch_album(url, lang)
                rows = core.read_folder(folder)
                core.match(rows, album)
                self.after(0, self.show, album, rows)
            except Exception as e:
                self.after(0, self.fail, e)

        threading.Thread(target=work, daemon=True).start()

    def fail(self, e):
        self.fetch_btn.configure(state="normal")
        self.info.set("取得できませんでした。")
        messagebox.showerror("エラー", str(e))

    def show(self, album, rows):
        self.album, self.rows = album, rows
        self.fetch_btn.configure(state="normal")
        self.refresh()
        if not rows:
            self.info.set("このフォルダに MP3 がありません。")
            return
        n_title = sum(r.how == "曲名" for r in rows)
        n_order = sum(r.how == "順番" for r in rows)
        self.info.set(f"アルバム「{album.title}」／ {album.album_artist} ／ 全{len(album.tracks)}曲。"
                      f"MP3 {len(rows)}個：曲名で対応 {n_title}、並び順で対応 {n_order}。"
                      + ("" if album.cover else "（ジャケット画像は取得できませんでした）"))
        self.write_btn.configure(state="normal")

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        if not self.album:
            return
        aa = self.album.album_artist
        for i, r in enumerate(self.rows):
            now = "あり" if r.has_cover else "なし"
            if r.track:
                song = f"{r.track.number}. {r.track.title}"
                act = core.cover_action(r, self.album, self.embed.get(), self.replace.get())
                cur_t = r.cur_title or "（空）"
                title = f"{cur_t} → {r.track.title}" if self.title_on.get() else f"{cur_t}（そのまま）"
                vals = (r.path.name, r.how, song, title,
                        f"{r.cur_album or '（空）'} → {self.album.title}",
                        f"{r.cur_artist or '（空）'} → {r.track.artist}",
                        f"{r.cur_album_artist or '（空）'} → {aa}",
                        f"{r.cur_track or '（空）'} → {r.new_track_text}",
                        f"{now} → {act}")
            else:
                vals = (r.path.name, r.how, SKIP, "", "", "", "", "", f"{now} → そのまま")
            tags = ["odd" if i % 2 else "even"]  # 1行おきに薄い色で見やすく
            if r.how == "順番":
                tags.append("order")
            elif not r.track:
                tags.append("none")
            self.tree.insert("", "end", iid=str(i), values=vals, tags=tags)

    def edit_row(self, _event):
        sel = self.tree.selection()
        if not sel or not self.album:
            return
        r = self.rows[int(sel[0])]
        choices = [SKIP] + [f"{t.number}. {t.title}" for t in self.album.tracks]

        win = tk.Toplevel(self)
        win.title("曲を選び直す")
        win.configure(bg=CARD)
        win.transient(self)
        win.grab_set()
        ttk.Label(win, text="対応する曲を選び直す", style="CardTitle.TLabel",
                  padding=(16, 14, 16, 2)).pack(anchor="w")
        ttk.Label(win, text=f"ファイル：{r.path.name}", style="Hint.TLabel",
                  padding=(16, 0, 16, 10)).pack(anchor="w")
        var = tk.StringVar(value=f"{r.track.number}. {r.track.title}" if r.track else SKIP)
        ttk.Combobox(win, textvariable=var, values=choices, width=60, state="readonly").pack(padx=16, ipady=3)

        def ok():
            v = var.get()
            if v == SKIP:
                r.track, r.how = None, "なし"
            else:
                r.track, r.how = self.album.tracks[choices.index(v) - 1], "手動"
            core.finalize(self.rows, self.album)
            self.refresh()
            win.destroy()

        ttk.Button(win, text="決定", style="Accent.TButton", command=ok).pack(pady=14)

    def write(self):
        targets = [r for r in self.rows if r.track]
        if not targets:
            messagebox.showinfo("対象なし", "書き込む行がありません。")
            return
        nums = [r.track.number for r in targets]
        dup = len(nums) != len(set(nums))
        what = ("曲名・" if self.title_on.get() else "") + "アルバム名・アーティスト・アルバムアーティスト・トラック番号"
        msg = f"{len(targets)}個の MP3 に、{what}を書き込みます。"
        if not self.backup.get():
            msg += "\n\n※ バックアップを作らない設定です。元に戻せません。"
        n_cover = sum(core.cover_action(r, self.album, self.embed.get(), self.replace.get()) != "そのまま"
                      for r in targets)
        if n_cover:
            msg += f"\nジャケット画像は {n_cover}個に入れます（置き換えを含む）。"
        if dup:
            msg += "\n\n※ 同じ曲に対応している行が複数あります。"
        msg += "\n\nよろしいですか？"
        if not messagebox.askyesno("書き込みの確認", msg):
            return
        try:
            dest = core.backup(self.rows) if self.backup.get() else None
            n = core.write_tags(self.rows, self.album, self.embed.get(), self.replace.get(),
                                self.title_on.get())
        except Exception as e:
            messagebox.showerror("エラー", f"書き込みに失敗しました。\n{e}")
            return
        done = f"{n}個のファイルに書き込みました。"
        if dest:
            done += f"\n\nバックアップ：{dest}"
        messagebox.showinfo("完了", done)
        # 書き込んだ後の状態を読み直して表示
        rows = core.read_folder(Path(self.folder.get()))
        core.match(rows, self.album)
        self.show(self.album, rows)


if __name__ == "__main__":
    App().mainloop()
