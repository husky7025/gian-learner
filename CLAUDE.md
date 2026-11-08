# 기안 학습기 — 프로젝트 지침

- 로컬 전용 앱(127.0.0.1:8765). Supabase·Vercel 없음 (만들지 않음).
- GitHub 저장소: https://github.com/husky7025/gian-learner (공개, 기본 브랜치 main, 커밋 작성자 husky7025 noreply 주소). 코드만 올리고 샘플·데이터·개인정보는 올리지 않는다. push 전 비밀값·개인정보 검사.
- 배포: GitHub Releases로 Windows용 zip 배포 예정(Python 없이 실행되는 exe).
- 구성: `app/hwpx_engine.py`(학습·생성), `app/storage.py`(SQLite+파일, `%LOCALAPPDATA%\기안학습기`), `app/main.py`(FastAPI), `app/system.py`(바탕화면·시작프로그램 .lnk만 생성/삭제, 레지스트리 미사용), `app/static/`(화면), `run.py`, `기안학습기 실행.bat`.
- 테스트 시 실제 데이터 폴더를 건드리지 않도록 `GIAN_DATA_DIR` 환경변수로 임시 폴더를 지정한다.
- 샘플 hwpx(학교 문서·개인정보 포함 가능)는 프로젝트 폴더나 Git에 넣지 않는다.
- 분류: forms.category = gian(기안)/pumui(품의)/gatong(가정통신문). 분류에 양식이 없으면 기본 양식을 자동 생성.
