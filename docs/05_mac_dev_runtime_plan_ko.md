# Krita Mac Dev Runtime Plan

## 1. 이번 단계의 목적

이번 단계의 목적은 기능 확장이 아니라 macOS 개발 환경에서 Krita 플러그인이 실제로 로드되고, repo의 `src/` 코어와 연결되며, 실패 시 진단 가능한 상태를 만드는 것이다.

## 2. dev mode 원칙

- 플러그인 설치는 copy가 아니라 symlink 기반 dev mode를 기본으로 한다.
- `pykrita/native_illustration_compiler`는 Krita 전용 얇은 wrapper로 유지한다.
- 실제 비즈니스 로직은 계속 `src/nic_ir`, `src/nic_compiler`에 둔다.
- 플러그인 bootstrap은 `__file__.resolve()` 기준으로 repo root를 찾는다.
- 경로 해석 실패나 import 실패는 bootstrap log에 남기고 예외를 삼키지 않는다.

## 3. 현재 구현 기준의 검증 분리

### Codex가 이번에 실제로 검증한 것

- 순수 Python 테스트
- path resolution
- examples/assets 존재 여부
- dry-run report 생성
- dev install script 정합성

### Codex가 이번에 검증하지 못한 것

- Krita.app 실제 실행
- Python Plugin Manager 노출 여부
- Tools -> Scripts 메뉴 액션 실노출 여부
- 실제 `.kra` 생성
- 실제 manifest export 실행

## 4. 개발 모드 배포 구조

- Krita resource root: `~/Library/Application Support/Krita/`
- dev install target: `~/Library/Application Support/Krita/pykrita/`
- symlink 대상:
  - `native_illustration_compiler.desktop`
  - `native_illustration_compiler/`
- bootstrap은 repo `src/`를 `sys.path`에 추가한다.

## 5. output 정책

- output root는 compile 시작 시 한 번만 결정한다.
- 사용자가 output directory를 선택하면 그 경로를 쓴다.
- 사용자가 취소하면 기본값으로 `PROJECT_ROOT/.nic_dev_build/<source_stem>/`를 쓴다.
- export 파일은 IR의 `file_name`에서 디렉터리 부분을 무시하고 leaf filename만 사용한다.
- report는 항상 output root 아래에 쓴다.

## 6. self-check 전략

실행 전 아래 항목을 점검한다.

- project root / src / examples / assets 존재
- 필수 Python 모듈 import 가능 여부
- source IR 존재 여부
- output root 쓰기 가능 여부
- Krita API import 가능 여부
- brush API probe 가능 여부
- transform payload 미지원 사실

## 7. 단계별 완료 기준

1. dev install script로 macOS Krita resource root에 symlink 설치 가능
2. plugin bootstrap failure가 log에 남음
3. dry-run report가 output root에 기록됨
4. 사람이 Krita에서 메뉴 액션 노출과 demo compile을 검증할 수 있음

