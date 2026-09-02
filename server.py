#!/usr/bin/env python3
"""
yank-server — 크롬 확장(yank-ext)이 부르는 로컬 다운로드 서버.

유튜브 페이지에 붙은 MP4 / MP3 버튼이 이 서버로 요청을 보내면,
yank.py 의 build_cmd 를 그대로 재사용해서 yt-dlp 를 돌린다.
127.0.0.1 에만 바인딩하고, 유튜브 도메인에서 온 유튜브 URL만 받는다.

실행:
    python3 server.py                  # 기본 127.0.0.1:7979
    python3 server.py -p 8080          # 포트 변경
    python3 server.py -o ~/Movies      # 저장 폴더 변경

API:
    GET  /health                       → {ok, out, version}
    POST /download {url, mode, quality, title}  → {id}
    GET  /status?id=...                → {state, pct, eta, path, error}
    POST /reveal {id}                  → 파인더에서 폴더 열기
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yank  # build_cmd 재사용

VERSION = "1.0.0"

ALLOWED_ORIGINS = {
    "https://www.youtube.com",
    "https://m.youtube.com",
    "https://music.youtube.com",
}
ALLOWED_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "music.youtube.com", "youtu.be", "www.youtu.be",
}

PCT = re.compile(r"\[download\]\s+(\d{1,3}(?:\.\d)?)%")
ETA = re.compile(r"ETA\s+(\S+)")
DEST = re.compile(r"^\[(?:download|Merger|ExtractAudio)\]\s+"
                  r"(?:Destination:\s*|Merging formats into \")(.+?)\"?$")

PAGE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><title>yank server</title>
<style>
  :root { --ink:#1c1d2b; --dim:#6b6f8a; --line:#e6e7f2;
          --grad:linear-gradient(135deg,#7b5cff 0%,#ff5f6d 55%,#ff8f3f 100%); }
  *{margin:0;padding:0;box-sizing:border-box}
  body{padding:40px 24px;color:var(--ink);background:#fff;
       font:400 15px/1.6 Pretendard,'Apple SD Gothic Neo',Roboto,'Noto Sans KR',system-ui,sans-serif;
       -webkit-font-smoothing:antialiased}
  .wrap{max-width:620px;margin:0 auto}
  h1{display:inline-block;font-size:34px;font-weight:800;letter-spacing:-.03em;
     background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent}
  .sub{color:var(--dim);font-size:14px;margin-bottom:24px}
  .card{border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-bottom:14px}
  .row{display:flex;align-items:center;justify-content:space-between;gap:12px}
  .row+.row{margin-top:12px;padding-top:12px;border-top:1px solid var(--line)}
  .lbl{color:var(--dim);font-size:14px;flex:none}
  .val{font-size:14px;font-weight:600;text-align:right;word-break:break-all}
  .pill{display:inline-flex;align-items:center;gap:7px;padding:5px 12px;border-radius:20px;
        font-size:13px;font-weight:600;color:#fff;
        background:linear-gradient(135deg,#12a150,#17c964)}
  .pill.bad{background:linear-gradient(135deg,#a3202e,#e0475b)}
  h2{font-size:13px;font-weight:700;color:var(--dim);letter-spacing:.02em;margin:26px 0 10px}
  .job{display:flex;align-items:center;gap:12px;padding:11px 0}
  .job+.job{border-top:1px solid var(--line)}
  .tag{flex:none;width:46px;text-align:center;padding:3px 0;border-radius:7px;
       font-size:11px;font-weight:700;color:#fff;
       background:linear-gradient(135deg,#ff5f6d,#ff8f3f)}
  .tag.mp3{background:linear-gradient(135deg,#7b5cff,#35b8ff)}
  .jt{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px}
  .js{flex:none;font-size:13px;color:var(--dim);font-variant-numeric:tabular-nums}
  .js.done{color:#12a150;font-weight:600}
  .js.error{color:#e0475b;font-weight:600}
  .empty{color:var(--dim);font-size:14px;padding:6px 0}
  code{padding:2px 7px;border-radius:6px;background:#f4f5fb;color:#33365a;
       font:13px ui-monospace,SFMono-Regular,Menlo,monospace}
</style></head>
<body><div class="wrap">
  <h1>yank</h1>
  <div class="sub">크롬 확장이 부르는 로컬 다운로드 서버</div>

  <div class="card">
    <div class="row"><span class="lbl">서버</span>
      <span class="val"><span class="pill" id="up">켜짐</span></span></div>
    <div class="row"><span class="lbl">저장 위치</span><span class="val" id="out">-</span></div>
    <div class="row"><span class="lbl">yt-dlp</span><span class="val" id="ytdlp">-</span></div>
    <div class="row"><span class="lbl">ffmpeg</span><span class="val" id="ffmpeg">-</span></div>
  </div>

  <h2>최근 작업</h2>
  <div class="card" id="jobs"><div class="empty">아직 없음. 유튜브에서 MP4 / MP3 버튼을 눌러봐.</div></div>

  <div class="sub">이 페이지는 상태만 보여준다. 받는 건 유튜브 영상 아래 버튼으로.
    확장은 <code>chrome://extensions</code> 에서 개발자 모드로 <code>yank/extension</code> 폴더를 로드.</div>
</div>
<script>
const $ = (id) => document.getElementById(id);
async function tick() {
  try {
    const h = await (await fetch('/health')).json();
    $('out').textContent = h.out;
    $('ytdlp').textContent = h.ytdlp ? '있음' : '없음 — brew install yt-dlp';
    $('ffmpeg').textContent = h.ffmpeg ? '있음' : '없음 — brew install ffmpeg';
    $('up').className = 'pill'; $('up').textContent = '켜짐';

    const { jobs } = await (await fetch('/jobs')).json();
    const box = $('jobs');
    box.textContent = '';
    if (!jobs.length) {
      const d = document.createElement('div');
      d.className = 'empty';
      d.textContent = '아직 없음. 유튜브에서 MP4 / MP3 버튼을 눌러봐.';
      box.appendChild(d);
      return;
    }
    for (const j of jobs) {
      const row = document.createElement('div'); row.className = 'job';
      const tag = document.createElement('span');
      tag.className = 'tag' + (j.mode === 'mp3' ? ' mp3' : '');
      tag.textContent = (j.mode || '').toUpperCase();
      const t = document.createElement('span');
      t.className = 'jt'; t.textContent = j.title || '(제목 없음)';
      const st = document.createElement('span');
      st.className = 'js' + (j.state === 'done' ? ' done' : j.state === 'error' ? ' error' : '');
      st.textContent = j.state === 'done' ? '완료'
        : j.state === 'error' ? (j.error || '실패')
        : `${Number(j.pct || 0).toFixed(0)}% · ${j.stage || ''}`;
      row.append(tag, t, st);
      box.appendChild(row);
    }
  } catch {
    $('up').className = 'pill bad'; $('up').textContent = '응답 없음';
  }
}
tick(); setInterval(tick, 1500);
</script>
</body></html>
"""

