const DEFAULTS = { port: 7979, quality: 'best' };
const $ = (id) => document.getElementById(id);

const send = (msg) =>
  new Promise((resolve) => {
    chrome.runtime.sendMessage(msg, (r) => {
      const err = chrome.runtime.lastError;
      if (err) return resolve({ ok: false, swDead: true,
                                error: `확장 내부 통신 실패 — ${err.message}` });
      resolve(r || { ok: false, swDead: true, error: '서비스 워커가 응답하지 않음' });
    });
  });

async function refresh() {
  $('dot').className = 'dot';
  $('stateTxt').textContent = '확인 중';
  const r = await send({ type: 'health' });

  if (!r.ok) {
    $('dot').className = 'dot off';
    // 원인을 구분해서 말한다. 서버가 꺼진 것과 확장이 고장난 건 완전히 다른 문제다.
    $('stateTxt').textContent = r.swDead ? '확장 오류' : '연결 안 됨';
    $('out').textContent = '';
    $('err').hidden = false;
    $('err').textContent = r.error || '알 수 없는 오류';
    $('startBox').hidden = r.swDead;   // 확장 문제면 서버 켜라는 안내는 무의미
    return;
  }

  const missing = ['yt-dlp', 'ffmpeg'].filter((t) => !r.data[t.replace('-', '')]);
  $('dot').className = 'dot on';
  $('stateTxt').textContent = missing.length ? `${missing.join(', ')} 없음` : '켜짐';
  $('out').textContent = `저장 위치  ${r.data.out}`;
  $('err').hidden = true;
  $('startBox').hidden = true;
}

(async () => {
  const s = { ...DEFAULTS, ...(await chrome.storage.sync.get(DEFAULTS)) };
  $('quality').value = s.quality;
  $('port').value = s.port;
  $('cmd').textContent = 'python3 ~/Desktop/폴더임/capp/yank/server.py';

  $('retry').addEventListener('click', refresh);

  $('quality').addEventListener('change', (e) =>
    chrome.storage.sync.set({ quality: e.target.value }));

  $('port').addEventListener('change', async (e) => {
    const port = Math.min(65535, Math.max(1, Number(e.target.value) || DEFAULTS.port));
    e.target.value = port;
    await chrome.storage.sync.set({ port });
    refresh();
  });

  refresh();
})();
