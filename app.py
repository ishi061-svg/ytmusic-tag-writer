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

import core

SKIP = "（書き込まない）"

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
        self.geometry("1450x600")
        if ICON.exists():
            self.iconbitmap(default=str(ICON))  # default= で確認画面などにも同じアイコン
        self.album: core.Album | None = None
        self.rows: list[core.FileRow] = []

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="アルバムの URL").grid(row=0, column=0, sticky="w")
        self.url = tk.StringVar()
        ttk.Entry(top, textvariable=self.url, width=90).grid(row=0, column=1, columnspan=2, sticky="we", padx=4)

        ttk.Label(top, text="言語").grid(row=0, column=3, sticky="e")
        self.lang = tk.StringVar(value="日本語")
        ttk.Combobox(top, textvariable=self.lang, values=["日本語", "英語"], width=6,
                     state="readonly").grid(row=0, column=4, padx=4)

        ttk.Label(top, text="MP3 のフォルダ").grid(row=1, column=0, sticky="w", pady=4)
        self.folder = tk.StringVar()
        ttk.Entry(top, textvariable=self.folder, width=80).grid(row=1, column=1, sticky="we", padx=4)
        ttk.Button(top, text="選ぶ…", command=self.pick_folder).grid(row=1, column=2, sticky="w")
        top.columnconfigure(1, weight=1)

        btns = ttk.Frame(self, padding=(8, 0))
        btns.pack(fill="x")
        self.fetch_btn = ttk.Button(btns, text="① 取得して照合", command=self.fetch)
        self.fetch_btn.pack(side="left")
        self.write_btn = ttk.Button(btns, text="② 書き込む", command=self.write, state="disabled")
        self.write_btn.pack(side="left", padx=8)
        saved = load_settings()
        self.backup = tk.BooleanVar(value=saved.get("backup", True))
        ttk.Checkbutton(btns, text="書き込む前にバックアップを作る", variable=self.backup,
                        command=self.on_check).pack(side="left", padx=8)
        self.title_on = tk.BooleanVar(value=saved.get("write_title", False))
        ttk.Checkbutton(btns, text="曲名も書き込む", variable=self.title_on,
                        command=self.on_check).pack(side="left", padx=8)
        self.embed = tk.BooleanVar(value=saved.get("embed_cover", True))
        ttk.Checkbutton(btns, text="ジャケットを埋め込む", variable=self.embed,
                        command=self.on_check).pack(side="left", padx=8)
        self.replace = tk.BooleanVar(value=saved.get("replace_cover", False))
        ttk.Checkbutton(btns, text="すでに入っているジャケットも置き換える", variable=self.replace,
                        command=self.on_check).pack(side="left", padx=8)

        self.info = tk.StringVar(value="URL とフォルダを入れて「① 取得して照合」を押してください。"
                                       "（フォルダや MP3、ブラウザの URL は画面に落としても入ります）")
        ttk.Label(self, textvariable=self.info, padding=8).pack(fill="x")

        cols = ("file", "how", "song", "title", "album", "artist", "aartist", "track", "cover")
        heads = ("ファイル名", "照合", "対応する曲（YouTube Music）", "曲名 今 → 新", "アルバム名 今 → 新",
                 "アーティスト 今 → 新", "アルバムアーティスト 今 → 新", "トラック番号 今 → 新",
                 "ジャケット")
        widths = (170, 45, 170, 200, 150, 170, 170, 95, 95)
        frame = ttk.Frame(self, padding=(8, 0, 8, 8))
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=cols, show="headings")
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("order", background="#fff4d6")
        self.tree.tag_configure("none", foreground="#999999")
        self.tree.bind("<Double-1>", self.edit_row)

        ttk.Label(self, padding=(8, 0, 8, 8),
                  text="黄色の行＝曲名で見つからず、並び順で当てはめた行です。違っていたら行をダブルクリックして選び直してください。"
                  ).pack(fill="x")

        self.register_drop(self)

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
            tag = "order" if r.how == "順番" else ("none" if not r.track else "")
            self.tree.insert("", "end", iid=str(i), values=vals, tags=(tag,))

    def edit_row(self, _event):
        sel = self.tree.selection()
        if not sel or not self.album:
            return
        r = self.rows[int(sel[0])]
        choices = [SKIP] + [f"{t.number}. {t.title}" for t in self.album.tracks]

        win = tk.Toplevel(self)
        win.title("曲を選び直す")
        win.transient(self)
        win.grab_set()
        ttk.Label(win, text=f"ファイル：{r.path.name}", padding=8).pack(anchor="w")
        var = tk.StringVar(value=f"{r.track.number}. {r.track.title}" if r.track else SKIP)
        ttk.Combobox(win, textvariable=var, values=choices, width=60, state="readonly").pack(padx=8)

        def ok():
            v = var.get()
            if v == SKIP:
                r.track, r.how = None, "なし"
            else:
                r.track, r.how = self.album.tracks[choices.index(v) - 1], "手動"
            core.finalize(self.rows, self.album)
            self.refresh()
            win.destroy()

        ttk.Button(win, text="決定", command=ok).pack(pady=8)

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