JOBS = {}
LOCK = threading.Lock()
OUT_DIR = os.path.expanduser("~/Downloads/yank")


def set_job(job_id, **kw):
    with LOCK:
        JOBS.setdefault(job_id, {}).update(kw)


def get_job(job_id):
    with LOCK:
        return dict(JOBS.get(job_id) or {})


def valid_url(url):
    try:
        u = urlparse(url)
    except ValueError:
        return False
    return u.scheme in ("http", "https") and u.hostname in ALLOWED_HOSTS


def run_job(job_id, url, mode, quality):
    args = SimpleNamespace(
        mp3=(mode == "mp3"),
        audio_format=None,
        quality=quality,
        out=OUT_DIR,
        name="%(title)s.%(ext)s",
        no_playlist=True,   # 확장에서는 항상 그 영상 하나만
        keep=False,
        list=False,
    )
    os.makedirs(OUT_DIR, exist_ok=True)
    cmd = yank.build_cmd(args, url)
    set_job(job_id, state="running", pct=0.0, stage="준비 중")

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
    except OSError as e:
        set_job(job_id, state="error", error=str(e))
        return

    tail = []
    path = None
    dl_no = 0   # mp4 는 영상/음성 스트림을 따로 받으므로 몇 번째인지 센다
    for line in proc.stdout:
        line = line.rstrip()
        if not line:
            continue
        tail.append(line)
        del tail[:-15]

        m = PCT.search(line)
        if m:
            e = ETA.search(line)
            if mode == "mp3" or dl_no <= 1:
                stage = "받는 중" if mode == "mp3" else "영상 받는 중"
            else:
                stage = "음성 받는 중"
            set_job(job_id, pct=float(m.group(1)), stage=stage,
                    eta=(e.group(1) if e else ""))
            continue
        d = DEST.match(line)
        if d:
            path = d.group(1)
            if line.startswith("[download]"):
                dl_no += 1
        if line.startswith("[ExtractAudio]"):
            set_job(job_id, stage="mp3 변환 중", eta="")
        elif line.startswith("[Merger]"):
            set_job(job_id, stage="합치는 중", eta="")
        elif line.startswith(("[EmbedThumbnail]", "[Metadata]", "[ThumbnailsConvertor]")):
            set_job(job_id, stage="마무리 중", eta="")

    rc = proc.wait()
    if rc == 0:
        set_job(job_id, state="done", pct=100.0, stage="완료",
                eta="", path=path or OUT_DIR)
    else:
        msg = next((l for l in reversed(tail) if "ERROR" in l), "")
        msg = msg.replace("ERROR:", "").strip() or f"yt-dlp 종료 코드 {rc}"
        set_job(job_id, state="error", error=msg[:300])


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"yank/{VERSION}"

    def log_message(self, fmt, *a):
        sys.stderr.write(f"  {self.address_string()} {fmt % a}\n")

    # ── 공통 ────────────────────────────────────────────
    def _origin_ok(self):
        origin = self.headers.get("Origin")
        # 확장 서비스워커에서 온 요청은 Origin 이 chrome-extension:// 또는 없음
        return (origin is None
                or origin in ALLOWED_ORIGINS
                or origin.startswith("chrome-extension://"))

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        origin = self.headers.get("Origin")
        self.send_header("Access-Control-Allow-Origin", origin or "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body):
        raw = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n or n > 65536:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, UnicodeDecodeError):
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin",
                         self.headers.get("Origin") or "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ── 라우트 ──────────────────────────────────────────
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._send_html(PAGE)
        if u.path == "/jobs":
            with LOCK:
                jobs = [dict(v, id=k) for k, v in JOBS.items()]
            jobs.sort(key=lambda j: j.get("started", 0), reverse=True)
            return self._send(200, {"jobs": jobs[:20]})
        if u.path == "/health":
            return self._send(200, {
                "ok": True, "version": VERSION, "out": OUT_DIR,
                "ytdlp": bool(shutil.which("yt-dlp")),
                "ffmpeg": bool(shutil.which("ffmpeg")),
            })
        if u.path == "/status":
            jid = (parse_qs(u.query).get("id") or [""])[0]
            job = get_job(jid)
            if not job:
                return self._send(404, {"error": "그런 작업 없음"})
            return self._send(200, job)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._origin_ok():
            return self._send(403, {"error": "허용되지 않은 출처"})
        u = urlparse(self.path)

        if u.path == "/download":
            b = self._body()
            url = (b.get("url") or "").strip()
            mode = "mp3" if b.get("mode") == "mp3" else "mp4"
            quality = str(b.get("quality") or "best")
            if quality not in ("480", "720", "1080", "1440", "2160", "best"):
                quality = "best"
            if not valid_url(url):
                return self._send(400, {"error": "유튜브 주소가 아님"})
            for tool in ("yt-dlp", "ffmpeg"):
                if not shutil.which(tool):
                    return self._send(503, {"error": f"{tool} 없음 — brew install {tool}"})

            jid = uuid.uuid4().hex[:12]
            set_job(jid, state="queued", pct=0.0, stage="대기 중", eta="",
                    mode=mode, title=str(b.get("title") or "")[:200],
                    started=time.time())
            threading.Thread(target=run_job, args=(jid, url, mode, quality),
                             daemon=True).start()
            print(f"  ← {mode}  {b.get('title') or url}")
            return self._send(200, {"id": jid})

        if u.path == "/reveal":
            job = get_job(self._body().get("id") or "")
            path = job.get("path") or OUT_DIR
            if sys.platform == "darwin":
                cmd = ["open", "-R", path] if os.path.isfile(path) else ["open", OUT_DIR]
                subprocess.Popen(cmd)
            return self._send(200, {"ok": True})

        return self._send(404, {"error": "not found"})


