"""Windows용 배포 zip 만들기 (PyInstaller, Python 설치 없이 실행되는 exe).

사용: python tools/build_exe.py [--out 폴더]
결과: <out>/gian-learner-v<버전>-windows.zip  (안에 「기안학습기」 폴더: 기안학습기.exe + 사용안내.txt)
"""
from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.version import __version__  # noqa: E402

APP_NAME = "기안학습기"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist"))
    a = ap.parse_args()
    out = Path(a.out).resolve()
    work = out / "_build"
    shutil.rmtree(work, ignore_errors=True)

    import PyInstaller.__main__ as pyi

    sep = ";"  # Windows
    pyi.run([
        str(ROOT / "run.py"),
        "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", APP_NAME,
        "--distpath", str(work / "dist"),
        "--workpath", str(work / "work"),
        "--specpath", str(work),
        "--add-data", f"{ROOT / 'app' / 'static'}{sep}app/static",
        "--add-data", f"{ROOT / 'packs'}{sep}packs",
        "--collect-submodules", "uvicorn",
        "--hidden-import", "multipart",
        "--hidden-import", "python_multipart",
        "--paths", str(ROOT),
        "--exclude-module", "numpy", "--exclude-module", "PIL", "--exclude-module", "tkinter",
    ])

    app_dir = work / "dist" / APP_NAME
    shutil.copy(ROOT / "docs" / "사용안내.txt", app_dir / "사용안내.txt")

    zip_path = out / f"gian-learner-v{__version__}-windows.zip"
    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(app_dir.rglob("*")):
            if f.is_file():
                z.write(f, Path(APP_NAME) / f.relative_to(app_dir))
    print(f"만듦: {zip_path} ({zip_path.stat().st_size // (1024 * 1024)} MB)")
    print(f"exe: {app_dir / (APP_NAME + '.exe')}")


if __name__ == "__main__":
    main()
