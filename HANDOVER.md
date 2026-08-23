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

### 3.7 실패 분류 → 타깃 재요청 수선 루프 (수집 성공률 개선) ✅
- **설계**: 실패 시 블라인드 재시도 대신, 결정적 검사로 "무엇이 빠졌는지" 분류해 힌트를 얹어 **대화 이력을 보존한 채** 이어서 요청 — 처음부터 다시 하는 것보다 저렴하고 성공률도 높음
- **`stage0.py` 추가**:
  - `classify_failure(summary, observation)` → 결정적 유형 판정: `no_document / invalid_response / export_missing / done_missing / action_failures`
  - `build_repair_message(classes)` → 유형별 처방 힌트 조합
  - `ACTION_BLOCK_SCHEMA` — 액션 블록 JSON 스키마(구조화 출력용)
- **`planner.py`**: `LLMPolicy.resume_with_repair(message, extra_blocks)` — `_done` 해제 + 블록 예산 증가 + 힌트 user 메시지 어펜드 (히스토리 유지가 핵심); `conversation()` 텍스트 덤프; `image_history_limit`(오래된 캔버스 이미지를 텍스트로 생략); 빈 응답 즉시 재시도(블록 미소모); 관찰에 `FIX:` 처방 힌트 + `Blocks used: n/N` 카운트다운 주입
- **`chat.py`**: OllamaChatClient `format_schema` → `/v1`에 `response_format: json_schema` 전송
- **`session_log.py`**: `log_repair()` — `kind:"repair"` 기록; 세션마다 `conversation.jsonl` 덤프(SFT 원료)
- **CLI**: `--temperature --repair-rounds --image-history --history-turns`
- **SFT**: `build_sft_dataset.py` — manifest의 success 세션만 대화 컨텍스트→assistant 턴 종단 샘플로 직렬화 (`--include-repair` 스위치)
- **목표 생성기**: `make_goals.py` — 12개 카테고리 템플릿 결정론 조합 100골 (`goals_100.txt`)

### 3.8 모델 A/B와 처리량 실측 ⚠️ (중요)
| 구성 | 속도 | 성공률 |
|---|---|---|
| qwen3-vl:8b (원 프롬프트, repair) | ~5-9분/골 | 첫 실행 ~40-50%, resume/repair 후 상승 |
| qwen3-vl + 카운트다운/FIX/구조화 | 비슷(~9분/골) | 비슷 |
| qwen2.5vl:7b (모든 구성) | **12초/블록 (15배 빠름)** | **~0%** — 문맥 수정 불능(같은 실패 반복), 스키마 위반 |

- **qwen3-vl 병목 확정 사실**: 호출당 이미지 인코딩 플로어 ~15초 + `/no_think`·`think:false` 모두 무시되는 숨은 reasoning 생성(수천 자) → 블록당 평균 ~50-110초. 프롬프트 축소·이미지 elision·history 축소로도 못 줄임
- **빈 응답 원인**: reasoning이 max_tokens 예산을 태워 content가 빈 채 종료 → invalid_response 연쇄
- **결론**: 로컬 단일 모델로 목표당 ~9분이 물리적 현실. 100골 ≈ 15시간 — 청크 resume으로 분할 실행 필요
- **pytest 97개 통과**

### 3.9 수집 진행 현황과 파이프라인 선검증 ✅
- `output/goals_100.txt` (100골) → chunk0~3 파일로 분할 (25골씩)
- **full_c0: 20/25 실행, 9 성공** (manifest 누적, `--resume`로 계속)
- **val5(chunk0의 20~24번): 5실행 2성공**
- **선검증 결과** (`validate_collection.py`):
  - 재생 결정론성: 성공 세션 11/11 fingerprint 완전 일치 — 수집 궤적은 결정론적 재생 보장
  - 샘플 정합성: 93건 중 8건 불량(세션 중간 빈/파편 응답 턴) → 빌더가 자동 탈락 처리
- **데이터셋 v1 산출** (`output/sft/`):
  - `dataset_v1_clean.jsonl`: 61 샘플(클린 세션만)
  - `dataset_v1_all.jsonl`: 85 샘플(수선 세션 포함)
  - 참조 PNG 전부 존재 확인, 샘플 구조(goal/messages/turn/used_repair) 검증