def main():
    global OUT_DIR
    p = argparse.ArgumentParser(prog="yank-server",
                                description="yank 크롬 확장용 로컬 다운로드 서버")
    p.add_argument("-p", "--port", type=int, default=7979)
    p.add_argument("-o", "--out", default=OUT_DIR, help="저장 폴더")
    a = p.parse_args()
    OUT_DIR = os.path.expanduser(a.out)
    os.makedirs(OUT_DIR, exist_ok=True)

    # launchd 로 띄우면 stdout 이 파일이라 색코드가 그대로 박힌다 → 색 끄기
    tty = sys.stdout.isatty()
    if not tty:
        for k in list(vars(yank.C)):
            if not k.startswith("_"):
                setattr(yank.C, k, "")

    missing = [t for t in ("yt-dlp", "ffmpeg") if not shutil.which(t)]
    C = yank.C
    print(f"{C.MAG}{C.B}  yank-server {C.R}{C.DIM}v{VERSION}{C.R}")
    print(f"{C.DIM}  듣는 중 {C.R}{C.CYN}http://127.0.0.1:{a.port}{C.R}"
          f"{C.DIM}  →  {C.R}{C.GRN}{OUT_DIR}{C.R}")
    if missing:
        print(f"{C.RED}  ✗ 없음: {', '.join(missing)}"
              f"  (brew install {' '.join(missing)}){C.R}")
    print(f"{C.DIM}  종료: Ctrl+C{C.R}\n" if tty else "")

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{C.DIM}  끝.{C.R}")
        srv.shutdown()


if __name__ == "__main__":
    main()
