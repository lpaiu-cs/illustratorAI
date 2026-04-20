# Krita Native Illustration Compiler v0 검증 계획

## 1. 검증 목표

validator는 잘못된 IR을 조용히 통과시키지 않고, 구조 오류와 의미 오류를 가능한 한 빠르게 드러내야 한다. compile 단계는 Krita 런타임 capability 차이를 unsupported 이벤트로 분리해야 하며, 전체 파이프라인은 실패 지점을 report에 남겨야 한다.

## 2. 정적 검증

### 구조 검증

- 최상위 필수 키 존재 여부
- `document` 필수 필드 타입
- `layers`/`children`/`masks`/`ops` 배열 구조
- `resources`/`exports` 항목 형태

### 의미 검증

- 레이어/마스크/리소스 ID 중복 금지
- 지원 레이어 타입 검증
- 레이어 타입별 허용 op 검증
- `import_png`, `add_svg`의 리소스 참조 무결성 검증
- 색상 문자열 형식 검증
- `opacity` 범위 검증
- workspace 경계 밖 파일 경로 금지

### 구현 범위 검증

- v0에서 허용하지 않는 색공간 조합 거부
- live text 관련 필드 거부
- transform mask 상세 적용값은 경고 또는 unsupported 예정 항목으로 분류

## 3. 컴파일 시점 검증

- Krita runtime 존재 여부
- 브러시 API (`paintLine`, `paintPath`) 존재 여부
- `addShapesFromSvg()` 존재 여부
- paint layer에만 `setPixelData()`를 적용하는지 검증

## 4. 리포팅 전략

compile report에는 아래를 남긴다.

- 입력 IR 파일 경로
- workspace root
- runtime capability snapshot
- 생성 문서 메타데이터
- outputs
- warnings
- unsupported
- errors

## 5. 자동 테스트

### `tests/test_ir_validator.py`

- 정상 IR 검증
- 잘못된 레이어 타입 거부
- 잘못된 resource 참조 거부

### `tests/test_layer_tree_planning.py`

- bottom-to-top 순서 유지
- 그룹 경로 계산
- flatten된 계획 결과 검증

### `tests/test_color_parsing.py`

- `#RGB`, `#RGBA`, `#RRGGBB`, `#RRGGBBAA`
- `transparent`
- 잘못된 색상 포맷 예외

## 6. 수동 스모크 테스트

- Krita 5.3.1에서 플러그인 인식 여부
- demo compile 실행
- 저장된 `.kra` 재오픈
- 레이어 이름/순서/opacity/blend mode 확인
- selection/transparency/transform mask 존재 확인
- preview PNG 생성 확인
- PSD export가 켜져 있을 때 보조 결과 확인

## 7. 합격 기준

- validator가 잘못된 IR을 명시적으로 거부한다.
- pytest가 순수 Python 영역에서 통과한다.
- Krita 수동 테스트에서 최소 하나의 demo가 `.kra` + `.png`를 생성한다.
- 브러시 API 부재가 fatal error가 아니라 warning/unsupported 또는 fallback으로 처리된다.
