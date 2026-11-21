# Backend (Python / FastAPI)

FastAPI와 MySQL을 사용하는 백엔드입니다.

- Python 3.10+, FastAPI, SQLAlchemy 2.0, MySQL 8, Alembic
- 공통 설정, DB 연결, 예외 처리, CORS, 상태 확인 API 포함

## 1. MySQL 띄우기

```bash
docker compose up -d
```
`docker-compose.yml` 기본값: DB `gachi` / 아이디 `gachi` / 비밀번호 `gachi1234` / 문자셋 `utf8mb4`

Docker 없이 이미 설치된 MySQL을 쓴다면:
```sql
CREATE DATABASE gachi DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'gachi'@'%' IDENTIFIED BY 'gachi1234';
GRANT ALL PRIVILEGES ON gachi.* TO 'gachi'@'%';
FLUSH PRIVILEGES;
```
> 이모지 같은 문자를 저장하려면 문자셋이 꼭 `utf8mb4`여야 합니다.

## 2. 실행

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env             # Windows: copy .env.example .env

uvicorn app.main:app --reload --port 8080
```

확인: http://localhost:8080/api/health
```json
{ "success": true, "data": { "server": "UP", "db": "UP" }, "error": null }
```
API 문서(자동 생성): http://localhost:8080/docs

배포 시: `uvicorn app.main:app --host 0.0.0.0 --port 8080` (`--reload` 빼기)

## 3. 환경변수 (`.env`)

| 이름 | 기본값 | 설명 |
|---|---|---|
| `DATABASE_URL` | `mysql+pymysql://gachi:gachi1234@localhost:3306/gachi?charset=utf8mb4` | 끝의 `?charset=utf8mb4` 꼭 유지 |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:5173` | 프론트 주소 (쉼표로 여러 개) |
| `SHOW_SQL` | `false` | `true`면 SQL 로그 출력 |

## 4. 공통 규칙

**응답 형식** — 라우터는 `return ok(data)`
```json
// 성공
{ "success": true, "data": { ... }, "error": null }
// 실패
{ "success": false, "data": null, "error": { "code": "NOT_FOUND", "message": "..." } }
```

**에러** — `app/common.py`의 `ErrorCode`에 추가하고 `raise BusinessException(ErrorCode.XXX)`

**테이블** — `app/models/`에 SQLAlchemy 모델을 만들고 생성/수정 시각이 필요하면 `TimestampMixin`을 사용합니다.

**마이그레이션** — 모델을 추가한 뒤 변경 이력을 생성하고 적용합니다.
```bash
alembic revision --autogenerate -m "create user"
alembic upgrade head
```
모델은 `app/models/__init__.py`에서 import해야 Alembic 자동 생성 대상에 포함됩니다.

## 5. 구조

```
app/
├── main.py              앱 시작, CORS, 예외 처리, 라우터 등록
├── common.py            공통 응답(ok/fail), ErrorCode, BusinessException
├── core/config.py       환경변수
├── db/
│   ├── base.py          SQLAlchemy Base, TimestampMixin
│   └── session.py       DB 연결, SessionLocal, get_db
├── models/              SQLAlchemy 모델
├── schemas/             요청·응답 DTO
├── api/                 라우터
│   └── health.py        /api/health
├── services/            비즈니스 로직
└── repositories/        DB 조회·저장
alembic/                 DB 마이그레이션 설정과 버전 파일
tests/                   테스트 코드
pyproject.toml           의존성 및 프로젝트 설정
.env                     로컬 환경변수 (git 제외)
```

테스트 실행: `pytest`
