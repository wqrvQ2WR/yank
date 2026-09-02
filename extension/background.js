// yank — 서비스 워커.
// 콘텐츠 스크립트는 페이지 오리진(youtube.com)에 묶여 있어 localhost 로 직접
// 못 부른다. MV3 에서는 host_permissions 를 가진 서비스 워커만 CORS 를 넘는다.
// 그래서 모든 서버 호출은 여기를 거친다.

const DEFAULTS = { port: 7979, quality: 'best' };

async function settings() {
  return { ...DEFAULTS, ...(await chrome.storage.sync.get(DEFAULTS)) };
}

async function api(path, { method = 'GET', body, timeout = 8000 } = {}) {
  const { port } = await settings();
  const url = `http://127.0.0.1:${port}${path}`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  try {
    const res = await fetch(url, {
      method,
      signal: ctrl.signal,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      // 서버에 닿긴 했다 — 껐다고 하면 안 된다
      return { ok: false, status: res.status,
               error: data.error || `서버가 ${res.status} 로 거절함` };
    }
    return { ok: true, data };
  } catch (e) {
    // 여기 오는 이유는 여러 가지다(서버 꺼짐 / 포트 다름 / 크롬이 로컬 접근 차단 등).
    // 뭉뚱그리면 원인을 못 찾으니 실제 메시지를 그대로 올려보낸다.
    const detail = (e && e.message) || String(e);
    console.error('[yank] 요청 실패', url, e);
    return {
      ok: false,
      unreachable: true,
      url,
      error: e && e.name === 'AbortError'
        ? `${url} 응답 없음 (${timeout}ms 초과)`
        : `${url} 연결 실패 — ${detail}`,
    };
  } finally {
    clearTimeout(timer);
  }
}

const ROUTES = {
  health: () => api('/health', { timeout: 2500 }),
  status: (m) => api(`/status?id=${encodeURIComponent(m.id)}`, { timeout: 5000 }),
  reveal: (m) => api('/reveal', { method: 'POST', body: { id: m.id } }),
  async download(m) {
    const { quality } = await settings();
    return api('/download', {
      method: 'POST',
      timeout: 15000,
      body: {
        url: m.url,
        mode: m.mode,
        title: m.title || '',
        quality: m.mode === 'mp3' ? 'best' : (m.quality || quality),
      },
    });
  },
};

console.log('[yank] 서비스 워커 시작', new Date().toLocaleTimeString());

chrome.runtime.onMessage.addListener((msg, _sender, respond) => {
  const route = ROUTES[msg && msg.type];
  if (!route) return false;
  route(msg).then(respond, (e) => respond({ ok: false, error: String(e) }));
  return true; // 비동기 응답
});
