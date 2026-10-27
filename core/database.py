import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 支持环境变量覆盖，避免路径硬编码
DB_PATH = os.environ.get("SMT_DB_PATH", "D:\\SMT_Data\\smt_final.db")

# 如果指定的文件夹不存在，让程序自动创建
os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
    echo=False,
)

# expire_on_commit=False：避免 commit 后再访问 ORM 对象属性重新查询
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)
