# 기안 학습기 — 프로젝트 지침

- 앱 표시 이름: **행정업무 AI** (2026-11-21 변경, exe·바로가기·bat 이름 포함). 저장소·데이터 폴더(`기안학습기`)·.gianpack 이름은 그대로.
- 화면 디자인(2026-11-21 교체): 흰 바탕·연회색(#f5f5f7) 사이드바·검정 타일(#272729, 미리보기 틀). 누를 수 있는 것은 파란색 #0066cc 하나뿐, 주요 버튼은 알약 모양, 제목은 시스템 산세리프 굵기 600·좁은 자간, 그림자는 미리보기 「종이」에만, 누르면 scale(.95). 색은 style.css의 :root 변수만 쓴다. 회사 로고·이름(Apple 등)은 넣지 않는다.
- AI 설정의 「🔑 API 키 받는 방법 (Gemini)」 버튼 → https://aistudio.google.com/apikey (새 창, pywebview는 외부 브라우저로 연다).
- 실행 속도(2026-11-21): bat의 설치 확인은 `python run.py --check-deps`(find_spec만, import 금지 — anthropic import만 12초). PYTHONIOENCODING=utf-8은 bat 맨 위(사용자 폴더 한글 경로). 기본 모드는 창을 먼저 띄워 「불러오는 중」 → 서버 준비되면 load_url.
- 백업: 중요한 백업 20개 + 자주 생기는 백업(샘플 삭제·옮기기, `routine=True`) 10개를 따로 센다. DB는 `S.db()`(항상 닫힘)로 연다.

- 로컬 전용 앱(127.0.0.1:8765). Supabase·Vercel 없음 (만들지 않음).
- GitHub 저장소: https://github.com/husky7025/gian-learner (공개, 기본 브랜치 main, 커밋 작성자 husky7025 noreply 주소). 코드만 올리고 샘플·데이터·개인정보는 올리지 않는다. push 전 비밀값·개인정보 검사.
- 배포: GitHub Releases로 Windows용 zip 배포 예정(Python 없이 실행되는 exe).
- 구성: `app/hwpx_engine.py`(학습·생성), `app/storage.py`(SQLite+파일, `%LOCALAPPDATA%\기안학습기`), `app/main.py`(FastAPI), `app/system.py`(바탕화면·시작프로그램 .lnk만 생성/삭제, 레지스트리 미사용), `app/static/`(화면), `run.py`, `기안학습기 실행.bat`.
- 테스트 시 실제 데이터 폴더를 건드리지 않도록 `GIAN_DATA_DIR` 환경변수로 임시 폴더를 지정한다.
- 샘플 hwpx(학교 문서·개인정보 포함 가능)는 프로젝트 폴더나 Git에 넣지 않는다.
- 분류: forms.category = gian(기안)/pumui(품의)/gatong(가정통신문). 분류에 양식이 없으면 기본 양식을 자동 생성.
- 양식 꾸러미: `app/packs.py`(내보내기 시 작성자·미리보기 그림·파일명 제거, 개인정보 검사). 기본 꾸러미 `packs/기본양식.gianpack`은 `tools/make_default_pack.py`로 가상 예시만 넣어 생성 — 다시 만들면 원본 이름·전화번호가 없는지 바이트 단위로 검사 후 커밋.
- 버전: `app/version.py` = 태그 vX.Y.Z (Actions가 불일치 시 실패). 출시는 `.github/workflows/release.yml`(windows-latest, PyInstaller onedir --windowed, exe 실행 검사 후 gh release create).
- ODT·PDF 샘플은 `app/convert.py`로 기본 꾸러미 품의 예시 서식의 hwpx로 변환(content.hpf description=gian-learner:converted). 기준 서식은 원본 hwpx 샘플을 우선.
- PDF는 pypdf(BSD) 사용. PyMuPDF는 AGPL이라 쓰지 않음.
- 새 버전 알림: `app/updates.py`가 GitHub releases/latest의 tag_name만 조회(6시간 캐시, settings.json의 update_check로 끔). 시험할 때는 GIAN_UPDATE_URL로 가짜 응답 주소 지정.
- ⚠ 시험할 때는 반드시 `GIAN_PORT=8766`(다른 포트)와 `GIAN_DATA_DIR`(임시 폴더)를 함께 지정한다. 8765에는 사용자가 실제로 쓰는 앱이 떠 있을 수 있다(2026-11-08 실수로 실제 데이터에 시험 샘플이 올라간 적 있음).
- 표 줄 늘리기·줄이기는 만들지 않는다(사용자 결정 2026-11-21: 기안문엔 표가 없고 품의 표는 에듀파인이 자동 생성). 샘플 다른 양식 감지 `/api/forms/{id}/sample-check`(E.signature 유사도), 옮기기 `.../move`(백업 후).
- 샘플 폴더 `샘플/`(사용자가 실제 샘플을 두는 곳)는 .gitignore 처리 — 절대 커밋하지 않는다.
- AI 모델: 기본 gemini-3.6-flash / gpt-6-luna (2026-11). `RETIRED_MODELS`면 기본 모델로, 모델 없음 오류면 `pick_model`로 목록에서 골라 한 번 재시도 후 저장(결과에 switched_from).
- 실행 bat: 같은 python의 pythonw로 창 없이 실행(for 변수는 %%i — %%p는 ~dp와 겹침, 한글 경로 때문에 PYTHONIOENCODING=utf-8). 시험 때는 cmd에 GIAN_PORT/GIAN_DATA_DIR가 실제로 넘어갔는지 /api/info로 꼭 확인(2026-11-21 bash→cmd로 안 넘어가 8765 실데이터로 켜진 적 있음).
- 자동 시험: `python -m pytest -q tests` (tests/conftest.py가 임시 데이터 폴더·가짜 Gemini 서버를 먼저 설정, 기본 꾸러미 가상 예시만 사용). release.yml은 시험 통과 후 빌드, test.yml은 main push마다 실행.
- 캐시: main._learn은 (양식, 샘플 파일 크기·수정시각, 학습설정)으로, sample-check 표식은 샘플 파일 stamp로 캐시. 백업은 samples/outputs 하드링크(_link_tree) — 이 파일들은 쓴 뒤 고치지 않는다는 전제.
- 보고서 검토(2026-11-21)에서 안 한 것: 문단 안 부분 서식 보존(기안·품의 샘플엔 없음, 가정통신문·협의록만), 다중 구역 학습(안내만), WAL(필요 없음), os._exit 교체, 라우터·프론트 구조 개편.
- AI 작성: `app/ai.py` — 제공자 ollama(기본)/claude(anthropic SDK, output_config json_schema, opus-5-5 등은 fallbacks="default")/gemini/openai(REST). 키는 `ai.json`에 DPAPI 암호화. 온라인 AI는 redact()로 개인정보 가림. 시험은 GIAN_CLAUDE_URL/GIAN_OPENAI_URL/GIAN_GEMINI_URL로 가짜 서버 지정. 실제 모델로 품질 검사는 아직 못 함.
