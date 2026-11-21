export function createApi(getToken, onUnauthorized) {
  async function req(path, opts = {}) {
    const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    const t = getToken();
    if (t) headers.Authorization = "Bearer " + t;
    const r = await fetch(path, { ...opts, headers });
    if (r.status === 401) {
      onUnauthorized();
      throw new Error("未登录");
    }
    const text = await r.text();
    let j = {};
    try { j = text ? JSON.parse(text) : {}; } catch { j = { detail: text }; }
    if (!r.ok) {
      const d = j.detail;
      throw new Error(typeof d === "string" ? d : JSON.stringify(d || j));
    }
    return j;
  }
  return {
    get: (p) => req(p),
    post: (p, body) => req(p, { method: "POST", body: JSON.stringify(body || {}) }),
  };
}
