const API_BASE = "http://localhost:8000"; // 設定後端 API 的 base URL

const form = document.querySelector("#form");
const list = document.querySelector("#list");

function preventXSS(s) {
    return s.replace(/[&<>"']/g, m => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    }[m]));
}

async function getPosts() {
  const res = await fetch("/api/posts");
  if (!res.ok) {
    list.innerHTML = `<div class="post">無法取得貼文</div>`;
    return;
  }

  const json = await res.json(); // { "data": [ { "id": 1, "message": "...", "image_url": "...", "created_at": "..." }, ... ] }
  list.innerHTML = json.data.map(p => `
    <div class="post">
      <h3>${preventXSS(p.message)}</h3>
      ${p.image_url ? `<img src="${p.image_url}" alt="image">` : ""}
      <div class="meta">#${p.id} · ${p.created_at}</div>
    </div>
  `).join("");
}

// 向後端要 presign（一次性可用的 S3 上傳資訊）
async function presign(file) {
  const res = await fetch(`${API_BASE}/api/presign`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: file.name, // 原始檔名
      content_type: file.type || "application/octet-stream", // 檔案 MIME，沒有就用通用值
      size: file.size // 檔案大小（讓後端可以先擋掉超過上限）
     })
  });

  if (!res.ok) throw new Error(await res.text()); // S3 還沒設好、憑證沒設
  
  return await res.json();
}

// 把檔案直接上傳到 S3（用 presigned POST，不是presigned PUT）
async function uploadToS3(presignData, file) {
  const fd = new FormData();
  for (const [k, v] of Object.entries(presignData.fields)){
    fd.append(k, v);
  } // presignData.fields 是 AWS 規定要帶的欄位（含 policy、x-amz-*、key、Content-Type 等），必須全部 append 進去，S3 才會驗證通過。
  fd.append("file", file); // 最後把檔案本體放到欄位名 "file"

  const r = await fetch(presignData.url, {
    method: "POST",
    body: fd
  });

  if (!r.ok) throw new Error(`上傳到 S3 失敗: ${r.status}`);
}


form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const message = form.querySelector("textarea[name=message]").value.trim();
  const file = form.querySelector("input[name=image]").files[0]; // 因為「type=file」，使用者選完檔案後，瀏覽器會把檔案放在 input.files（FileList）裡，再用[0]取得第一個檔案。file 含檔名、大小、MIME、內容等資訊

  const btn = form.querySelector("button");
  btn.disabled = true;

  try {
    let image_key = null;

    if (file) {
      const presignData = await presign(file); // 向後端要 presign 資訊
      await uploadToS3(presignData, file); // 拿 presign 的資料把檔案直傳 S3
      image_key = presignData.key; // 上傳成功後，記下 S3 裡的檔案 key，之後要存到資料庫
    }

    // 圖片（如果有）成功傳到 S3 之後，才呼叫後端 /api/posts 寫入 DB
    const res = await fetch(`${API_BASE}/api/posts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        image_key // 如果沒有上傳檔案，image_key 就是 null
      })
    });

    if (!res.ok) throw new Error(await res.text());

    form.reset(); // 清空表單（文字跟檔案選取都會被清掉）
    await getPosts(); // 重新拉一次貼文列表，讓剛發的貼文立即出現在畫面
  } catch (err) { // presign 失敗 / S3 上傳失敗 / 存 DB 失敗
    alert("上傳失敗: " + err.message);
  } finally {
    btn.disabled = false;
  } 
});

// 頁面載入就先拉一次貼文
getPosts();