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
    list.innerHTML = "無法取得貼文";
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

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const formData = new FormData(form);
  const res = await fetch("/api/posts", {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const txt = await res.text();
    alert("上傳失敗 " + txt);
    return;
  }
  form.reset();
  getPosts();
})

getPosts();