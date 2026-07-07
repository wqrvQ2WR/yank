#!/usr/bin/env python3
"""
yank — 유튜브(및 1000여 개 사이트) 영상을 mp4 또는 mp3로 뽑아온다.

yt-dlp + ffmpeg 를 감싸서 기본값·컬러 출력·파일명 정리까지 알아서 해준다.
받은 파일은 기본으로 ~/Downloads/yank 에 저장된다.

사용법:
    yank <url>                 # 최고 화질 mp4
    yank <url> --mp3           # 오디오만 mp3 (320k)
    yank <url> -q 1080         # 1080p 이하로 제한
    yank <url1> <url2> ...     # 여러 개 한 번에
    yank <재생목록 url>         # 재생목록 통째로
    yank <url> -o ~/내폴더      # 저장 위치 지정

    yank 뉴진스 하입보이         # 제목으로 검색 → 목록에서 골라 받기
    yank -s "aespa spicy"      # 검색 모드 명시
    yank -s 로파이 --mp3 -r 20   # 20개 검색해서 고른 걸 mp3로

옵션:
    -s, --search     인자를 URL이 아닌 검색어로 취급 (유튜브 검색)
    -r, --results    검색 결과 개수 (기본 10)
    --mp3            영상 대신 오디오(mp3)만 추출
    -q, --quality    최대 화질: 480 / 720 / 1080 / 1440 / 2160 / best (기본 best)
    -o, --out        저장 폴더 (기본 ~/Downloads/yank)
    -n, --name       파일명 템플릿 (yt-dlp 형식, 기본 "%(title)s.%(ext)s")
    --audio-format   mp3 대신 다른 오디오 포맷 (m4a/opus/wav 등)
    --no-playlist    재생목록 url이어도 그 영상 하나만
    --keep           변환 후 원본도 남김
    --list           받지 말고 사용 가능한 포맷만 보여줌
"""

import argparse
import os
import shutil
import subprocess
import sys

# ── 터미널 색 ──────────────────────────────────────────────
class C:
    R = "\033[0m"; B = "\033[1m"; DIM = "\033[2m"
    GRN = "\033[32m"; YEL = "\033[33m"; RED = "\033[31m"
    CYN = "\033[36m"; MAG = "\033[35m"


def die(msg):
    print(f"{C.RED}✗ {msg}{C.R}", file=sys.stderr)
    sys.exit(1)


def need(tool):
    if shutil.which(tool) is None:
        die(f"'{tool}' 가 없어. 설치하고 다시 시도해:  brew install {tool}")


def banner():
    print(f"{C.MAG}{C.B}  yank {C.R}{C.DIM}— 영상 뽑아오기{C.R}")


def is_url(s):
    return s.startswith(("http://", "https://", "youtu.be/", "www."))


def fmt_views(v):
    if not v or not v.isdigit():
        return ""
    n = int(v)
    if n >= 100_000_000:
        return f"{C.DIM}조회 {n/100_000_000:.1f}억{C.R}"
    if n >= 10_000:
        return f"{C.DIM}조회 {n/10_000:.0f}만{C.R}"
    return f"{C.DIM}조회 {n:,}{C.R}"


def search_youtube(query, n):
    """유튜브를 검색해서 결과 메타데이터 리스트를 돌려준다 (다운로드 X)."""
    spec = f"ytsearch{n}:{query}"
    fields = "%(id)s\t%(title)s\t%(duration_string)s\t%(channel)s\t%(view_count)s"
    cmd = ["yt-dlp", spec, "--flat-playlist", "--no-warnings",
           "--ignore-errors", "--print", fields]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True)
    except KeyboardInterrupt:
        die("중단됨.")
    results = []
    for line in out.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0]:
            continue
        g = lambda i: parts[i] if len(parts) > i and parts[i] != "NA" else ""
        results.append({
            "id": parts[0], "title": parts[1],
            "dur": g(2), "channel": g(3), "views": g(4),
        })
    return results


def parse_selection(raw, maxn):
    """'1 3 5', '1-3', '2,4' 같은 입력을 인덱스 리스트로."""
    picked = []
    for tok in raw.replace(",", " ").split():
        if "-" in tok:
            a, _, b = tok.partition("-")
            if a.isdigit() and b.isdigit():
                picked.extend(range(int(a), int(b) + 1))
        elif tok.isdigit():
            picked.append(int(tok))
    seen, out = set(), []
    for i in picked:
        if 1 <= i <= maxn and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def pick_results(results, query):
    """검색 결과를 보여주고 사용자가 고른 영상들의 URL 리스트를 돌려준다."""
    print(f'{C.CYN}"{query}"{C.R}{C.DIM} 검색 결과 {len(results)}개:{C.R}\n')
    for i, r in enumerate(results, 1):
        dur = r["dur"] or "?"
        line2 = "   ".join(x for x in [
            f"{C.DIM}⏱ {dur}{C.R}",
            f"{C.CYN}{r['channel']}{C.R}" if r["channel"] else "",
            fmt_views(r["views"]),
        ] if x)
        print(f"  {C.YEL}{C.B}{i:>2}{C.R}  {r['title']}")
        if line2:
            print(f"      {line2}")
    print()
    prompt = (f"{C.B}번호 선택{C.R} "
              f"{C.DIM}(예: 1 · 1-3 · 1 3 5 · a=전체 · q=취소): {C.R}")
    try:
        raw = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return []
    if not raw or raw.lower() == "q":
        return []
    if raw.lower() == "a":
        idxs = list(range(1, len(results) + 1))
    else:
        idxs = parse_selection(raw, len(results))
    return [f"https://www.youtube.com/watch?v={results[i - 1]['id']}"
            for i in idxs]


