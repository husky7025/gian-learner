"""시험 환경: 실제 데이터 폴더를 건드리지 않도록 임시 폴더와 가짜 Gemini 서버를 쓴다.
(app을 가져오기 전에 환경 변수를 정해야 하므로 여기서 먼저 설정한다.)"""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class FakeGemini(BaseHTTPRequestHandler):
    """모델 목록과 generateContent를 흉내 낸다. 기록은 FakeGemini.calls에."""
    calls: list = []
    gone = {"gemini-2.5-flash", "gemini-9-gone"}   # 이 계정에서 못 쓰는 모델
    reject_schema = False                          # True면 responseJsonSchema가 있으면 400

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        names = ["gemini-3.6-flash", "gemini-3.8-flash", "gemini-2.5-flash", "gemini-3-flash-preview",
                 "gemini-3.6-flash-image", "gemini-embedding-001"]
        self._send(200, {"models": [{"name": "models/" + n, "supportedGenerationMethods":
                                     ["embedContent"] if "embedding" in n else ["generateContent"]} for n in names]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        model = self.path.split("/models/")[1].split(":")[0]
        has_schema = "responseJsonSchema" in body.get("generationConfig", {})
        FakeGemini.calls.append((model, has_schema))
        if model in FakeGemini.gone:
            return self._send(404, {"error": {"message": f"models/{model} is not found"}})
        if has_schema and FakeGemini.reject_schema:
            return self._send(400, {"error": {"message": "Invalid JSON payload: responseJsonSchema"}})
        ans = {"filename": "시험", "fields": {}, "outline": [{"depth": 0, "label": "건명", "value": "시험 품의"}],
               "attach": [], "cells": {}}
        self._send(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(ans, ensure_ascii=False)}]}}]})


_srv = HTTPServer(("127.0.0.1", 0), FakeGemini)
threading.Thread(target=_srv.serve_forever, daemon=True).start()

os.environ["GIAN_DATA_DIR"] = tempfile.mkdtemp(prefix="gian-test-")
os.environ["GIAN_GEMINI_URL"] = f"http://127.0.0.1:{_srv.server_port}"
os.environ["GIAN_UPDATE_URL"] = "http://127.0.0.1:1/none"
os.environ.setdefault("GIAN_PORT", "8765")


@pytest.fixture
def fake_gemini():
    return FakeGemini
