# 기안 학습기 — 프로젝트 지침

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
