# yank

유튜브(및 [yt-dlp](https://github.com/yt-dlp/yt-dlp)가 지원하는 1000여 개 사이트) 영상을 **mp4** 또는 **mp3**로 뽑아오는 단일 파일 CLI.

`yt-dlp` + `ffmpeg`를 감싸서 기본값·컬러 출력·썸네일/메타데이터 임베드·파일명 정리까지 알아서 해준다. 받은 파일은 기본으로 `~/Downloads/yank`에 저장되고, 다 받으면 폴더가 자동으로 열린다(macOS).

## 설치

의존성 두 개만 있으면 된다:

```bash
brew install yt-dlp ffmpeg
```

그리고 `yank.py`를 내려받아 별칭을 걸어두면 끝:

```bash
alias yank='python3 "/경로/yank/yank.py"'
```

## 사용법

```bash
yank <url>              # 최고 화질 mp4 (썸네일·메타데이터·자막 임베드)
yank <url> --mp3        # 오디오만 mp3 (앨범아트 커버 임베드)
yank <url> -q 1080      # 화질 상한 (480/720/1080/1440/2160/best)
yank <url> -o ~/폴더     # 저장 위치 지정
yank url1 url2 ...      # 여러 개 한 번에
yank <재생목록 url>      # 재생목록 통째로
```

## 옵션

| 옵션 | 설명 |
|------|------|
| `--mp3` | 영상 대신 오디오(mp3, 최고 품질)만 추출 |
| `-q`, `--quality` | 최대 화질: `480` / `720` / `1080` / `1440` / `2160` / `best` (기본 `best`) |
| `-o`, `--out` | 저장 폴더 (기본 `~/Downloads/yank`) |
| `-n`, `--name` | 파일명 템플릿 (yt-dlp 형식, 기본 `%(title)s.%(ext)s`) |
| `--audio-format` | mp3 대신 다른 오디오 포맷 (`m4a`/`opus`/`wav` 등) |
| `--no-playlist` | 재생목록 url이어도 그 영상 하나만 |
| `--keep` | 변환 후 원본도 남김 |
| `--list` | 받지 말고 사용 가능한 포맷만 표시 |

## 라이선스

MIT
