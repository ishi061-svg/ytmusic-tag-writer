"""YouTube Music のアルバム情報を取ってきて、MP3 のタグに書き込む中身の部分。

書き込むのは次のものだけ（ほかのタグには触らない）:
  - アルバム名          (ID3 の TALB)
  - アーティスト        (ID3 の TPE1)
  - アルバムアーティスト (ID3 の TPE2)
  - トラック番号        (ID3 の TRCK、「3/12」の形)
  - ジャケット画像      (ID3 の APIC、選んだときだけ)
"""
from __future__ import annotations

import difflib
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TPE1, TPE2, TRCK


# ---------------------------------------------------------------- データの形
@dataclass
class Track:
    number: int
    title: str
    artist: str
    alt_title: str = ""  # もう一つの言語での曲名（照合用）


@dataclass
class Album:
    title: str
    album_artist: str
    tracks: list[Track]
    cover: bytes = b""          # ジャケット画像の中身
    cover_mime: str = ""        # image/jpeg など


@dataclass
class FileRow:
    path: Path
    title: str           # 照合に使った曲名（タグ、無ければファイル名）
    cur_artist: str
    cur_album_artist: str
    cur_track: str
    cur_album: str = ""
    has_cover: bool = False
    track: Track | None = None
    how: str = ""        # 「曲名」「順番」「手動」「なし」
    score: float = 0.0
    new_track_text: str = field(default="")


