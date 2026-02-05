import os
import re
from pathlib import Path # 處理路徑與檔名
from uuid import uuid4 # 產生唯一 ID
from dotenv import load_dotenv
import boto3 # AWS SDK for Python，用於與 S3 互動

load_dotenv()

S3_BUCKET = os.getenv("S3_BUCKET", "").strip() # 讀取 S3 bucket 名稱
AWS_REGION = os.getenv("AWS_REGION", "").strip() # 讀取 AWS 區域設定

_session = boto3.session.Session(region_name=AWS_REGION or None) # 建立一個 AWS session，明確控制使用的 AWS 區域；如果沒指定 region，就傳 None 讓 boto3 用預設邏輯（例如從 aws configure、環境變數、或 instance role 推斷 region）
_s3 = _session.client("s3") # 從這個 session 產生一個 S3 client，之後所有 S3 API 都會走這個 client

# 把原始檔名清理成安全版本
def _safe_filename(filename: str) -> str:
    name = Path(filename).name or "upload" # 把字串變成 Path 物件後，.name 會回傳最後的檔名；如果空就用 "upload"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name) # 把不是英數字、點、底線、減號的字元都換成底線
    return name[:120] # 最長限制 120 字元

# 回傳「讓瀏覽器可以直接上傳到 S3」所需的資料
def create_presigned_post(filename: str, content_type: str, *, max_bytes: int, expires_in: int): # 「*,」代表從這之後的參數都要用關鍵字參數傳入（一定要寫成 max_bytes=...、expires_in=...）
    if not S3_BUCKET: # 如果 bucket 沒設定（空字串），丟錯，避免產生不完整資訊
        raise RuntimeError("S3_BUCKET is not set")

    # 決定這個檔案在 S3 裡的路徑（object key），組合起來像：uploads/2f3a..._cat.png
    key = f"uploads/{uuid4().hex}_{_safe_filename(filename)}"
    # uploads/：固定放在 uploads 資料夾下
    # uuid4().hex：一串隨機唯一字串（避免同名覆蓋）

    # fields 是「前端要原封不動塞進 FormData」的表單欄位
    fields = {
        "key": key, # 要上傳到哪個 object key
        "Content-Type": content_type, # 要求的 MIME 類型
    }

    # conditions 是「policy 的約束」，S3 會用它來驗證上傳的合法性
    conditions = [ 
        {"key": key},
        {"Content-Type": content_type},
        ["content-length-range", 1, max_bytes], # 檔案大小限制 1 到 max_bytes 之間
    ]

    # boto3 產生 presigned POST 所需資料
    post = _s3.generate_presigned_post(
        Bucket=S3_BUCKET, # 指定要上傳到哪個 bucket
        Key=key, # 指定 object key
        Fields=fields, # 除了上面希望的固定欄位，會混入 AWS 自己需要的 policy、x-amz-* 等
        Conditions=conditions,
        ExpiresIn=expires_in, # 這組 presign 資料的有效期限（秒）
    )

    return {
        "method": "POST", # 提醒前端用 form POST 上傳
        "url": post["url"], # 上傳的目標 URL（S3 endpoint）
        "fields": post["fields"], # 前端必須 append 到 FormData 的欄位集合
        "key": key, # 方便前端拿來存 DB（不必從 fields 裡找）
        "expires_in": expires_in,
    }

# 輸入一個 object key，回傳一個「暫時可讀取」的 URL（用在 CloudFront 還沒上之前）
def create_presigned_get(key: str, *, expires_in: int) -> str:
    if not S3_BUCKET:
        raise RuntimeError("S3_BUCKET is not set")

    return _s3.generate_presigned_url(
        "get_object", # S3 的 GetObject 動作，產生一個「暫時可讀取/下載該檔案」的 URL，可以把它放到 <img src="..."> 讓圖片顯示
        Params={"Bucket": S3_BUCKET, "Key": key}, # 指定要讀取哪個 bucket、哪個 object key
        ExpiresIn=expires_in,
    )