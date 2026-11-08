"""기안 학습기 실행: 서버를 이 PC 전용 주소(127.0.0.1)로 켜고 브라우저를 연다."""
import socket
import sys
import threading
import webbrowser

import os

HOST, PORT = "127.0.0.1", int(os.environ.get("GIAN_PORT", "8765"))  # 시험할 때는 다른 포트로
URL = f"http://{HOST}:{PORT}/"


def already_running() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


if __name__ == "__main__":
    if sys.stdout is None or sys.stderr is None:  # pythonw(창 없이 실행)일 때 로그를 파일로
        import os
        from pathlib import Path
        log_dir = Path(os.environ.get("GIAN_DATA_DIR") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "기안학습기")
        log_dir.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(log_dir / "app.log", "a", encoding="utf-8", buffering=1)
    for stream in (sys.stdout, sys.stderr):  # 영어 Windows 등에서 한글 출력 때문에 멈추지 않게
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if already_running():
        print("이미 실행 중입니다. 브라우저를 엽니다.")
        webbrowser.open(URL)
        sys.exit(0)
    import uvicorn

    from app.main import app  # exe(PyInstaller)에서도 동작하도록 직접 가져오기

    if "--no-browser" not in sys.argv:
        threading.Timer(1.5, lambda: webbrowser.open(URL)).start()
    print(f"기안 학습기: {URL}  (이 창을 닫으면 앱이 꺼집니다)")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning", log_config=None)
