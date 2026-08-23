# IllustratorAI 세션 핸드오프 문서

## 1. 프로젝트 개요
- **프로젝트**: IllustratorAI (native-illustration-compiler)
- **목표**: LLM이 그림 도구를 토큰처럼 하나씩 짜내어 그리는 에이전틱 드로잉 시스템 구축
- **핵심 아이디어**: LLM이 토큰을 생성하듯, 그림 도구(브러시, 레이어, SVG 등)를 하나씩 호출하여 그림을 그림

## 2. 초기 분석 및 계획 (세션 시작 시)

### 초기 상태 분석
- 저장소: `E:\lab\illustratorAI` (native-illustration-compiler)
- 기존 코드: `nic_compiler` (IR→Kra 배치 컴파일러), `nic_ir` (IR 스키마/검증), `pykrita` (Krita 플러그인)
- 문서: `docs/01~07` 한국어 계획서 존재
- Git: 원격 origin 연결, main 브랜치, 미커밋 변경 없음

### 수립된 3단계 계획
1. **① 비전 피드백** (VLM으로 캔버스 렌더를 보며 그리기)
2. **② 벡터 SVG·그룹 op 확장** (add_svg, vector/group, parent_id)
3. **③ Stage 0 대량 수집 자동화** (데이터 수집 파이프라인)

**순서 근거**: 액션 스페이스(도구)가 먼저 확정되어야(②) 피드백 루프(①)가 의미 있고, 둘 다 안정화된 뒤 대량 수집(③) 진행

---

## 3. 현재까지 완료된 작업

### 3.1 v0 스켈레톤 완성 (`nic_agent` 패키지)
- **프로토콜·실행기·시뮬레이터·세션로그·폐루프·LLM 플래너** 모듈화
- pytest **77개 통과**
- `src/nic_agent/` 하위: `backend`, `chat`, `executor`, `loop`, `models`, `planner`, `policy`, `schema`, `session_log`, `simulator`, `validator`, `svg_raster`

### 3.2 Krita RPC 브리지 (단계 ① 기반)
- `DocumentBackend` 프로토콜로 실행기 추상화 (헤드리스 시뮬레이터 / Krita 백엔드 공용)
- JSON 라인 프로토콜 + QTimer 메인스레드 펌프로 Krita 스레드 안전성 확보
- 재생 바이트 동일성 검증 완료 (결정론적 실행 보장)

### 3.3 벡터 SVG·그룹 op 확장 (2번 완료) ✅
- **액션 추가**: `add_svg {svg:string}` - 벡터 레이어에 SVG 주입
- **레이어 타입 확장**: `kind: "vector" | "group" | "paint"` + `parent_id` 트리 구조
- **svg_raster.py**: 순수 stdlib 최소 SVG 래스터라이저
  - 지원: rect/circle/ellipse/line/polyline/polygon, path(M/L/H/V/C/Q/A/Z)
  - `<g>/<svg>/<defs>` 재귀 + 스타일 상속
  - even-odd scanline fill, 미지원(transform/S/T) → warnings 보고
- 시뮬레이터: 그룹 visible/opacity 캐스케이드 트리 컴포짓
- Krita 백엔드: `addShapesFromSvg` 직주입
- **pytest 77개 통과**

### 3.4 LLM 플래너 Stage 0 (데이터 수집 파이프라인)
- `chat.py`: ChatClient 프로토콜 + OpenAI 호환 + Ollama 네이티브(이중 클라이언트)
- `planner.py`: LLMPolicy 블록큐·피드백 루프, `suppress_thinking` 토큰(`/no_think`)
- `scripts/dev/run_stage0_llm.py`: 데이터 수집 CLI
- **핵심 해결**: qwen3-vl:8b의 thinking 모드 무한 루프 문제 해결
  - **핵심 조합**: `/no_think` 시스템 프롬프트 + `format:json` + `response_format:json_object` + `max_tokens=8192`
  - OpenAI 호환 `/v1/chat/completions` 엔드포인트 사용 (안정적)
  - `max_tokens=8192`로 thinking 완료 후 JSON 완결 보장

