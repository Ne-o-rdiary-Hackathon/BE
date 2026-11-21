# Backend (Python / FastAPI 기본 뼈대)

기획 확정 전, 기능 없이 **공통 설정만** 들어 있는 프로젝트입니다.

- Python 3.10+, FastAPI, SQLAlchemy 2.0, MySQL 8
- 들어 있는 것: MySQL 연결, 공통 응답 형식, 에러 처리, CORS, 생성/수정 시각 공통 컬럼, 상태 확인 API

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
pip install -r requirements.txt

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

**테이블** — 생성/수정 시각이 필요하면 `class User(TimestampMixin, Base)`

## 5. 구조

```
app/
├── main.py          앱 시작, CORS, 예외 → 공통 응답, 라우터 등록
├── config.py        환경변수
├── database.py      DB 연결, Base, TimestampMixin, get_db
├── common.py        공통 응답(ok/fail), ErrorCode, BusinessException
└── routers/
    └── health.py    /api/health
```

기능을 추가할 때 추천 구조:
```
app/
├── models/          테이블 (예: user.py)  → main.py에서 import 해야 테이블 생성됨
├── schemas/         요청/응답 형식 (Pydantic)
├── services/        비즈니스 로직
└── routers/         API 경로 → main.py에서 app.include_router(...)
```
