import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ⭐ 设置你要存放数据库的绝对路径
# 注意：Windows 路径中的反斜杠 \ 需要写成双反斜杠 \\，或者用正斜杠 /
DB_PATH = "D:\\SMT_Data\\smt_final.db"

# 如果指定的文件夹不存在，让程序自动创建
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# 拼接 SQLite 的连接字符串 (前面需要三个斜杠加上绝对路径)
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