# ---------------------------------------------------------------- URL → ID
def url_to_browse_id(yt, url: str) -> str:
    """アルバムページの URL から、YouTube Music 内部のアルバム ID を取り出す。"""
    url = url.strip()
    m = re.search(r"(MPREb_[A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    qs = parse_qs(urlparse(url).query)
    lst = (qs.get("list") or [""])[0]
    if not lst:
        m = re.search(r"(OLAK5uy_[A-Za-z0-9_-]+)", url)
        lst = m.group(1) if m else ""
    if lst:
        bid = yt.get_album_browse_id(lst)
        if bid:
            return bid
    raise ValueError(
        "アルバムの URL として読めませんでした。\n"
        "YouTube Music でアルバムのページを開き、そのアドレスを貼ってください。\n"
        "例: https://music.youtube.com/playlist?list=OLAK5uy_... または\n"
        "    https://music.youtube.com/browse/MPREb_..."
    )


def _artist_text(artists) -> str:
    return ", ".join(a["name"] for a in (artists or []) if a.get("name"))


def fetch_album(url: str, lang: str = "ja") -> Album:
    """アルバムの情報を取ってくる（ログイン不要・読むだけ）。"""
    from ytmusicapi import YTMusic

    yt = YTMusic(language=lang, location="JP")
    bid = url_to_browse_id(yt, url)
    data = yt.get_album(bid)

    # 照合しやすくするため、もう一つの言語の曲名も取っておく
    other = "en" if lang == "ja" else "ja"
    alt = {}
    try:
        data2 = YTMusic(language=other, location="JP").get_album(bid)
        for t in data2.get("tracks", []):
            if t.get("trackNumber"):
                alt[t["trackNumber"]] = t.get("title") or ""
    except Exception:
        pass

    album_artist = _artist_text(data.get("artists"))
    tracks = []
    for i, t in enumerate(data.get("tracks", []), start=1):
        num = t.get("trackNumber") or i
        tracks.append(Track(
            number=num,
            title=t.get("title") or "",
            artist=_artist_text(t.get("artists")) or album_artist,
            alt_title=alt.get(num, ""),
        ))
    cover, mime = fetch_cover(data.get("thumbnails") or [])
    return Album(title=data.get("title") or "", album_artist=album_artist, tracks=tracks,
                 cover=cover, cover_mime=mime)


def fetch_cover(thumbnails) -> tuple[bytes, str]:
    """一番大きいジャケット画像を取ってくる。取れなければ空。"""
    import requests

    if not thumbnails:
        return b"", ""
    best = max(thumbnails, key=lambda t: t.get("width", 0))["url"]
    # Google の画像は URL の「=w544-h544」部分で大きさを指定できる
    big = re.sub(r"=w\d+-h\d+", "=w1200-h1200", best)
    for url in (big, best):
        try:
            res = requests.get(url, timeout=20)
            mime = res.headers.get("Content-Type", "").split(";")[0]
            if res.ok and mime.startswith("image/"):
                return res.content, mime
        except Exception:
            pass
    return b"", ""


# ---------------------------------------------------------------- MP3 を読む
def _text(tags, key) -> str:
    if tags is None or key not in tags:
        return ""
    return str(tags[key].text[0]) if tags[key].text else ""


def _title_from_filename(p: Path) -> str:
    # 先頭の「01 」「01. 」「01 - 」などの番号は外す
    return re.sub(r"^\s*\d{1,3}\s*[-_.、．)）]?\s*", "", p.stem)


def read_folder(folder: Path) -> list[FileRow]:
    rows = []
    for p in sorted(folder.glob("*.mp3"), key=lambda x: x.name.lower()):
        try:
            tags = ID3(p)
        except ID3NoHeaderError:
            tags = None
        title = _text(tags, "TIT2") or _title_from_filename(p)
        rows.append(FileRow(
            path=p, title=title,
            cur_artist=_text(tags, "TPE1"),
            cur_album_artist=_text(tags, "TPE2"),
            cur_track=_text(tags, "TRCK"),
            cur_album=_text(tags, "TALB"),
            has_cover=bool(tags and tags.getall("APIC")),
        ))
    return rows


# ---------------------------------------------------------------- 照合
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[\(\[（【].*?[\)\]）】]", "", s)   # かっこ書き（Remaster など）は外す
    s = re.sub(r"[\s\W_]+", "", s)
    return s


def _similar(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


MATCH_THRESHOLD = 0.6


def match(rows: list[FileRow], album: Album) -> None:
    """まず曲名が似ているもの同士を組み合わせ、残りはファイル名の並び順で組み合わせる。"""
    pairs = []
    for ri, r in enumerate(rows):
        for ti, t in enumerate(album.tracks):
            s = max(_similar(r.title, t.title), _similar(r.title, t.alt_title))
            if s >= MATCH_THRESHOLD:
                pairs.append((s, ri, ti))
    pairs.sort(reverse=True)
    used_r, used_t = set(), set()
    for s, ri, ti in pairs:
        if ri in used_r or ti in used_t:
            continue
        rows[ri].track, rows[ri].how, rows[ri].score = album.tracks[ti], "曲名", s
        used_r.add(ri)
        used_t.add(ti)

    rest_t = [t for i, t in enumerate(album.tracks) if i not in used_t]
    for ri, r in enumerate(rows):
        if ri in used_r:
            continue
        if rest_t:
            r.track, r.how, r.score = rest_t.pop(0), "順番", 0.0
        else:
            r.track, r.how = None, "なし"
    finalize(rows, album)


def finalize(rows: list[FileRow], album: Album) -> None:
    total = len(album.tracks)
    for r in rows:
        r.new_track_text = f"{r.track.number}/{total}" if r.track else ""


# ---------------------------------------------------------------- 書き込む
def backup(rows: list[FileRow]) -> Path | None:
    targets = [r for r in rows if r.track]
    if not targets:
        return None
    dest = targets[0].path.parent / f"_backup_{datetime.now():%Y%m%d_%H%M%S}"
    dest.mkdir()
    for r in targets:
        shutil.copy2(r.path, dest / r.path.name)
    return dest


def cover_action(row: FileRow, album: Album, embed: bool, replace: bool) -> str:
    """ジャケットをどうするか：「入れる」「置き換える」「そのまま」。"""
    if not (embed and album.cover and row.track):
        return "そのまま"
    if not row.has_cover:
        return "入れる"
    return "置き換える" if replace else "そのまま"


def write_tags(rows: list[FileRow], album: Album,
               embed_cover: bool = False, replace_cover: bool = False) -> int:
    n = 0
    for r in rows:
        if not r.track:
            continue
        try:
            tags = ID3(r.path)
            ver = 3 if tags.version[1] == 3 else 4  # 元の形式（v2.3/v2.4）を保つ
        except ID3NoHeaderError:
            tags, ver = ID3(), 3
        tags.setall("TPE1", [TPE1(encoding=3, text=[r.track.artist])])
        tags.setall("TPE2", [TPE2(encoding=3, text=[album.album_artist])])
        tags.setall("TRCK", [TRCK(encoding=3, text=[r.new_track_text])])
        if album.title:
            tags.setall("TALB", [TALB(encoding=3, text=[album.title])])
        if cover_action(r, album, embed_cover, replace_cover) != "そのまま":
            # type=3 は「表ジャケット」
            tags.setall("APIC", [APIC(encoding=3, mime=album.cover_mime, type=3,
                                      desc="Cover", data=album.cover)])
        tags.save(r.path, v2_version=ver)
        n += 1
    return n
