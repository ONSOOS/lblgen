"""GitHub Releases を使ったオンラインアップデート

リリースに次のファイルを添付しておく（build.py が作る）
  SujiMaker-<版>-setup.exe  … インストーラ（インストール版の更新に使う）
  SujiMaker-<版>.exe        … 単体exe（インストールせずに使っている場合の更新に使う）
  SHA256SUMS.txt            … 上記のチェックサム。一致しないファイルは使わない
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

from app_info import APP_ID, GITHUB_REPO, VERSION

UA = f"{APP_ID}-updater/{VERSION}"


def parse_version(s):
    nums = [int(x) for x in re.findall(r"\d+", s)[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def is_installed():
    """インストーラで入れた版か（インストール先に unins000.exe がある）"""
    return getattr(sys, "frozen", False) and os.path.exists(
        os.path.join(os.path.dirname(sys.executable), "unins000.exe"))


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def check():
    """最新リリースを調べる。{newer, version, notes, page, asset, asset_url, sums_url, kind} を返す"""
    if not GITHUB_REPO:
        raise RuntimeError("更新の確認先（GitHub のリポジトリ）がまだ設定されていません。")
    with _get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest") as r:
        data = json.load(r)
    tag = data.get("tag_name", "")
    assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
    setup = next((n for n in assets if n.lower().endswith("-setup.exe")), None)
    single = next((n for n in assets if n.lower().endswith(".exe") and n != setup), None)
    if is_installed() or not getattr(sys, "frozen", False):
        asset, kind = (setup, "setup") if setup else (single, "exe")
    else:
        asset, kind = (single, "exe") if single else (setup, "setup")
    return {
        "newer": parse_version(tag) > parse_version(VERSION),
        "version": tag.lstrip("vV"),
        "notes": (data.get("body") or "").strip(),
        "page": data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases"),
        "asset": asset,
        "asset_url": assets.get(asset),
        "sums_url": assets.get("SHA256SUMS.txt"),
        "kind": kind,
    }


def download(info, progress=None, cancel=None):
    """更新ファイルをダウンロードし、SHA256 を確かめてパスを返す"""
    if not info["asset_url"]:
        raise RuntimeError("このリリースには更新用のファイルが添付されていません。")
    if not info["sums_url"]:
        raise RuntimeError("このリリースには SHA256SUMS.txt が無いため、安全のため更新を中止しました。")
    with _get(info["sums_url"]) as r:
        sums = {}
        for line in r.read().decode("utf-8", "replace").splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                sums[parts[-1].lstrip("*")] = parts[0].lower()
    expected = sums.get(info["asset"])
    if not expected:
        raise RuntimeError(f"SHA256SUMS.txt に {info['asset']} がありません。")

    path = os.path.join(tempfile.gettempdir(), info["asset"])
    h = hashlib.sha256()
    with _get(info["asset_url"], timeout=60) as r, open(path, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancel and cancel():
                f.close()
                os.remove(path)
                raise RuntimeError("中止しました。")
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if h.hexdigest().lower() != expected:
        os.remove(path)
        raise RuntimeError("ダウンロードしたファイルのチェックサムが一致しません。更新を中止しました。")
    return path


def install(path, kind):
    """更新を始める。呼んだ側はこのあとすぐアプリを終了すること"""
    if kind == "setup":
        # インストーラを画面付き・質問なしで実行（終わるとアプリが再起動する）
        subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                         close_fds=True)
        return
    if not getattr(sys, "frozen", False):
        raise RuntimeError("exe で起動していないため、自動で入れ替えられません。")
    # 単体exe：アプリの終了を待って exe を差し替え、起動し直すバッチを動かす
    target = sys.executable
    bat = os.path.join(tempfile.gettempdir(), f"{APP_ID}_update.bat")
    with open(bat, "w", encoding="cp932", errors="replace") as f:
        f.write(f"""@echo off
chcp 932 >nul
:wait
tasklist /fi "PID eq {os.getpid()}" | find "{os.getpid()}" >nul && (timeout /t 1 /nobreak >nul & goto wait)
copy /y "{path}" "{target}" >nul || (echo 更新できませんでした & pause & exit /b 1)
del "{path}"
start "" "{target}"
del "%~f0"
""")
    subprocess.Popen(["cmd", "/c", bat], creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
