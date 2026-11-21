"""기안 학습기 실행: 서버를 이 PC 전용 주소(127.0.0.1)로 켜고 데스크톱 창(pywebview)으로 연다.

- 기본: 데스크톱 앱 창(Edge WebView2)으로 실행. 창을 닫으면 서버도 함께 종료된다.
- WebView2가 없는 구형 PC이거나 --browser 인수를 주면 자동으로 웹 브라우저로 열린다.
- --no-browser: 창·브라우저 없이 뒤에서 서버만 실행(자동 실행·CI 시험용).
"""
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

HOST, PORT = "127.0.0.1", int(os.environ.get("GIAN_PORT", "8765"))  # 시험할 때는 다른 포트로
URL = f"http://{HOST}:{PORT}/"


def already_running() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def wait_server(timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if already_running():
            return True
        time.sleep(0.1)
    return False


def open_desktop_window() -> bool:
    """pywebview 데스크톱 창으로 연다. 실패하면 False(브라우저 폴백)."""
    try:
        import webview  # noqa: PLC0415

        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        webview.create_window(
            "기안 학습기",
            URL,
            width=1280,
            height=840,
            min_size=(900, 620),
        )
        webview.start(gui="edgechromium")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"데스크톱 창을 열지 못해 브라우저로 전환합니다: {e}")
        return False


def _setup_logging() -> None:
    if sys.stdout is None or sys.stderr is None:  # pythonw(창 없이 실행)일 때 로그를 파일로
        log_dir = Path(os.environ.get("GIAN_DATA_DIR") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "기안학습기")
        log_dir.mkdir(parents=True, exist_ok=True)
        log = log_dir / "app.log"
        try:  # 2MB가 넘으면 app.log.1로 넘기고 새로 쓴다 (계속 커지지 않게)
            if log.exists() and log.stat().st_size > 2 * 1024 * 1024:
                os.replace(log, log_dir / "app.log.1")
        except OSError:
            pass
        sys.stdout = sys.stderr = open(log, "a", encoding="utf-8", buffering=1)
    for stream in (sys.stdout, sys.stderr):  # 영어 Windows 등에서 한글 출력 때문에 멈추지 않게
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


if __name__ == "__main__":
    _setup_logging()
    no_browser = "--no-browser" in sys.argv
    force_browser = "--browser" in sys.argv

    if already_running():
        print("이미 실행 중입니다. 화면을 엽니다.")
        if no_browser:
            sys.exit(0)
        if force_browser or not open_desktop_window():
            webbrowser.open(URL)
        sys.exit(0)

    import uvicorn

    from app.main import app  # exe(PyInstaller)에서도 동작하도록 직접 가져오기

    if no_browser or force_browser:
        if not no_browser:
            threading.Timer(1.5, lambda: webbrowser.open(URL)).start()
        print(f"기안 학습기: {URL}  (이 창을 닫으면 앱이 꺼집니다)")
        uvicorn.run(app, host=HOST, port=PORT, log_level="warning", log_config=None)
        sys.exit(0)

    # 기본 모드: 서버를 백그라운드 스레드에서 켜고 데스크톱 창(pywebview) 실행
    class _BgServer(uvicorn.Server):
        def install_signal_handlers(self) -> None:
            pass  # 백그라운드 스레드에서는 시그널 등록 생략

    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning", log_config=None)
    server = _BgServer(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    if not wait_server():
        print("서버 시작에 실패했습니다.")
        sys.exit(1)

    print(f"기안 학습기: {URL}")
    if open_desktop_window():
        # 창 X 버튼을 닫으면 서버도 깔끔하게 종료
        server.should_exit = True
        t.join(timeout=3)
    else:
        # WebView2 미지원 PC: 브라우저로 자동 폴백해 계속 실행
        webbrowser.open(URL)
        try:
            t.join()
        except KeyboardInterrupt:
            server.should_exit = True
            t.join(timeout=3)
