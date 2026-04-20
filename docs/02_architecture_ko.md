# Krita Native Illustration Compiler v0 아키텍처

## 1. 아키텍처 개요

시스템은 세 계층으로 분리한다.

1. `nic_ir`
   - IR dataclass
   - JSON schema 상수
   - 구조/의미 검증기
2. `nic_compiler`
   - 순수 Python 계획 단계
   - Krita 세션 어댑터
   - layer/raster/vector/mask/export/report 모듈
3. `pykrita/native_illustration_compiler`
   - Krita Extension 엔트리
   - 파일 선택 및 액션 등록

## 2. 데이터 흐름

1. 플러그인 액션이 IR JSON 경로를 받는다.
2. 컴파일러가 JSON을 로드한다.
3. validator가 dataclass 기반 내부 구조체로 변환한다.
4. layer planner가 레이어 순서와 경로를 계산한다.
5. Krita session이 새 문서를 생성한다.
6. layer builder가 노드/마스크를 만든다.
7. raster/vector ops가 각 레이어 내용을 채운다.
8. export ops가 `.kra`, `.png`, 선택적 `.psd`를 저장한다.
9. reporting이 compile report JSON을 기록한다.

## 3. 모듈 책임

### `src/nic_ir/models.py`

- IR의 표준 내부 표현
- 순회 유틸리티
- validation issue 모델

### `src/nic_ir/schema.py`

- 문서화용 JSON schema 사양
- 지원 타입/오퍼레이션 상수

### `src/nic_ir/validator.py`

- JSON -> dataclass 변환
- 구조 검증
- 리소스/레이어/오퍼레이션 참조 검증
- workspace 경계 검증

### `src/nic_compiler/compiler.py`

- 전체 파이프라인 orchestration
- 예외 처리
- report 생성 및 종료 처리

### `src/nic_compiler/krita_session.py`

- Krita API thin wrapper
- runtime capability detection
- file I/O sandboxing
- document/layer/mask/export 보조 함수

### `src/nic_compiler/layer_builder.py`

- 레이어 순서 계획
- 노드 생성 및 공통 속성 적용

### `src/nic_compiler/raster_ops.py`

- 색상 파싱
- 타일 단위 `setPixelData()`
- 단색 채우기
- 픽셀 블록 쓰기
- PNG import
- 브러시 fallback 드로잉

### `src/nic_compiler/vector_ops.py`

- SVG 문자열 로드
- vector layer 주입

### `src/nic_compiler/mask_ops.py`

- selection/transparency/transform mask 생성
- Selection 기반 데이터 주입

### `src/nic_compiler/export_ops.py`

- export 경로 해석
- `.kra` 저장
- `.png`/`.psd` export

### `src/nic_compiler/reporting.py`

- warning/error/unsupported/output 이벤트 축적
- JSON report serialization

## 4. 결정론

- IR 배열 순서는 bottom-to-top으로 정의한다.
- export 파일명은 IR 또는 기본 규칙으로 결정한다.
- runtime capability는 브러시 관련 분기에서만 사용하고, 결과는 report에 남긴다.
- 시간 의존 값은 report 메타데이터에만 포함하고 문서 구조에는 개입하지 않는다.

## 5. 파일 I/O 경계

- 플러그인 내부 파일 I/O는 workspace root 이하만 허용한다.
- 기본 workspace root는 선택한 IR JSON 파일의 부모 디렉터리다.
- resource path와 export path는 모두 workspace root 이하 상대 경로를 권장한다.
- 경계를 벗어나는 절대/상대 경로는 validator 또는 session에서 거부한다.

## 6. v0에서 의도적으로 제한하는 부분

- 문서 색공간: `RGBA` + `U8`
- live text layer 미지원
- transform mask 상세 변환 적용 미지원
- brush API는 존재할 때만 사용
- 브러시 부재 시 픽셀 기반 선 그리기 fallback 사용

## 7. 향후 확장 포인트

- Krita 6.x 전용 브러시/도형 API 확장
- 더 많은 색공간/비트심도
- ColorizeMask, filter layer, fill layer 지원
- manifest 기반 round-trip export/import
- 다중 백엔드 어댑터

