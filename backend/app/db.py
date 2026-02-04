import os
from dotenv import load_dotenv
import mysql.connector.pooling

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "anon_board")

_pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="anon_board_pool",
    pool_size=5,
    pool_reset_session=True,
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME,
    charset="utf8mb4",
    collation="utf8mb4_unicode_ci",
)

def get_connection():
    con = _pool.get_connection() # 從連線池取出一條連線
    con.ping(reconnect=True) # 確認連線活著，斷線就自動重連
    return con

def init_db():
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS posts (
              id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
              message TEXT NOT NULL,
              image_key VARCHAR(1024) NULL,
              created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
        )
        con.commit()
    finally:
        con.close()