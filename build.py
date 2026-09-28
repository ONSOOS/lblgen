"""配布用ファイルを作る：python build.py

  release\\<版>\\SujiMaker-<版>.exe         単体exe（インストール不要版）
  release\\<版>\\SujiMaker-<版>-setup.exe   インストーラ（Inno Setup が入っている場合）
  release\\<版>\\SHA256SUMS.txt             オンラインアップデートの確認用

作業用の Python 環境は %LOCALAPPDATA%\\SujiMakerBuild に作る（初回のみ数分かかる）
"""
import glob
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import app_info  # noqa: E402

VER = app_info.VERSION
WORK = os.path.join(os.environ["LOCALAPPDATA"], "SujiMakerBuild")
VENV_PY = os.path.join(WORK, "venv", "Scripts", "python.exe")
OUT = os.path.join(HERE, "release", VER)


def run(*args, **kw):
    print(">", " ".join(str(a) for a in args), flush=True)
    subprocess.run(args, check=True, **kw)


def ensure_venv():
    if not os.path.exists(VENV_PY):
        os.makedirs(WORK, exist_ok=True)
        run(sys.executable, "-m", "venv", os.path.join(WORK, "venv"))
    run(VENV_PY, "-m", "pip", "install", "-q", "--disable-pip-version-check", "pyinstaller", "pillow")


def make_icon():
    path = os.path.join(HERE, "icon.ico")
    if os.path.exists(path):
        return path
    import suji_core as c
    p = dict(c.DEFAULTS, mode="list", items="1", shape="circle", text_height=50, line_width=9, margin=2,
             fill_color="#FFFFFF", bg_transparent=True, text_color="#E60012", frame_color="#E60012")
    img = c.render(c.make_items(p)[0], p, 256 / 1200)
    img.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


def version_file():
    nums = tuple(int(x) for x in (VER.split(".") + ["0"] * 4)[:4])
    path = os.path.join(WORK, "version_info.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}),
  kids=[StringFileInfo([StringTable('041104b0', [
    StringStruct('CompanyName', '{app_info.COMPANY}'),
    StringStruct('FileDescription', '{app_info.APP_NAME}'),
    StringStruct('FileVersion', '{VER}'),
    StringStruct('InternalName', '{app_info.APP_ID}'),
    StringStruct('LegalCopyright', '{app_info.COPYRIGHT}'),
    StringStruct('OriginalFilename', '{app_info.APP_ID}.exe'),
    StringStruct('ProductName', '{app_info.APP_NAME}'),
    StringStruct('ProductVersion', '{VER}')])]),
    VarFileInfo([VarStruct('Translation', [1041, 1200])])])
""")
    return path


def find_iscc():
    for pat in (r"C:\Program Files (x86)\Inno Setup *\ISCC.exe", r"C:\Program Files\Inno Setup *\ISCC.exe",
                os.path.join(os.environ["LOCALAPPDATA"], "Programs", "Inno Setup *", "ISCC.exe")):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return shutil.which("ISCC")


def main():
    ensure_venv()
    icon = make_icon()
    os.makedirs(OUT, exist_ok=True)
    src = os.path.join(WORK, "src")
    shutil.rmtree(src, ignore_errors=True)
    os.makedirs(src)
    for f in ("suji_core.py", "updater.py", "app_info.py", "help_text.py", "shape_lib.py", "icon.ico"):
        shutil.copy(os.path.join(HERE, f), src)
    shutil.copy(os.path.join(HERE, "数字画像メーカー.pyw"), os.path.join(src, "app.pyw"))
    run(VENV_PY, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed", "--name", app_info.APP_ID,
        "--icon", icon, "--version-file", version_file(), "--add-data", f"{icon};.",
        "--paths", src, "--distpath", os.path.join(WORK, "dist"), "--workpath", os.path.join(WORK, "build"),
        "--specpath", os.path.join(WORK, "build"), os.path.join(src, "app.pyw"))
    built = os.path.join(WORK, "dist", f"{app_info.APP_ID}.exe")
    single = os.path.join(OUT, f"{app_info.APP_ID}-{VER}.exe")
    shutil.copy(built, single)

    iscc = find_iscc()
    if iscc:
        run(iscc, f"/DMyAppVersion={VER}", f"/DExePath={built}", f"/O{OUT}", os.path.join(HERE, "installer.iss"))
    else:
        print("\n※ Inno Setup が見つからないため、インストーラは作りませんでした。")

    files = sorted(f for f in os.listdir(OUT) if f.lower().endswith(".exe"))
    with open(os.path.join(OUT, "SHA256SUMS.txt"), "w", encoding="utf-8", newline="\n") as f:
        for name in files:
            with open(os.path.join(OUT, name), "rb") as fp:
                f.write(f"{hashlib.sha256(fp.read()).hexdigest()}  {name}\n")
    print(f"\n完成：{OUT}")
    for name in files + ["SHA256SUMS.txt"]:
        print("  ", name)
    print(f"\nGitHub のリリース（タグ v{VER}）に、上のファイルをすべて添付してください。")


if __name__ == "__main__":
    main()
