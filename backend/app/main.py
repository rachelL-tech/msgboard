import os
from typing import Optional # 用來表示某些欄位「可以是 None / 可以不填」
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field # 用來定義 request body 的資料結構與欄位驗證規則
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .db import init_db, get_connection
from .storage import create_presigned_post, create_presigned_get

load_dotenv()

app = FastAPI() # 建立 FastAPI app 實例，後面會在它上面掛路由

# 註冊一個「啟動事件」，當 FastAPI 啟動完成後會呼叫這個函式
@app.on_event("startup")
def _startup():
    init_db() # 啟動時初始化資料庫（如果表格已經存在就不會重建）

# 定義 Request body 的資料結構
# for /api/presign
class PresignIn(BaseModel):
    filename: str = Field(..., min_length=1, max_length=200) # ... 代表這個欄位是必填的，且長度限制 1–200
    content_type: str = Field(..., min_length=1, max_length=100)
    size: Optional[int] = Field(None, ge=1) # size 可不填（或是 None），如果有填必須 ≥ 1

# for /api/posts 
class PostCreateIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    image_key: Optional[str] = None

# 把 DB 裡存的 image_key，轉成前端能放在 <img src="..."> 的 image_url
def _build_image_url(image_key: Optional[str]) -> Optional[str]:
    # 沒圖片就回 None，前端就不渲染 <img>
    if not image_key:
        return None
    
    # 有 CloudFront 就直接回 CDN URL（不需要 presigned GET）
    cdn = os.getenv("CDN_DOMAIN", "").strip()
    if cdn:
        return f"https://{cdn}/{image_key}"
    
    # CloudFront 還沒串好前，先回一個「暫時可讀」的 presigned GET URL，讓使用者能預覽私有 S3 物件
    expires = int(os.getenv("VIEW_EXPIRES_IN", "3600"))
    try:
        return create_presigned_get(image_key, expires_in=expires)
    except Exception: # 如果 S3 設定/憑證有問題，回 None 讓前端不顯示圖片
        return None

@app.post("/api/presign")
def presign(data: PresignIn):
    # 只允許圖片( MIME type 以 image/ 開頭的 )，其他類型的檔案都拒絕
    if not data.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image/* is allowed")
    
    max_bytes = int(os.getenv("UPLOAD_MAX_BYTES", str(20 * 1024 * 1024))) # 預設 20 MB
    if data.size and data.size > max_bytes:
        raise HTTPException(status_code=400, detail=f"File too large (> {max_bytes} bytes)")
    
    expires = int(os.getenv("PRESIGN_EXPIRES_IN", "60"))

    try:
        return create_presigned_post(
            data.filename,
            data.content_type,
            max_bytes=max_bytes,
            expires_in=expires,
        )
    
    # 還沒建 S3 bucket、還沒 aws configure、權限不夠
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Presign failed (S3 not ready): {e}")
    
@app.post("/api/posts")
def create_post(data: PostCreateIn):
    con = get_connection()
    try:
        cur = con.cursor(dictionary=True)
        cur.execute(
            "INSERT INTO posts (message, image_key) VALUES (%s, %s)",
            (data.message, data.image_key),
        )
        con.commit()
        post_id = cur.lastrowid # 取得剛插入資料的自增主鍵 ID

        cur.execute("SELECT id, message, image_key, created_at FROM posts WHERE id=%s", (post_id,))
        row = cur.fetchone()
        
        print(_build_image_url(row.get("image_key")))

        return {
            "id": int(row["id"]),
            "message": row["message"],
            "image_url": _build_image_url(row.get("image_key")), # image_key 可能是 None，所以用 .get()
            "created_at": row["created_at"].isoformat(),
        }
        
    finally:
        con.close()

@app.get("/api/posts")
def list_posts(limit: int = 50):
    limit = max(1, min(limit, 100)) # 限制在 1–100 範圍內

    con = get_connection()
    try:
        cur = con.cursor(dictionary=True)
        cur.execute(
            "SELECT id, message, image_key, created_at FROM posts ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
        rows = cur.fetchall()

        data = []
        for r in rows:
            data.append({
                "id": int(r["id"]),
                "message": r["message"],
                "image_url": _build_image_url(r.get("image_key")),
                "created_at": r["created_at"].isoformat(),
            })
        
        return {"data": data}
    finally:
        con.close()

# 冒煙測試用（容器、ALB、Nginx health check 都常用）
@app.get("/health")
def health_check():
    return {"ok": True}

BASE_DIR = Path(__file__).resolve().parents[2] # ./msgboard
WEB_DIR = BASE_DIR / "web" # ./msgboard/web

app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web") # directory="web"：指定靜態檔資料夾，是相對路徑，會以你啟動 uvicorn 時的工作目錄為基準；html=True：訪問 / 時會回傳 web/index.html