### 3.4 실기 스모크 성공 ✅
- **모델**: qwen3-vl:8b (Ollama, 로컬)
- **목표**: 64×64 스마일리(원 외곽선 + 눈 2개 + 미소)
- **결과**: 5블록 만에 `stop_reason=finish`, PNG(329B) 내보내기 성공
- **핵심 조합**: `/no_think` + `format:json` + `response_format:json_object` + `max_tokens=8192`
- SVG 단일 루트 `<g>` 그룹 강제 규칙으로 다중 요소 결합 문제 해결

### 3.5 비전 피드백 완성 (1번 완료) ✅
- **발견**: 멀티모달 파이프라인이 이미 구현돼 있었음 (chat `_split_content_parts`, planner `image_provider`, 백엔드 `canvas_png_base64`, CLI `--no-vision`)
- **VLM 선결과제 불필요**: 주력 `qwen3-vl:8b`가 이름 그대로 비전 모델 — 별도 설치(qwen2.5-vl:7b) 없이 그대로 사용
- **보강 1 — 오류 관찰에 전체 상태 병합** (`loop.py`): 기존엔 실패 턴 관찰이 `{step, error}`뿐이라 레이어 목록을 못 보고 모델이 오류 루프에 빠짐(존재하지 않는 `"root"` parent 반복). 이제 `{step, error, **observe()}`로 상태 포함
- **보강 2 — 프롬프트 규칙 3건 추가** (`planner.py`):
  - 암묵적 root 레이어 없음 → 최상위 레이어는 parent_id 생략
  - add_svg는 **누적** 드로잉 → 맞는 도형 재전송 금지, 누락/수정 부분만
  - 완료 규칙 → 목표 달성+export 성공 후 `{"actions": [], "done": true}` 강제 (재다듬기 방지)
- **실기 비전 스모크 성공**: qwen3-vl:8b, 64×64 스마일리, 세션 내 오류 0건, `stop_reason=finish`, PNG(366B), 8블록
- **pytest 78개 통과** (`test_error_observations_include_full_state` 추가)

### 3.6 Stage 0 대량 수집 자동화 (3번 완료) ✅
- **`stage0.py`** (순수 로직): `load_goals`(주석·빈줄 스킵), `is_collection_success`(ok+finish+PNG 셋), `build_manifest_entry`, `run_batch`(manifest.jsonl 어펜드+flush), `summarize_batch`, `read_manifest`
- **`run_stage0_llm.py` 리팩터**: `run_single_session()` 추출 — 배치가 재사용, 세션마다 `summary.json` 기록
- **`run_stage0_batch.py`**: 목표 파일 일괄 실행 CLI (`--goals-file --limit --resume --no-vision`)
- **성공 판정**: `ok && stop_reason==finish && exported_png 비어있지 않음` — finish해도 export 누락이면 FAIL 처리 확인
- **--resume 검증**: 성공분 스킵, 실패만 재실행 (스모크에서 실패 1건 회복)
- **실기 배치 스모크**(3목표): 1차 1/3 성공 → resume 재실행으로 2/3. 파이프라인은 정상, **모델 변동성이 병목**(같은 스마일리 목표가 실행마다 성패 갈림)
- **pytest 84개 통과** (`test_stage0.py` 6건 추가)

---

## 4. 검증 결과
- pytest **84개 통과**
- 실기 비전 스모크: qwen3-vl:8b가 캔버스 렌더를 보며 64×64 스마일리 완주 — 세션 내 오류 0건, `stop_reason=finish`, PNG(366B) 내보내기, 8블록
- 배치 스모크(3목표): 1차 1/3 → resume 후 2/3 성공, 성공 판정·스킵·재실행 모두 확인
- **핵심 발견**: qwen3-vl은 thinking 모드에서 무한 추론 → `/no_think` + `format:json` + `response_format:json_object` + `max_tokens=8192`로 해결
- SVG 단일 루트 `<g>` 그룹 강제 규칙으로 다중 요소 결합 문제 해결
- **에이전트 관찰 설계 교훈**: 오류 턴이라도 전체 상태(layers 목록 등)를 관찰에 실어야 모델이 자기 수정 가능 — 상태 없는 오류 보고는 복구를 막는다

---

## 5. 다음 단계 (우선순위 순)

