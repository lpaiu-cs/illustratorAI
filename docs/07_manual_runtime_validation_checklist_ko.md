# Manual Runtime Validation Checklist

## 1. 전제

이 문서는 사람이 macOS에서 Krita를 직접 실행해 검증하는 절차다. Codex는 이 절차를 대신 수행하지 못한다.

## 2. Codex가 이미 끝낸 항목

- dev install script 작성
- bootstrap/path resolution 코드 추가
- dry-run mode 구현
- report 구조 강화
- pytest 기반 비-Krita 검증

## 3. 사람이 해야 하는 검증 항목

### 설치

1. 터미널에서 `scripts/dev/install_plugin_dev_mac.sh` 실행
2. `python scripts/dev/print_krita_dev_paths.py` 실행
3. 출력된 `desktop_target`, `plugin_target_dir`가 기대 경로인지 확인

### Krita 로딩

1. Krita 실행
2. `Settings -> Configure Krita... -> Python Plugin Manager` 열기
3. `native_illustration_compiler`가 목록에 보이는지 확인
4. 비활성화되어 있다면 체크
5. Krita 재시작

### 메뉴 액션

1. `Tools -> Scripts` 열기
2. 아래 3개 액션이 보이는지 확인
3. `Compile IR JSON to New Document`
4. `Compile Bundled Demo`
5. `Export Active Document Manifest`

### bundled demo compile

1. `Compile Bundled Demo` 실행
2. `demo_anime_bust.json` 선택
3. output directory 선택 또는 취소해서 기본 dev output root 사용
4. compile가 시작되는지 확인
5. report dialog에 output root / report path가 표시되는지 확인

### 산출물 확인

1. output root 아래 `.kra` 존재 확인
2. preview `.png` 존재 확인
3. `*_compile_report.json` 존재 확인
4. report의 `self_check`, `capability`, `path_resolution`, `compile_summary` 확인

### 재오픈/manifest

1. 생성된 `.kra`를 Krita에서 다시 열기
2. 레이어/그룹/마스크/벡터 구조 확인
3. `Export Active Document Manifest` 실행
4. manifest JSON 생성 확인

## 4. 실패 시 우선 확인할 것

- Plugin Manager에서 hover tooltip에 import error가 보이는지
- bootstrap log가 생성되었는지
- `print_krita_dev_paths.py`의 target 경로가 실제 Krita resource root와 맞는지
- output root에 쓰기 권한이 있는지
- report의 `self_check`에서 fail 항목이 무엇인지

## 5. 통과 기준

- 플러그인이 Manager에 표시됨
- Tools -> Scripts에 액션 3개가 보임
- bundled demo가 import/path 오류 없이 시작됨
- report가 output root에 남음
- `.kra` 또는 명확한 실패 report 둘 중 하나가 남음

