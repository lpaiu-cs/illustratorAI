# Krita Native Illustration Compiler v0 프로젝트 계획

## 1. 목적

이번 버전의 목표는 에이전트형 드로잉 시스템이 아니라, 구조화된 IR(JSON)을 받아 Krita 네이티브 `.kra` 문서를 생성하는 결정론적 컴파일러를 만드는 것이다. 결과물은 사람 일러스트레이터가 Krita에서 다시 열어 레이어, 그룹, 벡터, 일부 마스크 구조를 유지한 채 후편집할 수 있어야 한다.

## 2. 비목표

- 프롬프트 기반 이미지 생성
- UI 자동화, 화면 클릭, 키 입력 재현
- 외부 네트워크 호출
- 멀티 백엔드 지원
- 라이브 텍스트 레이어 자동 생성
- RL, 모델 학습, 추론 서버 연동

## 3. v0 타깃

- Krita 5.3.1 desktop
- Krita Extension 기반 Python 플러그인
- 주 출력 포맷: `.kra`
- 보조 출력 포맷: `.png`, 선택적 `.psd`
- 안정성 우선 구현 범위: `RGBA` + `U8`

## 4. 핵심 요구사항

1. 새 문서를 생성한다.
2. 그룹/페인트/벡터 레이어 트리를 결정론적으로 구성한다.
3. 레이어 이름, 순서, 가시성, 불투명도, 블렌딩 모드, 잠금, inherit alpha를 반영한다.
4. selection/transparency/transform mask를 최소 단위로 생성한다.
5. 래스터 오퍼레이션은 `setPixelData()` 중심으로 구현한다.
6. 벡터 오퍼레이션은 `addShapesFromSvg()` 중심으로 구현한다.
7. 실패와 미지원 항목을 compile report에 남긴다.

## 5. 단계

### Phase 1

- 프로젝트 문서화
- IR 스키마 고정
- 검증 전략 수립

### Phase 2

- Krita 플러그인 뼈대
- 메뉴 액션 노출
- JSON 선택 및 새 문서 생성
- 빈 레이어 트리 생성

### Phase 3

- IR validator
- 레이어 빌더
- raster/vector/mask/export 연산
- compile report 작성

### Phase 4

- `demo_anime_bust.json`
- `demo_vector_accessories.json`
- 예제 asset 정리

### Phase 5

- pytest 기반 순수 Python 테스트
- Krita 수동 스모크 테스트 문서화

## 6. 설계 원칙

- 문서 컴파일러 우선: `IR -> Krita document`
- Krita 의존부 최소화
- 순수 Python 코어 분리
- 같은 입력에 같은 결과
- 미지원 기능은 조용히 누락하지 않고 보고

## 7. 주요 리스크와 대응

### 브러시 API 버전 차이

- 런타임 feature detection 사용
- 지원 시 Krita 브러시 API 사용
- 미지원 시 픽셀 기반 fallback 또는 unsupported 기록

### 마스크 API 범위 제한

- selection/transparency mask는 Selection 기반 데이터 주입 지원
- transform mask는 우선 생성 중심으로 구현
- 상세 transform 적용은 추후 확장 포인트로 분리

### PSD export 과신

- `.kra`를 정본으로 유지
- PSD는 secondary export
- PSD export 성공/실패/누락 가능성을 report에 기록

## 8. 완료 기준

- 예제 IR에서 `.kra`와 `.png`가 생성된다.
- Krita에서 문서를 다시 열 수 있다.
- 구조적 레이어 트리가 유지된다.
- compile report가 생성된다.
- 브러시 관련 API 차이가 전체 컴파일 실패로 번지지 않는다.

