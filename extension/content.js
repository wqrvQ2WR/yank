// yank — 유튜브 영상 액션 줄(좋아요/공유 옆)에 MP4 / MP3 버튼을 붙인다.
// 실제 다운로드는 로컬 yank 서버가 한다. 여기는 UI 와 진행률만.

(() => {
  'use strict';

  const ID = 'yank-buttons';
  const POLL_MS = 600;

  const ICON = {
    mp4: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v10.6l3.3-3.3 1.4 1.4L11 17.4l-5.7-5.7 1.4-1.4 3.3 3.3V3h2z"/><path d="M4 19h16v2H4z"/></svg>',
    mp3: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v10.6a3.5 3.5 0 1 0 2 3.16V7h4V3h-6z"/></svg>',
    done: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.6 16.6 5 12l1.4-1.4 3.2 3.2 8-8L19 7.2z"/></svg>',
    warn: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2 1 21h22L12 2zm1 14h-2v2h2v-2zm0-7h-2v5h2V9z"/></svg>',
  };

  // 실패를 두 갈래로 나눠서 본다.
  //   swDead  = 콘텐츠 스크립트 → 서비스 워커 자체가 안 됨 (확장 문제)
  //   unreachable = 서비스 워커 → 로컬 서버가 안 됨 (서버/포트/차단 문제)
  const send = (msg) =>
    new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(msg, (r) => {
          const err = chrome.runtime.lastError;
          if (err) {
            return resolve({ ok: false, swDead: true,
                             error: `확장 내부 통신 실패 — ${err.message}` });
          }
          resolve(r || { ok: false, swDead: true, error: '서비스 워커가 응답하지 않음' });
        });
      } catch (e) {
        resolve({ ok: false, swDead: true, error: `확장 호출 실패 — ${e.message}` });
      }
    });

  // ── 페이지에서 영상 정보 긁기 ──────────────────────────
  function videoUrl() {
    const v = new URLSearchParams(location.search).get('v');
    if (v) return `https://www.youtube.com/watch?v=${v}`;
    const m = location.pathname.match(/^\/(?:shorts|live)\/([\w-]{6,})/);
    return m ? `https://www.youtube.com/watch?v=${m[1]}` : null;
  }

  function videoTitle() {
    const h1 = document.querySelector('ytd-watch-metadata h1 yt-formatted-string, h1.ytd-watch-metadata');
    return (h1 && h1.textContent.trim()) || document.title.replace(/ - YouTube$/, '').trim();
  }

  function actionRow() {
    return document.querySelector('ytd-watch-metadata #actions #top-level-buttons-computed')
      || document.querySelector('#top-level-buttons-computed')
      || document.querySelector('ytd-watch-metadata #actions-inner')
      || document.querySelector('ytd-watch-metadata #actions');
  }

  // ── 토스트 ────────────────────────────────────────────
  let toastTimer;
  function toast(text, kind = 'info') {
    let el = document.querySelector('.yank-toast');
    if (!el) {
      el = document.createElement('div');
      el.className = 'yank-toast';
      document.body.appendChild(el);
    }
    el.dataset.kind = kind;
    el.textContent = text;
    el.classList.add('yank-show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('yank-show'), 5200);
  }

  // ── 버튼 상태 ─────────────────────────────────────────
  function setLabel(btn, html, text) {
    btn.querySelector('.yank-ico').innerHTML = html;
    btn.querySelector('.yank-txt').textContent = text;
  }

  function reset(btn) {
    const mode = btn.dataset.mode;
    btn.dataset.state = 'idle';
    btn.style.setProperty('--p', '0%');
    btn.disabled = false;
    btn.title = mode === 'mp3' ? '오디오만 mp3 로 받기' : '영상을 mp4 로 받기';
    setLabel(btn, ICON[mode], mode.toUpperCase());
  }

  async function poll(btn, id) {
    const r = await send({ type: 'status', id });
    if (!btn.isConnected) return;

    if (!r.ok) {
      btn.dataset.state = 'error';
      btn.disabled = false;
      btn.title = r.error;
      setLabel(btn, ICON.warn, '끊김');
      toast(r.error, 'error');
      setTimeout(() => btn.isConnected && reset(btn), 5000);
      return;
    }

    const j = r.data;
    if (j.state === 'done') {
      btn.dataset.state = 'done';
      btn.dataset.job = id;
      btn.disabled = false;
      btn.title = '저장한 폴더 열기';
      btn.style.setProperty('--p', '100%');
      setLabel(btn, ICON.done, '폴더 열기');
      toast(`${(j.mode || '').toUpperCase()} 저장 완료 — ${j.title || ''}`, 'done');
      return;
    }
    if (j.state === 'error') {
      btn.dataset.state = 'error';
      btn.disabled = false;
      btn.title = j.error || '다운로드 실패';
      setLabel(btn, ICON.warn, '실패');
      toast(j.error || '다운로드 실패', 'error');
      setTimeout(() => btn.isConnected && reset(btn), 5000);
      return;
    }

    const pct = Number(j.pct || 0);
    const stage = j.stage || '진행 중';
    const downloading = stage.includes('받는');
    btn.style.setProperty('--p', `${pct}%`);
    // mp4 는 영상/음성을 따로 받아 게이지가 두 번 찬다 → 어느 쪽인지 툴팁에.
    btn.title = downloading && j.eta ? `${stage} · 남은 시간 ${j.eta}` : stage;
    setLabel(btn, ICON[btn.dataset.mode],
      downloading ? `${pct.toFixed(0)}%` : stage);
    setTimeout(() => poll(btn, id), POLL_MS);
  }

  async function onClick(btn) {
    if (btn.dataset.state === 'done') {
      send({ type: 'reveal', id: btn.dataset.job });
      reset(btn);
      return;
    }
    if (btn.dataset.state === 'busy') return;

    const url = videoUrl();
    if (!url) return toast('이 페이지에서는 영상 주소를 못 찾겠어.', 'error');

    btn.dataset.state = 'busy';
    btn.disabled = true;
    btn.style.setProperty('--p', '0%');
    setLabel(btn, ICON[btn.dataset.mode], '시작 중');

    const r = await send({
      type: 'download', mode: btn.dataset.mode, url, title: videoTitle(),
    });

    if (!r.ok) {
      btn.dataset.state = 'error';
      btn.disabled = false;
      btn.title = r.error;
      setLabel(btn, ICON.warn,
        r.swDead ? '확장 오류' : r.unreachable ? '연결 실패' : '실패');
      toast(r.unreachable
        ? `${r.error}  |  서버가 켜져 있는지 확인: http://127.0.0.1:7979`
        : r.error, 'error');
      setTimeout(() => btn.isConnected && reset(btn), 8000);
      return;
    }
    poll(btn, r.data.id);
  }

  // ── 주입 ──────────────────────────────────────────────
  function makeButton(mode) {
    const b = document.createElement('button');
    b.className = 'yank-btn';
    b.dataset.mode = mode;
    b.dataset.state = 'idle';
    b.title = mode === 'mp3' ? '오디오만 mp3 로 받기' : '영상을 mp4 로 받기';
    b.innerHTML = `<span class="yank-ico">${ICON[mode]}</span>`
      + `<span class="yank-txt">${mode.toUpperCase()}</span>`;
    b.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      onClick(b);
    });
    return b;
  }

  function inject() {
    if (!videoUrl()) return;
    const row = actionRow();
    if (!row) return;

    const existing = document.getElementById(ID);
    if (existing) {
      if (existing.parentElement === row) return;  // 이미 제자리
      existing.remove();                            // 유튜브가 줄을 갈아끼움
    }

    const wrap = document.createElement('div');
    wrap.id = ID;
    wrap.className = 'yank-wrap';
    wrap.append(makeButton('mp4'), makeButton('mp3'));
    row.appendChild(wrap);
  }

  let timer;
  const schedule = () => {
    clearTimeout(timer);
    timer = setTimeout(inject, 300);
  };

  new MutationObserver(schedule).observe(document.documentElement, {
    childList: true, subtree: true,
  });
  window.addEventListener('yt-navigate-finish', schedule);
  document.addEventListener('yt-page-data-updated', schedule);
  schedule();
})();
