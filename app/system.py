"""바탕화면 바로가기·로그인 시 자동 실행(사용자 시작프로그램 폴더 바로가기) 관리.

시스템 설정이나 레지스트리는 건드리지 않고, 사용자 폴더에 .lnk 파일만 만들고 지운다.
"""
from __future__ import annotations

import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
LNK_NAME = "기안 학습기.lnk"
ICON = r"%SystemRoot%\System32\imageres.dll,97"


def _ps(script: str, env: dict | None = None) -> str:
    e = {**os.environ, **(env or {})}
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", env=e, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "PowerShell 실행 실패")
    return r.stdout.strip()


@lru_cache(maxsize=None)
def folder(kind: str) -> Path:
    """kind: Desktop | Startup (OneDrive로 옮겨진 바탕화면도 정확히 찾음)."""
    out = _ps("[Console]::OutputEncoding=[Text.Encoding]::UTF8; [Environment]::GetFolderPath($env:GL_FOLDER)",
              {"GL_FOLDER": kind})
    if not out:
        raise RuntimeError(f"{kind} 폴더를 찾을 수 없습니다.")
    return Path(out)


FROZEN = bool(getattr(sys, "frozen", False))  # exe로 실행 중인지


def launcher(extra: str = "") -> tuple[str, str, str]:
    """(실행 파일, 인수, 작업 폴더)"""
    if FROZEN:
        exe = Path(sys.executable)
        return str(exe), extra, str(exe.parent)
    return pythonw(), f'"{PROJECT / "run.py"}" {extra}'.strip(), str(PROJECT)


def pythonw() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def make_shortcut(path: Path, extra: str = "") -> None:
    target, args, wd = launcher(extra)
    _ps(
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:GL_LNK);"
        "$s.TargetPath=$env:GL_TGT; $s.Arguments=$env:GL_ARGS; $s.WorkingDirectory=$env:GL_WD;"
        "$s.IconLocation=$env:GL_ICO; $s.Description=$env:GL_DESC; $s.Save()",
        {"GL_LNK": str(path), "GL_TGT": target, "GL_ARGS": args, "GL_WD": wd,
         "GL_ICO": target if FROZEN else os.path.expandvars(ICON), "GL_DESC": "기안 학습기"},
    )


def status() -> dict:
    res = {}
    for key, kind in (("desktop", "Desktop"), ("autostart", "Startup")):
        try:
            res[key] = (folder(kind) / LNK_NAME).exists()
        except Exception:  # noqa: BLE001
            res[key] = None
    return res


def create_desktop() -> None:
    make_shortcut(folder("Desktop") / LNK_NAME)


def set_autostart(enable: bool) -> None:
    lnk = folder("Startup") / LNK_NAME
    if enable:
        make_shortcut(lnk, "--no-browser")
    else:
        lnk.unlink(missing_ok=True)
