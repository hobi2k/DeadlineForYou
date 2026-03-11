# OpenCode, Claude Code, Codex 설치 및 설정 가이드

기준일: 2026-03-11

이 문서는 `OpenCode`를 먼저 설치한 뒤, `Claude Code`와 `Codex`를 추가로 설치하고 기본 설정까지 마치는 흐름을 정리한다.

문서 목적은 세 가지다.

1. 세 도구를 빠르게 설치한다.
2. 각각 어떤 인증 방식과 실행 방식이 필요한지 정리한다.
3. 실제 개발 환경에서 어떻게 같이 쓸지 기준을 잡는다.

## 1. 도구별 역할 요약

### OpenCode

- 오픈소스 AI 코딩 에이전트
- 터미널 중심
- 여러 LLM provider를 연결해 쓸 수 있음
- IDE 터미널에서 실행하면 확장 기능이 자동 설치될 수 있음

### Claude Code

- Anthropic의 터미널 기반 코딩 에이전트
- Claude 계정 또는 Anthropic Console 계정으로 인증
- 코드 탐색, 수정, 설명, 계획 수립에 강함

### Codex

- OpenAI의 터미널 기반 코딩 에이전트
- ChatGPT 로그인 또는 OpenAI API 기반 사용 가능
- 로컬에서 파일을 읽고 수정하며 에이전트형으로 동작

## 2. 사전 준비

세 도구를 설치하기 전에 아래를 먼저 확인한다.

- 운영체제: macOS / Linux 권장
- Windows: 가능하면 WSL 사용
- Node.js: `18+` 권장
- 터미널: 최신 터미널 권장
- 네트워크: Claude Code와 Codex는 인증 시 인터넷 필요

Node.js 확인:

```bash
node -v
npm -v
```

설치가 안 되어 있으면 먼저 Node.js를 설치한다.

## 3. OpenCode 설치

공식 문서 기준으로 가장 간단한 설치 방법은 설치 스크립트다.

```bash
curl -fsSL https://opencode.ai/install | bash
```

대안:

```bash
npm install -g opencode-ai
```

Homebrew를 쓰는 경우:

```bash
brew install anomalyco/tap/opencode
```

설치 확인:

```bash
opencode --version
```

*버전 확인이 안 될 시

```bash
source ~/.bashrc
```

## 4. OpenCode 초기 설정

OpenCode는 사용할 LLM provider 키를 연결해서 쓴다.

가장 쉬운 흐름은 TUI 안에서 `/connect`를 실행하는 방식이다.

```bash
opencode
```

실행 후:

```text
/connect
```

그 다음:

1. provider 선택
2. 안내된 인증 페이지 이동
3. 로그인 및 과금/키 설정
4. 다시 TUI로 돌아와 연결 완료

### IDE 연동

VS Code, Cursor, Windsurf, VSCodium 같은 IDE의 통합 터미널에서 `opencode`를 실행하면 확장 기능이 자동 설치될 수 있다.

즉:

1. IDE 열기
2. 내장 터미널 열기
3. `opencode` 실행

자동 설치가 안 되면 마켓플레이스에서 `OpenCode` 확장을 수동 설치한다.

## 5. Claude Code 설치

Claude Code는 공식 문서 기준으로 `npm` 설치가 기본이다.

```bash
npm install -g @anthropic-ai/claude-code
```

주의:

- `sudo npm install -g`는 권장되지 않는다.
- 권한 문제가 있으면 npm 전역 디렉터리 설정을 먼저 정리하는 편이 낫다.

설치 확인:

```bash
claude --version
```

### Claude Code 대안 설치

Anthropic 문서에는 네이티브 설치 베타도 안내되어 있다.

macOS / Linux / WSL:

```bash
curl -fsSL claude.ai/install.sh | bash
```

하지만 관리 일관성을 위해 이미 Node 기반 CLI를 쓰고 있다면 `npm install -g` 방식으로 통일하는 편이 실무상 더 단순하다.

## 6. Claude Code 로그인과 기본 설정

프로젝트 폴더로 이동해서 실행한다.

```bash
cd /path/to/your/project
claude
```

처음 실행하면 인증이 필요하다.

가능한 인증 방식:

- Claude.ai 계정
- Anthropic Console 계정

권장:

- 개인 개발자: Claude.ai 계정
- 팀/과금 관리 필요: Anthropic Console

기본 확인 명령:

```bash
claude doctor
```

