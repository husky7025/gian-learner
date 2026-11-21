"""행정업무 AI 실행: 서버를 이 PC 전용 주소(127.0.0.1)로 켜고 데스크톱 창(pywebview)으로 연다.

- 기본: 데스크톱 앱 창(Edge WebView2)으로 실행. 창을 닫으면 서버도 함께 종료된다.
  창을 먼저 띄워 「불러오는 중」을 보여 주고, 그동안 뒤에서 서버를 켠다(기다리는 느낌을 줄이기).
- WebView2가 없는 구형 PC이거나 --browser 인수를 주면 자동으로 웹 브라우저로 열린다.
- --no-browser: 창·브라우저 없이 뒤에서 서버만 실행(자동 실행·CI 시험용).
- --check-deps: 필요한 프로그램이 설치됐는지만 빠르게 확인(실행 bat용). 다 있으면 python 경로, 없으면 MISSING.
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
REQUIRED = ("fastapi", "uvicorn", "lxml", "multipart", "pypdf", "anthropic", "webview")

LOADING_HTML = """<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><style>
html,body{height:100%;margin:0}
body{display:flex;align-items:center;justify-content:center;background:#fff;color:#1d1d1f;
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Inter","Pretendard","Apple SD Gothic Neo","Segoe UI","Malgun Gothic",sans-serif;
  -webkit-font-smoothing:antialiased}
.box{text-align:center}
h1{font-weight:600;letter-spacing:-0.5px;font-size:40px;color:#1d1d1f;margin:0 0 22px}
.dot{display:inline-block;width:9px;height:9px;margin:0 4px;border-radius:50%;background:#0066cc;
  animation:b 1.2s infinite ease-in-out}
.dot:nth-child(2){animation-delay:.15s}.dot:nth-child(3){animation-delay:.3s}
@keyframes b{0%,80%,100%{opacity:.25;transform:scale(.8)}40%{opacity:1;transform:scale(1)}}
p{color:#6e6e73;margin-top:18px;font-size:15px;letter-spacing:-0.2px}
</style></head><body><div class="box"><h1>행정업무 AI</h1>
<div><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>
<p>불러오는 중입니다…</p></div></body></html>"""

FAIL_HTML = """<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"></head>
<body style="background:#fff;color:#1d1d1f;font-family:-apple-system,'Segoe UI','Malgun Gothic',sans-serif;padding:48px;line-height:1.7">
<h2 style="font-weight:600;letter-spacing:-0.4px">앱을 시작하지 못했습니다</h2>
<p>창을 닫고 다시 실행해 주세요. 계속 안 되면 실행 파일을 <b>console</b> 인수로 실행해 오류 내용을 확인해 주세요.</p>
<p style="color:#6e6e73">{detail}</p></body></html>"""


def check_deps() -> None:
    """설치 여부만 본다(불러오지 않음). anthropic처럼 큰 라이브러리를 불러오면 10초 넘게 걸린다."""
    import importlib.util  # noqa: PLC0415
    missing = [m for m in REQUIRED if importlib.util.find_spec(m) is None]
    print("MISSING" if missing else sys.executable)


def already_running() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def wait_server(timeout: float = 30.0, alive=None) -> bool:
    """서버가 응답할 때까지 기다린다. alive()가 False가 되면(서버 스레드가 죽으면) 바로 포기."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if already_running():
            return True
        if alive is not None and not alive():
            return False
        time.sleep(0.1)
    return False


def start_server_thread() -> tuple[threading.Thread, dict]:
    """서버 프로그램을 불러오고(가장 오래 걸림) 켜는 일을 뒤에서 한다. holder에 server·error가 담긴다."""
    holder: dict = {}

    def target():
        try:
            import uvicorn  # noqa: PLC0415

            from app.main import app  # noqa: PLC0415 — exe(PyInstaller)에서도 동작하도록 직접 가져오기

            class _BgServer(uvicorn.Server):
                def install_signal_handlers(self) -> None:
                    pass  # 백그라운드 스레드에서는 시그널 등록 생략

            server = _BgServer(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning", log_config=None))
            holder["server"] = server
            server.run()
        except BaseException as e:  # noqa: BLE001
            holder["error"] = repr(e)
            print(f"서버 오류: {e!r}")

    t = threading.Thread(target=target, daemon=True)
    t.start()
    return t, holder


def open_desktop_window(server_ready=None) -> bool:
    """pywebview 데스크톱 창으로 연다. 실패하면 False(브라우저 폴백).
    server_ready가 있으면 창에 「불러오는 중」을 먼저 보여 주고, 준비되면 앱 화면으로 바꾼다."""
    try:
        import webview  # noqa: PLC0415

        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        kw = {"width": 1280, "height": 840, "min_size": (900, 620), "background_color": "#FFFFFF"}
        if server_ready is None:
            webview.create_window("행정업무 AI", URL, **kw)
            webview.start(gui="edgechromium")
            return True
        win = webview.create_window("행정업무 AI", html=LOADING_HTML, **kw)

        def switch():
            ok, detail = server_ready()
            if ok:
                win.load_url(URL)
            else:
                import html  # noqa: PLC0415
                win.load_html(FAIL_HTML.replace("{detail}", html.escape(detail or "서버가 응답하지 않습니다.")))

        webview.start(switch, gui="edgechromium")
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
    if "--check-deps" in sys.argv:
        check_deps()
        sys.exit(0)
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

    if no_browser or force_browser:
        import uvicorn

        from app.main import app  # exe(PyInstaller)에서도 동작하도록 직접 가져오기

        if not no_browser:
            threading.Timer(1.5, lambda: webbrowser.open(URL)).start()
        print(f"행정업무 AI: {URL}  (이 창을 닫으면 앱이 꺼집니다)")
        uvicorn.run(app, host=HOST, port=PORT, log_level="warning", log_config=None)
        sys.exit(0)

    # 기본 모드: 서버는 뒤에서 켜고, 그동안 창을 먼저 띄워 「불러오는 중」을 보여 준다
    t, holder = start_server_thread()

    def ready() -> tuple[bool, str]:
        ok = wait_server(alive=t.is_alive)
        return ok, holder.get("error", "")

    print(f"행정업무 AI: {URL}")
    if open_desktop_window(ready):
        # 창 X 버튼을 닫으면 서버도 깔끔하게 종료
        if "server" in holder:
            holder["server"].should_exit = True
        t.join(timeout=3)
    else:
        # WebView2 미지원 PC: 서버가 준비되면 브라우저로 자동 폴백해 계속 실행
        if not wait_server(alive=t.is_alive):
            print(f"서버 시작에 실패했습니다. {holder.get('error', '')}")
            sys.exit(1)
        webbrowser.open(URL)
        try:
            t.join()
        except KeyboardInterrupt:
            if "server" in holder:
                holder["server"].should_exit = True
            t.join(timeout=3)