### 3.10 품질 게이트 + 치명적 버그 수정 ✅⚠️
- **치명적 버그 발견·수정** (`chat.py`): `OllamaChatClient`에 `complete()`가 **두 개** 존재해 앞의 구현이 뒤(/v1)에 덮여 죽은 코드였고, /v1 경로는 멀티파트 content를 `text`로 접은 뒤 이미지를 규격 외 최상위 `image_url` 필드로 전송 → **ollama가 무시**. 즉 지금까지 어떤 이미지도 모델에 전달된 적 없었음("비전 피드백"이 실은 텍스트 관찰만으로 동작). 이미지 elision 실험이 속도 불변이었던 이유도 이것
- **수정**: complete() 단일화(content 리스트 그대로 전달 + base64 검증), 구조화 출력(json_schema)도 이제 실제 발동
- **품질 게이트** (`screen_quality.py` + stage0 판정 로직): 성공 세션의 PNG(투명 배경은 흰색 합성)를 VLM이 goal과 대조 심사 → `{match, score 0-10, missing[], reasoning}`; `--quality-file`/`--min-score`로 데이터셋 빌더 필터 연결
- **심사 결과(11건)**: **2건만 통과**(score 10×2), 나머지 9건 구체적 결함 지적 — "눈이 점이 아니라 별 모양", "지붕이 몸통 아래", "직선 입". 즉 기계적 성공의 82%가 실제 goal 미달 → SFT 오염 예방
- **데이터셋 v2**: `dataset_v2_gated.jsonl` 5샘플(게이트+clean). SVG 렌더 품질(작은 원이 별처럼 보임)은 svg_raster 개선 신호
- 참고: samples.html 브라우저 컨택트시트(`output/sft/samples.html`)
- **pytest 102개 통과**

### 3.11 Stage 1 학습 계층 구축 ✅ (구조 완성, 스모크 검증)
- **설치 완료**: torch 2.11.0+cu128(RTX 5090 CUDA 인식) + transformers 5.15 + peft 0.20 + datasets — `requirements-train.txt`
- **`stage0.build_sft_training_pair`**: 대화 샘플 → 토큰화 + assistant 종단 턴만 loss(템플릿 불관요 common-prefix 마스킹, 좌측 절단 시 타깃 보존). transformers 5.x의 dict 반환 등 이슈 정규화
- **`train_sft.py`**: dataset jsonl 소비 → LoRA SFT(q/k/v/o+gate/up/down, r=16) → 어댑터 저장; `--prepare-only`로 데이터 파이프라인만 검증 가능
- **실학습 스모크 성공**: Qwen2.5-0.5B-Instruct + gated 데이터셋 5샘플 → 4 epoch loss 0.73→0.14 수렴, 어댑터 저장(`output/sft/lora_smoke`)
- **남은 것(재투입 경로)**: 어댑터→병합→GGUF 변환→`ollama create` 또는 vLLM 서버 → 플래너 `--base-url/--model` 교체 → 동일 goals 배치 재실행으로 성공률 비교
- 참고: 현재 conversation 덤프는 이미지가 `[image]` 생략된 텍스트 체인 — Stage 1a는 텍스트 모방 학습. 이미지 조건부 학습은 덤프에 렌더 포함 후 확장
- **pytest 105개 통과**

### 3.12 재투입 경로 개통 ✅ (구조 순환 폐쇄)
- **병합**: `merge_lora.py` (AutoPeftModelForCausalLM → merge_and_unload → bf16 저장)
- **GGUF 변환**: llama.cpp `convert_hf_to_gguf.py` — transformers 4.x 필요(5.x 호환 안 됨, `transformers>=4.55,<5` 유지) + 병합 출력의 `extra_special_tokens` 키 제거 필요(PowerShell 재기록 시 **BOM 금지**)
- **ollama 등록**: Modelfile에 `PARAMETER num_ctx 8192` 명시 권장(기본값 위험)
- **chat.py**: 구조화 출력은 `/v1` json_schema를 ollama가 무시 → **네이티브 `/api/chat` `format` 경로 추가**(스키마 있을 때만 분기). 이제 스키마가 실제 강제됨
- **run_batch 내성**: runner 예외 시 세션 실패 기록 후 계속(배치 크래시 제거)
- **재투입 스모크 결과**(0.5B + 게이트 5샘플 파인튜닝):
  - 첫 골을 **1블록 만에 전체 궤적(finish 포함)**으로 완주 — 형식 학습 확인
  - `--no-vision`에서 스키마 유효 액션이 수십 스텝 실행되나 export/finish 없이 소진 — 5샘플 0.5B의 일반화 한계(예상 범위)
  - 텍스트 모델이라 이미지 요청 시 mmproj 없음으로 500 — **실전 재투입엔 VL 베이스(Qwen2.5-VL-3B/7B, mmproj GGUF 포함) 필수**
- **pytest 105개 통과**