def build_cmd(args, url):
    cmd = ["yt-dlp", "--newline", "--progress"]

    # 저장 위치 / 파일명
    out_tmpl = os.path.join(args.out, args.name)
    cmd += ["-o", out_tmpl]

    # 재생목록 처리
    if args.no_playlist:
        cmd += ["--no-playlist"]
    else:
        cmd += ["--yes-playlist"]

    if args.list:
        cmd += ["-F", url]
        return cmd

    if args.mp3 or args.audio_format:
        fmt = args.audio_format or "mp3"
        cmd += [
            "-f", "bestaudio/best",
            "--extract-audio",
            "--audio-format", fmt,
            "--audio-quality", "0",          # 최고 품질
            "--embed-thumbnail",
            "--embed-metadata",
        ]
    else:
        # 화질 상한 필터
        if args.quality and args.quality != "best":
            h = args.quality
            vf = (f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/"
                  f"bestvideo[height<={h}]+bestaudio/best[height<={h}]")
        else:
            vf = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        cmd += [
            "-f", vf,
            "--merge-output-format", "mp4",
            "--embed-thumbnail",
            "--embed-metadata",
            "--embed-subs",
            "--sub-langs", "ko,en",
        ]

    if args.keep:
        cmd += ["--keep-video"]

    cmd += [url]
    return cmd


def main():
    p = argparse.ArgumentParser(
        prog="yank",
        description="유튜브 등에서 영상을 mp4/mp3로 뽑아온다.",
        add_help=True,
    )
    p.add_argument("urls", nargs="*",
                   help="영상/재생목록 주소, 또는 검색어 (URL이 아니면 검색)")
    p.add_argument("-s", "--search", action="store_true",
                   help="인자를 검색어로 취급 (유튜브 검색)")
    p.add_argument("-r", "--results", type=int, default=10,
                   help="검색 결과 개수 (기본 10)")
    p.add_argument("--mp3", action="store_true", help="오디오만 mp3로 추출")
    p.add_argument("-q", "--quality", default="best",
                   help="최대 화질: 480/720/1080/1440/2160/best")
    p.add_argument("-o", "--out",
                   default=os.path.expanduser("~/Downloads/yank"),
                   help="저장 폴더 (기본 ~/Downloads/yank)")
    p.add_argument("-n", "--name", default="%(title)s.%(ext)s",
                   help="파일명 템플릿 (yt-dlp 형식)")
    p.add_argument("--audio-format", default=None,
                   help="mp3 대신 다른 오디오 포맷 (m4a/opus/wav 등)")
    p.add_argument("--no-playlist", action="store_true",
                   help="재생목록 url이어도 영상 하나만")
    p.add_argument("--keep", action="store_true", help="변환 후 원본도 남김")
    p.add_argument("--list", action="store_true",
                   help="받지 말고 사용 가능한 포맷만 표시")
    args = p.parse_args()

    if not args.urls:
        banner()
        p.print_help()
        sys.exit(0)

    need("yt-dlp")
    need("ffmpeg")

    banner()

    # ── 검색어 vs URL 판별 ──
    # -s 플래그가 있거나, 인자에 URL이 하나도 없으면 통째로 검색어로 취급.
    if args.search or not any(is_url(u) for u in args.urls):
        query = " ".join(args.urls).strip()
        if not query:
            die("검색어가 비었어.")
        print(f"{C.DIM}검색 중… {C.R}{C.CYN}{query}{C.R}\n")
        results = search_youtube(query, max(1, args.results))
        if not results:
            die(f'"{query}" 검색 결과가 없어.')
        download_urls = pick_results(results, query)
        if not download_urls:
            print(f"{C.DIM}선택 안 함. 종료.{C.R}")
            sys.exit(0)
    else:
        download_urls = args.urls

    args.out = os.path.expanduser(args.out)
    os.makedirs(args.out, exist_ok=True)

    kind = "mp3" if (args.mp3 or args.audio_format) else "mp4"
    label = args.audio_format if args.audio_format else kind
    print(f"{C.DIM}포맷 {C.R}{C.CYN}{label}{C.R}"
          f"{C.DIM}  화질 {C.R}{C.CYN}{args.quality}{C.R}"
          f"{C.DIM}  →  {C.R}{C.GRN}{args.out}{C.R}\n")

    ok, fail = 0, 0
    total = len(download_urls)
    for i, url in enumerate(download_urls, 1):
        if total > 1:
            print(f"{C.MAG}[{i}/{total}]{C.R} {C.B}{url}{C.R}")
        cmd = build_cmd(args, url)
        try:
            rc = subprocess.call(cmd)
        except KeyboardInterrupt:
            die("중단됨.")
        if rc == 0:
            ok += 1
            if not args.list:
                print(f"{C.GRN}✔ 완료{C.R}\n")
        else:
            fail += 1
            print(f"{C.RED}✗ 실패 (코드 {rc}){C.R}\n")

    if not args.list and total >= 1:
        msg = f"{C.GRN}{ok}개 성공{C.R}"
        if fail:
            msg += f", {C.RED}{fail}개 실패{C.R}"
        print(f"{C.B}끝.{C.R} {msg}  {C.DIM}→ {args.out}{C.R}")
        # 파인더에서 폴더 열기 (성공 시)
        if ok and sys.platform == "darwin":
            subprocess.call(["open", args.out])


if __name__ == "__main__":
    main()
