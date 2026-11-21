from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,   # 끊긴 연결 자동 감지
    pool_recycle=3600,    # MySQL이 오래된 연결을 끊기 전에 교체
    echo=settings.show_sql,
)

SessionLocal = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)


def get_db():
    """요청마다 DB 세션 하나. 라우터에서 db: Session = Depends(get_db)
    쓰기 작업은 db.commit()을 직접 호출하세요. 커밋 안 된 변경은 닫힐 때 롤백됩니다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