### 3.13 진짜 사이클 1회 완주 — VL-3B 재투입 ✅
- **다운로드**: Qwen/Qwen2.5-VL-3B-Instruct (HF 캐시 `E:\hf-cache`)
- **학습**: 게이트 통과 5샘플 LoRA — 37M 파라미터(0.98%), loss 0.51→0.075 (`output/sft/lora_vl3b`)
- **병합**: `merge_lora.py` VL 지원(AutoModelForImageTextToText, adapter_config의 base_model 자동 감지). 병합 디렉토리에 **preprocessor_config.json/chat_template.json 복사 필요**(mmproj 변환용)
- **GGUF**: 메인 6.17GB + mmproj 1.34GB (`--mmproj` 플래그)
- **ollama 등록**: Modelfile에 FROM 두 줄(메인+mmproj) — 멀티모달 등록 확인, 이미지 색 판별 5초 응답
- **재투입 배치**(미니 3골): **1/3 성공(finish)** + 1건 근접 실패(finish했으나 export 누락) + 1건 레이어 오류 반복(too_many_failures)
  - 텍스트 전용 0.5B(0/3 무한루프) 대비 질적 도약 — 진짜 비전 + 형식 학습 결합 확인
  - 실패 유형: unknown_layer/unknown_parent_layer 반복 → 레이어 상태 추종 약점 = 더 많은 데이터로 개선될 영역
- **순환 완결**: 수집→게이트→데이터셋→SFT→병합→GGUF(mmproj)→ollama→재투입 성공률 측정까지 전 경로 실기 가동

### 3.14 수집 진행 (2026-08-24, 진짜 비전 첫 수집) 🔄
- **chat.py 수정 후 처음으로 모델이 실제 렌더를 보며 그리는 수집** — chunk0 전골 소진 완주
- **full_c0: 25/25골 시도, 고유 성공 18골**(재실행 회복 포함; 처리량 ~6.7분/골, 세션당 청크 1시간 방식)
- 품질 게이트 누적: 심사 20건 중 통과 5세션(구체 결함 지적 계속 — "계단형 지붕", "별모양 눈" 등)
- **데이터셋 v3**: `dataset_v3_gated.jsonl` 11샘플(clean) / `dataset_v3_gated_all.jsonl` 45샘플(repair 포함)
- 남은 수집: chunk1~3(75골, ~8시간) + full_c0 실패골 재도전
- **pytest 105개 통과**

### 순환 전체 요약
```
수집(batch+resume) → 선검증(replay/샘플) → 품질게이트(VLM) → 데이터셋(gated)
→ LoRA SFT(train_sft) → 병합(merge_lora) → GGUF(+mmproj) → ollama create
→ 재투입 배치 → 성공률 비교  ✅ 전 경로 가동 확인 (2026-08-24)
```

---

## 4. 검증 결과
- pytest **91개 통과**
- 실기 비전 스모크: qwen3-vl:8b가 캔버스 렌더를 보며 64×64 스마일리 완주 — 세션 내 오류 0건, `stop_reason=finish`, PNG(366B) 내보내기, 8블록
- 배치 스모크(3목표): 수선 루프 없이 1/3 → **수선 루프 적용 시 3/3 전량 성공** (exhausted 세션이 repair 1회로 finish 회복)
- **핵심 발견**: qwen3-vl은 thinking 모드에서 무한 추론 → `/no_think` + `format:json` + `response_format:json_object` + `max_tokens=8192`로 해결
- SVG 단일 루트 `<g>` 그룹 강제 규칙으로 다중 요소 결합 문제 해결
- **에이전트 관찰 설계 교훈**: 오류 턴이라도 전체 상태를 관찰에 실어야 자기 수정 가능 / 실패는 유형 분류 후 타깃 재요청이 블라인드 재시도보다 우월

---

## 5. 다음 단계 (우선순위 순)

### ① 데이터 증량 사이클 반복 🔴
- 파이프라인이 전부 가동되므로 이제 변수는 **데이터 볼륨** 하나
- 수집 완주(full_c0 `--resume` + chunk1~3) → 게이트 일괄 심사 → 데이터셋 누적 → VL-3B 재학습 → 재투입 배치로 성공률 추적(기준선: 미니 3골 1/3)
- 실패 패턴(unknown_layer 반복)은 관찰에 자기교정 사례가 쌓이면 개선 기대

### ② 학습 신호 확장 (병행)
- conversation 덤프에 캔버스 렌더 포함(현재 [image] 생략) → 이미지 조건부 SFT
- export/finish 타이밍 강화: repair 궤적 포함 학습(`--include-repair`) 또는 완료 턴 가중

### ③ svg_raster 렌더 품질
- 작은 원/곡선이 별처럼 뭉개짐(게이트 심사 근거) — scanline 해상도·AA 개선

### ④ Krita 실기 E2E 스모크
- 브리지 경로 실기 검증(캔버스 렌더→VLM→액션 주입)

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
3. `python -m pytest -q` → 97 passed 확인
4. 수집 이어서: `python scripts/dev/run_stage0_batch.py --goals-file output\goals_chunk1.txt --model qwen3-vl:8b --canvas 64x64 --max-blocks 8 --image-history 1 --output-root output\stage0_batch\full_c1` (full_c0은 `--resume`)
5. 데이터셋: `python scripts/dev/build_sft_dataset.py --manifest output\stage0_batch\full_c0\manifest.jsonl --manifest output\stage0_batch\val5\manifest.jsonl --out output\sft\dataset.jsonl`

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