IDE 연동은 IDE 터미널에서 `claude`를 실행하면 되고, 공식 연동 기능은 VS Code 계열과 JetBrains 계열을 지원한다.

## 7. Codex 설치

Codex CLI는 OpenAI의 공식 오픈소스 CLI다.

가장 일반적인 설치:

```bash
npm install -g @openai/codex
```

Homebrew 사용 시:

```bash
brew install --cask codex
```

설치 확인:

```bash
codex --version
```

## 8. Codex 로그인과 기본 설정

프로젝트 폴더로 이동한 뒤 실행한다.

```bash
cd /path/to/your/project
codex
```

또는 로그인만 먼저 할 수 있다.

```bash
codex login
```

권장 인증 방식:

- `Sign in with ChatGPT`

이 방식의 장점:

- 수동 API 키 복사 없이 연결 가능
- ChatGPT 요금제와 연계 가능

대안:

- OpenAI API key 기반 사용

### Codex 기본 사용 모드

OpenAI 도움말 기준으로 대표 모드는 다음과 같다.

- 기본 suggest 모드
- `--auto-edit`
- `--full-auto`

예:

```bash
codex --auto-edit
codex --full-auto
```

업데이트:

```bash
codex --upgrade
```

## 9. 설치 순서 권장안

실무에서는 아래 순서가 깔끔하다.

### 1단계

공통 런타임 설치

```bash
node -v
npm -v
```

### 2단계

OpenCode 설치

```bash
curl -fsSL https://opencode.ai/install | bash
```

### 3단계

Claude Code 설치

```bash
npm install -g @anthropic-ai/claude-code
```

### 4단계

Codex 설치

```bash
npm install -g @openai/codex
```

### 5단계

버전 확인

```bash
opencode --version
claude --version
codex --version
```

## 10. 추천 설정 전략

세 도구를 다 설치했다고 해서 무조건 동시에 쓸 필요는 없다.

추천은 역할 분리다.

### OpenCode

추천 용도:

- 여러 provider를 붙여 실험할 때
- 오픈소스 기반 도구를 선호할 때
- IDE 터미널과 자연스럽게 붙이고 싶을 때

### Claude Code

추천 용도:

- 코드베이스 분석
- 구조 설명
- 계획 수립
- 리팩터링 논의

### Codex

추천 용도:

- OpenAI 계정 기반 빠른 사용
- 수정/실행/패치 중심 작업
- OpenAI 쪽 워크플로에 익숙한 경우

## 11. 같이 쓰는 예시 흐름

### 조합 1

OpenCode + Claude Code

- OpenCode: 다양한 모델/provider 실험
- Claude Code: 코드 읽기, 설명, 아키텍처 질문

### 조합 2

OpenCode + Codex

- OpenCode: IDE 친화적 사용
- Codex: 로컬 수정/패치 작업

### 조합 3

세 개 모두 설치

운영 기준:

- OpenCode는 멀티-provider 실험용
- Claude Code는 분석/설계용
- Codex는 실행형 작업용

이렇게 나누면 중복이 줄어든다.

## 12. 트러블슈팅

### `command not found`

원인:

- 전역 설치 경로가 PATH에 안 잡힘

확인:

```bash
npm bin -g
echo $PATH
```

### npm 전역 설치 권한 오류

원인:

- 시스템 전역 npm 경로 권한 문제

대응:

- `sudo npm install -g` 대신 npm prefix 설정 또는 Node 버전 관리자 사용

가장 자주 보는 오류는 이런 형태다.

```text
npm ERR! code EACCES
npm ERR! Error: EACCES: permission denied, mkdir '/usr/local/lib/node_modules'
```

이 뜻은 간단하다.

- npm이 패키지를 전역 설치하려고 함
- 기본 전역 설치 경로가 `/usr/local/lib/node_modules`로 잡혀 있음
- 현재 사용자에게 그 경로에 쓸 권한이 없음
- 그래서 설치가 거부됨

즉, 설치 명령 자체가 틀린 게 아니라 `전역 설치 대상 디렉터리`가 현재 사용자 기준으로 너무 시스템 쪽에 잡혀 있는 것이다.

### 왜 `sudo npm install -g`를 권장하지 않는가

처음 보면 `sudo`만 붙이면 해결될 것 같지만, 보통은 그렇게 하지 않는 편이 맞다.

이유:

