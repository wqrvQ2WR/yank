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

### 제목으로 검색해서 받기

URL 대신 검색어를 넣으면 유튜브를 검색해 목록을 보여주고, 번호로 골라 받는다.

```bash
yank 뉴진스 하입보이        # URL이 아니면 자동으로 검색 모드
yank -s "aespa spicy"     # 검색 모드 명시
yank -s 로파이 --mp3 -r 20  # 20개 검색해서 고른 걸 mp3로
```

목록이 뜨면 번호를 고른다 — `1` (하나), `1-3` (범위), `1 3 5` (여러 개), `a` (전체), `q` (취소):

```
"뉴진스 하입보이" 검색 결과 10개:

   1  NewJeans (뉴진스) 'Hype Boy' Official MV
      ⏱ 3:24   HYBE LABELS   조회 4.2억
   2  ...

번호 선택 (예: 1 · 1-3 · 1 3 5 · a=전체 · q=취소):
```

## 옵션

| 옵션 | 설명 |
|------|------|
| `-s`, `--search` | 인자를 URL이 아닌 검색어로 취급 (유튜브 검색) |
| `-r`, `--results` | 검색 결과 개수 (기본 10) |
| `--mp3` | 영상 대신 오디오(mp3, 최고 품질)만 추출 |
| `-q`, `--quality` | 최대 화질: `480` / `720` / `1080` / `1440` / `2160` / `best` (기본 `best`) |
| `-o`, `--out` | 저장 폴더 (기본 `~/Downloads/yank`) |
| `-n`, `--name` | 파일명 템플릿 (yt-dlp 형식, 기본 `%(title)s.%(ext)s`) |
| `--audio-format` | mp3 대신 다른 오디오 포맷 (`m4a`/`opus`/`wav` 등) |
| `--no-playlist` | 재생목록 url이어도 그 영상 하나만 |
| `--keep` | 변환 후 원본도 남김 |
| `--list` | 받지 말고 사용 가능한 포맷만 표시 |

## 크롬 확장 — 유튜브에서 버튼으로 받기

유튜브 영상 아래 좋아요·공유 옆에 **MP4 / MP3** 버튼을 붙인다.

확장 자체는 다운로드를 못 한다. 유튜브는 영상과 오디오 스트림이 분리(DASH)돼 있어
합치려면 ffmpeg 가 필요한데, 브라우저 안에서는 못 돌린다. 그래서 버튼은 로컬에 떠 있는
`server.py` 로 요청만 쏘고, 실제 작업은 여태 쓰던 yt-dlp 파이프라인(`build_cmd`)이 그대로 한다.

```
크롬 버튼  ──►  127.0.0.1:7979 (server.py)  ──►  yt-dlp + ffmpeg  ──►  ~/Downloads/yank
```

### 1. 서버 켜기

```bash
python3 ~/Desktop/폴더임/capp/yank/server.py
```

| 옵션 | 설명 |
|------|------|
| `-p`, `--port` | 포트 (기본 7979) |
| `-o`, `--out` | 저장 폴더 (기본 `~/Downloads/yank`) |

브라우저로 <http://127.0.0.1:7979> 를 열면 서버 상태(yt-dlp·ffmpeg 유무, 저장 위치)와
진행 중인 작업 목록을 볼 수 있다. 다운로드는 여기서 못 하고, 유튜브의 버튼으로 한다.

#### 자동 실행 (LaunchAgent)

`com.yank.server.plist` 를 걸어두면 로그인할 때 알아서 뜨고, 죽어도 되살아난다(`KeepAlive`).

```bash
cp ~/Desktop/폴더임/capp/yank/com.yank.server.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.yank.server.plist
```

| 하려는 것 | 명령 |
|-----------|------|
| 상태 확인 | `launchctl list \| grep yank` |
| 재시작 (코드 고친 뒤) | `launchctl kickstart -k gui/$(id -u)/com.yank.server` |
| 끄기 | `launchctl bootout gui/$(id -u)/com.yank.server` |
| 로그 | `tail -f /tmp/yank-server.log` |

plist 안에 홈 디렉터리 경로와 homebrew `PATH` 가 박혀 있다. 폴더를 옮기면 plist 도 같이 고치고
`bootout` → `bootstrap` 을 다시 해야 한다.

자동 실행을 안 쓸 거면 그냥 필요할 때 `python3 server.py` 로 띄워도 된다.

### 2. 확장 설치

1. 크롬에서 `chrome://extensions` 열기
2. 오른쪽 위 **개발자 모드** 켜기
3. **압축해제된 확장 프로그램을 로드합니다** → `yank/extension` 폴더 선택

웹스토어에는 못 올린다 — 유튜브 다운로더는 스토어 정책 위반이라 심사에서 떨어진다.
개발자 모드로 직접 로드해서 쓰는 용도.

### 3. 쓰기

유튜브 영상 페이지에 뜨는 **MP4** / **MP3** 버튼을 누르면 된다.

- 버튼이 진행률 게이지로 바뀐다. mp4 는 영상·음성을 따로 받아서 게이지가 두 번 찬다 (툴팁에 어느 쪽인지 표시)
- 다 받으면 초록색 **폴더 열기** 로 바뀐다. 누르면 파인더에서 파일을 띄운다
- 툴바의 yank 아이콘을 누르면 서버 상태, MP4 최대 화질, 포트를 바꿀 수 있다
- 재생목록 페이지에서 눌러도 그 영상 하나만 받는다

### 안전장치

로컬 서버라 아무 사이트나 부를 수 있으면 곤란하니 이렇게 막아뒀다:

- `127.0.0.1` 에만 바인딩 (외부에서 접근 불가)
- 유튜브 도메인 요청만 수락 (`Origin` 검사)
- 유튜브 URL 만 다운로드 (그 외 주소는 400)

### 확장 파일

| 파일 | 역할 |
|------|------|
| `extension/content.js` | 유튜브 액션 줄에 버튼 주입, 진행률 폴링 |
| `extension/content.css` | 버튼·토스트 스타일 |
| `extension/background.js` | 서비스 워커. 콘텐츠 스크립트는 CORS 때문에 localhost 를 직접 못 불러서 여기를 경유한다 |
| `extension/popup.html/js` | 서버 상태·화질·포트 설정 |
| `server.py` | 로컬 HTTP 서버. `yank.py` 의 `build_cmd` 재사용 |

## 라이선스

MIT
