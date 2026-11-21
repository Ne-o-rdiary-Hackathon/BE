"""MySQL 스키마(BIGINT / TINYINT)와 맞추면서 테스트용 SQLite에서도 동작하는 컬럼 타입."""
from sqlalchemy import BigInteger, Integer, SmallInteger
from sqlalchemy.dialects import mysql

# SQLite는 INTEGER PRIMARY KEY만 자동 증가하므로 테스트에서는 Integer로 바꿔 씁니다.
BigId = BigInteger().with_variant(Integer(), "sqlite")
TinyInt = SmallInteger().with_variant(mysql.TINYINT(), "mysql")