### ① 수집 성공률 개선 (최우선) 🔴
- **이유**: 배치 파이프라인은 정상이지만 모델 변동성으로 1차 성공률 ~33% (스마일리 목표조차 실행마다 성패 갈림) — 대량 수집 전에 개선 필요
- **후보**: temperature 낮춤(0.7→0.2~0.4), 실패 시 자동 재시도 예산(k회), finish 누락 시 export_png 자동 보정 여부 검토, 프롬프트 few-shot 예시 추가

### ② 본격 수집 실행
- **준비물**: 목표 프롬프트 세트 파일(100~1000개, 카테고리별) + `run_stage0_batch.py --resume` 반복 실행
- **산출**: manifest.jsonl에서 success=true 세션만 Stage 1 SFT 데이터셋으로 직렬화 (세션 로그 → 액션 시퀀스 + 관찰)

### ③ 벡터 SVG 고급 기능 (품질 개선)
- **대상**: 중첩 그룹, 마스크/클리핑 패스, 그라디언트/패턴 fill — `svg_raster.py` 확장 + Krita `addShapesFromSvg` 매핑

---

## 6. 환경 현황
- **하드웨어**: RTX 5090 32GB VRAM (qwen3-vl:8b/32B, gemma4 등 대형 모델 여유)
- **Ollama 모델**: `qwen3-vl:8b`(주력), `qwen36-hauhau`(21GB), `supergemma4`(18GB), `qwen2.5:7b`, `bge-m3`
- **저장소**: `E:\models` (Ollama 모델 디렉토리, `OLLAMA_CONTEXT_LENGTH=8192` 설정됨)
- **Krita**: 개발용 플러그인 심볼릭 링크 설치済 (`scripts/dev/install_plugin_dev_mac.sh`)

---

## 7. 즉시 재개 시 체크리스트
1. `cd E:\lab\illustratorAI`
2. `ollama ps` → `qwen3-vl:8b` 로드 확인
3. `python -m pytest -q` → 84 passed 확인
4. 단일 비전 스모크: `python scripts/dev/run_stage0_llm.py --goal "Draw a 64x64 smiley face: yellow circle outline, two eyes, a smiling mouth." --model qwen3-vl:8b --client ollama --canvas 64x64 --max-blocks 10 --output-dir output/test_vision`
5. 배치 스모크: 목표 파일 준비 후 `python scripts/dev/run_stage0_batch.py --goals-file <파일> --model qwen3-vl:8b --canvas 64x64 --max-blocks 10 --output-root output/stage0_batch/<이름>` (재실행 시 `--resume`)

---

## 8. 핵심 기술 결정 사항 요약

| 결정 | 내용 | 근거 |
|------|------|------|
| LLM 백엔드 | qwen3-vl:8b (Ollama) | 32GB VRAM에서 8B 안정적, thinking 모드 제어 가능 |
| 통신 프로토콜 | OpenAI 호환 `/v1/chat/completions` | 표준 준수, 멀티모달 지원, 안정적 |
| JSON 강제 | `format:json` + `response_format:json_object` | 파싱 안정성, 중단 없는 파싱 보장 |
| Thinking 제어 | `/no_think` + `max_tokens=8192` | thinking 모드 억제 + 충분한 토큰 예산 |
| SVG 규칙 | 단일 `<g>` 루트 강제 | 다중 요소 결합 시 단일 루트 강제 |
| 비전 피드백 | `image_provider`로 캔버스 렌더 PNG base64 매 턴 첨부 (qwen3-vl:8b) | 별도 VLM 설치 불필요 — 8B 하나가 플래닝+관찰 겸용 |
| 오류 관찰 | 실패 턴 관찰에도 전체 상태(`**observe()`) 병합 | 상태 없는 오류 보고는 모델의 자기 수정을 차단 |
| 완료·누적 규칙 | add_svg 누적 경고 + export 후 `done:true` 강제 | 재전송 스택업과 미완료 루프 방지 |
| 컨텍스트 | `OLLAMA_CONTEXT_LENGTH=8192` | KV 캐시 절약, 속도 2-3배 향상 |

---

*작성일: 2026-08-23 | 작성자: AI Assistant | 저장 위치: `E:\lab\illustratorAI\HANDOVER.md` (커밋 없음)*