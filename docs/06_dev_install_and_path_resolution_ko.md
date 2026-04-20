# Mac Dev Install And Path Resolution

## 1. 설치 스크립트

- 설치: [install_plugin_dev_mac.sh](/Users/lpaiu/vs/lab/illustratorAI_krita/scripts/dev/install_plugin_dev_mac.sh)
- 제거: [uninstall_plugin_dev_mac.sh](/Users/lpaiu/vs/lab/illustratorAI_krita/scripts/dev/uninstall_plugin_dev_mac.sh)
- 경로 출력: [print_krita_dev_paths.py](/Users/lpaiu/vs/lab/illustratorAI_krita/scripts/dev/print_krita_dev_paths.py)

기본 대상 경로는 `~/Library/Application Support/Krita/pykrita/`다. Krita 문서의 resource folder 기준도 macOS에서 이 경로를 사용한다.

## 2. 설치 방식

스크립트는 아래 두 항목을 symlink로 설치한다.

- `pykrita/native_illustration_compiler.desktop`
- `pykrita/native_illustration_compiler/`

이미 같은 위치에 실제 파일/디렉터리가 있으면 덮어쓰지 않고 실패한다. dev mode에서 기존 사용자 설치본을 조용히 손상시키지 않기 위한 보호다.

## 3. project root 해석

project root는 다음 순서로 찾는다.

1. `NIC_DEV_PROJECT_ROOT` 환경 변수
2. 명시적으로 전달된 root
3. 현재 anchor 파일의 `resolve()` 경로에서 상위 디렉터리로 올라가며 marker 검사

marker 조건은 다음을 동시에 만족하는 디렉터리다.

- `pyproject.toml`
- `src/nic_compiler`
- `src/nic_ir`
- `pykrita`
- `examples`

## 4. dev mode에서의 경로 기준

- `src_root`: `PROJECT_ROOT/src`
- `examples_root`: `PROJECT_ROOT/examples`
- `assets_root`: `PROJECT_ROOT/examples/assets`
- `logs_root`: `PROJECT_ROOT/.nic_dev_logs`
- 기본 `output_root`: `PROJECT_ROOT/.nic_dev_build/<source_stem>`

## 5. output 파일 해석 규칙

- export는 모두 `output_root` 아래에 쓴다.
- IR의 export `file_name`은 basename만 사용한다.
- 예:
  - `demo_anime_bust.kra`
  - `demo_anime_bust_preview.png`
  - `demo_anime_bust_compile_report.json`

즉, IR에 `examples/build/...` 같은 repo-relative 경로를 넣어도 실제 저장 위치는 output policy가 결정한다.

## 6. bootstrap failure 로그

플러그인 bootstrap 실패 시 로그는 임시 디렉터리 아래에 남긴다.

- log path: `tempdir/native_illustration_compiler/bootstrap.log`

이 로그에는 project root 탐색 실패, import failure, manifest export failure 같은 Krita 초기 진입 오류가 남는다.