- 시스템 전역 Node 패키지와 사용자 패키지가 뒤섞인다
- 나중에 권한 꼬임이 생기기 쉽다
- 삭제 / 업그레이드 / 재설치 때 다시 권한 문제가 반복된다
- 개발 도구 CLI는 보통 사용자 홈 디렉터리 아래에 두는 편이 안전하다

즉, 코딩 도구 CLI를 쓸 때는 `루트 권한으로 강제로 설치`하는 것보다 `사용자 전용 전역 설치 경로`를 잡는 편이 더 안정적이다.

### 권장 해결 방법: 사용자 전역 npm 경로 사용

아래 명령은 npm의 전역 설치 위치를 시스템 디렉터리 대신 사용자 홈 디렉터리 아래로 바꾸는 작업이다.

```bash
mkdir -p ~/.npm-global
npm config set prefix ~/.npm-global
```

의미:

- `~/.npm-global` 디렉터리를 만든다
- 앞으로 `npm install -g`를 했을 때 여기에 설치하도록 npm 설정을 바꾼다

그 다음 PATH에 실행 파일 위치를 추가한다.

```bash
echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

의미:

- 전역 설치된 CLI 실행 파일은 보통 `~/.npm-global/bin` 아래에 생긴다
- 이 경로가 `PATH`에 있어야 `claude`, `codex` 같은 명령을 바로 실행할 수 있다
- `source ~/.bashrc`는 방금 바꾼 PATH를 현재 셸에 즉시 반영하는 단계다

확인:

```bash
npm config get prefix
echo $PATH
```

정상이라면:

- `npm config get prefix` 결과가 `~/.npm-global` 계열로 나온다
- `echo $PATH` 결과 안에 `~/.npm-global/bin`이 포함된다

이제 다시 설치하면 된다.

```bash
npm install -g @anthropic-ai/claude-code
npm install -g @openai/codex
```

설치 확인:

```bash
claude --version
codex --version
```

### 대안: Node 버전 관리자 사용

조금 더 정석적으로 가려면 `nvm`, `fnm`, `mise` 같은 버전 관리자를 써도 된다.

이 방식의 장점:

- Node 버전별 환경 분리 가능
- 전역 패키지 경로가 사용자 영역으로 자연스럽게 정리됨
- 프로젝트별 Node 버전 맞추기 쉬움

하지만 빠르게 문제를 풀어야 한다면, 위의 `~/.npm-global` prefix 방식이 가장 단순하다.

### IDE 자동 연동이 안 됨

대응:

- IDE 내장 터미널에서 실행했는지 확인
- IDE CLI 명령이 PATH에 있는지 확인
- 확장을 수동 설치

### Codex 또는 Claude Code 로그인 문제

대응:

- 브라우저 로그인 세션 확인
- 회사망/프록시 환경 여부 확인
- CLI 최신 버전으로 업그레이드

## 13. 빠른 실행 예시

### OpenCode 실행

```bash
opencode
```

### Claude Code 실행

```bash
cd /path/to/project
claude
```

### Codex 실행

```bash
cd /path/to/project
codex
```

## 14. 추천 결론

설치만 놓고 보면 순서는 이렇게 가는 게 가장 무난하다.

1. OpenCode 설치
2. Claude Code 설치
3. Codex 설치
4. 각 도구 버전 확인
5. 각 도구 로그인 완료
6. IDE 터미널에서 각각 실행해보기

실무 관점에서 가장 덜 헷갈리는 운영 방식은 다음과 같다.

- OpenCode: 멀티-provider/IDE 실험용
- Claude Code: 분석과 설계 중심
- Codex: OpenAI 기반 실행형 작업

## 15. 공식 문서

### OpenCode

- Intro: https://opencode.ai/docs
- IDE: https://opencode.ai/docs/ide/

### Claude Code

- Overview: https://docs.anthropic.com/en/docs/claude-code/overview
- Getting Started: https://docs.anthropic.com/en/docs/claude-code/getting-started
- Quickstart: https://docs.anthropic.com/en/docs/claude-code/quickstart
- IDE Integrations: https://docs.anthropic.com/en/docs/claude-code/ide-integrations

### Codex

- OpenAI Codex CLI Help: https://help.openai.com/en/articles/11096431-openai-codex-ci-getting-started
- Sign in with ChatGPT: https://help.openai.com/en/articles/11381614-codex-codex-andsign-in-with-chatgpt
- 공식 저장소: https://github.com/openai/codex
