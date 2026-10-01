# Handover AI — Prototype v1

스캔 이미지 PDF 기반 인수인계서 자동 작성 및 분석 시스템입니다.
최우선 명세는 [PROTOTYPE_SPEC.md](PROTOTYPE_SPEC.md)이며, 현재 **Phase 1~3 — Project Skeleton / Document Pipeline / LLM Infrastructure**까지 구현했습니다.

## 현재 범위

```text
PDF 업로드 → 파일 검증 → 페이지 PNG 렌더링 → PaddleOCR
→ 페이지별 Raw JSON/SQLite 보존 → SectionMapper → sections/handover_items 저장
```

- FastAPI + Pydantic v2, SQLite + SQLAlchemy 2.x, Alembic
- PyMuPDF 이미지 렌더링 (기본 200 DPI)
- PaddleOCR 3.3.3 + PaddlePaddle 3.2.2 CPU
- `PP-OCRv5_mobile_det` + `korean_PP-OCRv5_mobile_rec`
- React + TypeScript + Vite + React Router: Upload, Documents, 문서 상세
- LLMProvider 추상화, Ollama REST adapter, 공통 JSON/Pydantic 검증, Task별 설정·프롬프트 구현
- 실제 SQL Generation/Retrieval, 문서·문제 생성 서비스, 채점/Python fallback, PDF Export는 이후 Phase 범위
- PP-StructureV3를 호출하거나 별도 필수 의존성으로 사용하지 않습니다.
- PDF 텍스트를 직접 추출하는 처리 경로는 없습니다. 입력은 항상 이미지로 렌더링하여 OCR합니다.

## 준비 및 실행

Python **3.12**, `uv`, Node.js **22.12 이상**, npm이 필요합니다.
검증 환경은 macOS arm64, Python 3.12.14, Node 24.14.0입니다.
의존성은 `backend/uv.lock`, `frontend/package-lock.json`으로 고정합니다.
최초 패키지 설치 및 OCR 모델 다운로드에는 인터넷 연결이 필요합니다.

저장소 루트에서:

```bash
cd backend
cp .env.example .env  # 기존 .env가 있으면 새 설정만 병합
uv sync --locked
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

다른 터미널에서:

```bash
cd frontend
cp .env.example .env  # 기존 .env가 있으면 보존
npm ci
npm run dev
```

- UI: http://127.0.0.1:5173
- API 문서: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/health → `{"status":"ok"}`

**Backend는 단일 worker로 실행하세요.** Prototype은 프로세스 내 BackgroundTasks와 lock으로 문서를 순차 처리합니다. 외부 queue/worker 시스템은 사용하지 않습니다. 자동 reload 중 작업이 중단될 수 있으므로 실제 OCR 검증에서는 `--reload`를 생략합니다.

## 모델 준비

모델은 첫 OCR 요청 시 adapter에서 지연 로딩되며 이후 재사용합니다. health/목록 조회는 모델을 로드하지 않습니다. 기본 PaddleX 캐시에 모델이 없으면 공식 모델 호스트에서 다운로드합니다.

검증 때 사용한 프로젝트 내부 캐시를 재사용하려면 backend 실행 전에:

```bash
# backend/ 기준, PaddleX 라이브러리의 프로세스 환경변수
export PADDLE_PDX_CACHE_HOME="$PWD/data/paddlex"
export PADDLE_PDX_MODEL_SOURCE=BOS
```

`PADDLE_PDX_*`는 라이브러리가 읽는 환경변수이므로 shell에서 export합니다. 이미 다운로드한 모델로 외부 연결 점검을 생략할 경우 `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`를 사용할 수 있습니다.

인터넷이 없는 환경에서는 두 모델 디렉터리를 미리 준비하고 `backend/.env`에 절대 경로를 지정하세요.

```env
OCR_DETECTION_MODEL_DIR=/absolute/path/to/PP-OCRv5_mobile_det
OCR_RECOGNITION_MODEL_DIR=/absolute/path/to/korean_PP-OCRv5_mobile_rec
```

PaddleOCR adapter는 PP-OCRv5 모델명을 명시합니다. 라이브러리 기본 모델이 바뀌어도 자동으로 다른 계열을 선택하지 않습니다. 문서 방향 분류·unwarping·텍스트 방향 모델은 사용하지 않으므로 샘플은 정방향으로 준비하세요.

## API / 실제 샘플 흐름

| API | 동작 |
| --- | --- |
| `GET /api/health` | 프로세스 liveness 확인 |
| `POST /api/documents/upload` | multipart `file`, 검증 후 HTTP 202와 document ID 반환 |
| `GET /api/documents?offset=0&limit=20` | 최근 문서부터 조회, 최대 limit 100 |
| `GET /api/documents/{id}` | 상태·페이지 OCR·섹션·업무 항목·처리 오류 |
| `GET /api/documents/{id}/sections` | 원천 페이지와 순서를 포함한 섹션 |

저장소의 `sample-data/scanned-pdfs/db-handover-scan.pdf`는 2페이지 합성 한국어 이미지 전용 PDF입니다. 실제 기업 기밀 데이터는 없습니다.

1. UI의 **PDF 업로드**에서 샘플을 선택하고 **업로드 및 분석**을 누릅니다.
2. 업로드 파일의 확장자/MIME, PDF signature, PyMuPDF 열기, 암호화/손상, 페이지 수/렌더 크기를 검증합니다.
3. 파일은 UUID 이름으로 저장합니다. 원본 파일명은 표시용으로만 저장합니다.
4. 202 응답 후 문서 상세로 이동합니다. UI는 처리 중인 문서를 2초 간격으로 조회합니다.
5. 페이지를 RGB PNG로 렌더링하고 실제 PaddleOCR를 수행합니다.
6. 엔진 JSON을 파일·DB에 먼저 저장한 후 text/confidence/bbox를 검증·정규화합니다.
7. 같은 행의 조각을 좌→우로 합쳐 parser 입력을 구성하고, 중앙 목차 키워드로 구조화합니다.
8. 상태가 `ocr_status=completed`, `parse_status=completed`가 됩니다. 원문, 신뢰도, bounding box, raw JSON, 섹션, 업무 항목을 화면에서 확인합니다.

CLI에서도 실행할 수 있습니다. 아래 `1`은 업로드 응답의 `document_id`로 바꿉니다.

```bash
# 저장소 루트에서
curl -F 'file=@sample-data/scanned-pdfs/db-handover-scan.pdf;type=application/pdf' \
  http://127.0.0.1:8000/api/documents/upload
curl http://127.0.0.1:8000/api/documents/1
curl http://127.0.0.1:8000/api/documents/1/sections
```

### 저장 위치와 Raw JSON

기본 경로는 다음과 같습니다.

```text
backend/data/uploads/<uuid>.pdf
backend/data/pages/<document_id>/page-0001.png
backend/data/ocr/<document_id>/page-0001.json
backend/data/ocr/<document_id>/error.json          # 실패 시
backend/data/app.db
```

페이지 JSON과 `document_pages.ocr_json`은 같은 payload를 보존합니다.

```json
{
  "page_number": 1,
  "raw_results": [{"res": {"rec_texts": ["업무 개요"], "rec_scores": [0.98], "rec_polys": [[[1,2],[90,2],[90,20],[1,20]]]}}],
  "lines": [{"text": "업무 개요", "confidence": 0.98, "bbox": [[1,2],[90,2],[90,20],[1,20]]}]
}
```

실제 `raw_results`에는 엔진 JSON의 나머지 metadata도 그대로 포함됩니다. 낮은 confidence의 인식 영역을 별도로 버리지 않습니다. `bbox`는 렌더된 이미지 픽셀 좌표입니다. DB `raw_text`에는 행을 조합한 텍스트를 저장하며 엔진이 반환한 텍스트·polygon은 JSON에 별도로 남습니다. 정규화 검증 실패 시에도 이미 받은 엔진 raw JSON을 보존합니다.

### Rule 기반 구조화 정책

- `app/parsing/section_aliases.py`에서 목차 키워드를 중앙 관리합니다.
- 번호/공백/콜론이 붙은 제목을 인식합니다. 새 제목이 없으면 다음 페이지의 본문은 기존 섹션에 이어집니다.
- 제목 이전 텍스트, 미분류 텍스트는 삭제하지 않습니다. 시작 부분은 `other` 섹션에 저장합니다.
- 기본적으로 내용이 있는 섹션마다 업무 항목을 만듭니다. 명시적인 `업무명:` 블록이 있으면 블록별로 나눕니다.
- `category`는 확인 가능한 section type입니다. Database/Backend 같은 업무 분야를 추측하지 않습니다.
- 설명·절차·주의사항·주기·관련 시스템·연락처·중요도는 명시된 필드 또는 해당 섹션 내용에서만 채웁니다. 중요도는 명시된 1~5만 저장합니다.
- 일반적인 **단일 열 문서**용 보수적 규칙입니다. 복잡한 표·다단 레이아웃·기울어진 스캔을 완벽히 복원하지 않습니다. parser는 `SectionParser`로 교체 가능하며 LLM을 사용하지 않습니다.

### 실패 및 transaction 정책

- 잘못된 PDF는 문서 생성 전에 4xx로 거부하고 임시 업로드 파일을 제거합니다.
- 상태: `pending → processing → completed/failed`, parse는 `pending → completed/failed`입니다.
- 페이지별 OCR 결과는 commit하여 이후 페이지 실패 시 앞선 결과를 보존합니다.
- 실패한 페이지는 이미지와 `{"status":"pending"}` placeholder가 남을 수 있습니다. 전체 실패 사유는 `processing_error`로 확인합니다.
- 모든 OCR 완료 후 섹션/업무 항목을 하나의 transaction으로 저장합니다. parser/구조화 저장 실패 시 부분 구조화 데이터는 rollback합니다.
- OCR 실패는 `OCR_FAILED`, parser/저장 실패는 `PARSING_FAILED`입니다. 원본 exception/본문/stack trace는 API에 노출하지 않습니다.
- 재시작 시 미완료 문서는 `PROCESSING_INTERRUPTED`로 실패 처리합니다. 자동 재시도/재처리 API는 이번 범위에 포함하지 않으며 PDF를 다시 업로드합니다. 기존 원본은 남습니다.
- 프로세스 내 background 작업은 durable queue가 아닙니다. 여러 worker나 여러 서버에서 같은 DB를 공유하지 마세요.

## 설정

`backend/.env`를 읽고 OS 환경변수가 우선합니다. 설정 변경 후 서버를 재시작합니다.

| 설정 | 기본값 |
| --- | --- |
| `DATABASE_URL` | `sqlite:///./data/app.db` |
| `PDF_RENDER_DPI` | 200 (72~300) |
| `MAX_UPLOAD_BYTES` | 52428800 (50 MiB) |
| `MAX_PDF_PAGES` | 30 |
| `MAX_PAGE_PIXELS` | 25000000 |
| `OCR_DETECTION_MODEL` | `PP-OCRv5_mobile_det` |
| `OCR_RECOGNITION_MODEL` | `korean_PP-OCRv5_mobile_rec` |
| `OCR_CPU_THREADS` | 4 |
| `CORS_ORIGINS` | localhost/127.0.0.1의 5173 origin, JSON 배열 |

DB 및 데이터 디렉터리 상대 경로는 항상 `backend/` 기준입니다. 모델 경로 override는 절대 경로를 사용합니다. SQLAlchemy 연결마다 SQLite FK를 활성화하며 session commit은 service/pipeline이 관리합니다. 시간은 UTC DATETIME이고 `updated_at`은 SQLAlchemy UPDATE 시 갱신됩니다.

Frontend `VITE_API_BASE_URL`은 `/api` 없는 backend origin이며 변경 시 재시작/재빌드가 필요합니다. 업로드 화면의 크기 안내는 기본 서버 설정 기준입니다. 서버의 제한을 변경하면 안내도 맞춰주세요.

## Phase 3 — LLM Infrastructure

### 구성과 경계

```text
향후 Business Service
    → StructuredLLMClient
        → LLMProvider (abstract interface)
            → OllamaLLMProvider
                → httpx.AsyncClient → POST /api/chat
        → JSON parse → Pydantic validation → typed result
```

- `LLMProvider.generate()`는 model/system_prompt/user_prompt/response_schema를 받아 비동기로 **검증 전 문자열**을 반환합니다.
- 실제 소비 계층은 `StructuredLLMClient.generate()`를 사용하여 Pydantic 객체를 받습니다.
- `OllamaLLMProvider`만 Ollama REST protocol을 압니다. Business Service에 Ollama SDK나 특정 모델명을 넣지 않습니다.
- 앱 생성 시 `create_app(..., llm_provider=provider)`로 다른 Provider를 주입할 수 있습니다. FastAPI dependency는 `get_llm_provider`, `get_llm_client`입니다.
- 기본 AsyncClient는 앱 lifespan에서 한 번 생성하고 종료 시 닫습니다. 주입된 Provider의 리소스는 호출자가 소유합니다.
- startup/health/OCR/문서 조회에서 Ollama에 연결하지 않습니다. 모델 자동 다운로드·서버 자동 실행도 하지 않습니다.
- `.env.example`의 기존 `qwen3.5:4b` 기본값을 사용하며 `httpx`를 개발 전용에서 runtime 의존성으로 옮겼습니다.

### Task별 분리

| 논리 Task | 환경변수 | 출력 contract | 형식 검증 실패 재요청 |
| --- | --- | --- | --- |
| SQL Generation | `SQL_MODEL` | `SQLGenerationOutput` | 최대 1회 |
| Document Generation | `DOCUMENT_MODEL` | `GeneratedDocument` | 최대 1회 |
| Question Generation | `QUESTION_MODEL` | `QuestionGenerationResult` | 최대 1회 |
| Scoring | `SCORING_MODEL` | `LLMScoringResult` | 없음, 실패 전달 |

네 모델의 Prototype 기본값은 모두 `qwen3.5:4b`입니다. OS 환경변수 또는 `backend/.env`에서 각각 바꾸고 backend를 재시작하면 새 Task 설정이 적용됩니다. Provider 코드와 향후 Business Service를 수정할 필요가 없습니다.

각 `llm/tasks/*_task.py`는 model, system prompt, output schema, 재시도 정책을 연결하는 **설정 모듈**입니다. 실제 자연어→SQL workflow, DB schema 구성, retrieval/context builder, 문서 생성 API, 문제 저장, 답안 채점 workflow는 구현하지 않았습니다. `/api/generation`, `/api/questions`, `/api/scoring` 경로도 추가하지 않았습니다.

출력 contract의 역할은 타입·필수 필드·점수 범위 등의 구조 검증입니다. `SQLGenerationOutput`을 통과해도 SQL이 안전하다는 뜻이 아닙니다. SQL 실행 코드가 없으며 Phase 4에서 별도 SQL Validator를 구현해야 합니다. 질문 수·정답/선택지 관계·원천 section 존재 여부 같은 비즈니스 검증도 해당 Phase에서 추가합니다.

### 통신과 출력 검증

- `OLLAMA_BASE_URL=http://localhost:11434`, `OLLAMA_TIMEOUT_SECONDS=120`을 사용합니다. URL은 HTTP(S) base URL이며 query/fragment/인증정보를 넣지 않습니다.
- `POST /api/chat`에 `stream=false`, system/user messages를 전송합니다. Schema가 주어지면 `format`에 Pydantic JSON Schema를 넣습니다. 공통 client는 prompt에도 JSON Schema를 포함합니다.
- 완료된 assistant 메시지의 `content`만 읽습니다. `thinking` metadata는 정답으로 사용하지 않습니다. 불완전한 응답, 잘못된 envelope, 길이 제한으로 중단된 응답은 실패입니다.
- JSON 객체 하나만 허용합니다. 코드펜스·설명문·여러 JSON·중복 키·NaN/Infinity는 자동 수정하지 않고 실패 처리합니다.
- Pydantic은 strict validation을 사용하며 알려지지 않은 필드, 필수 키 누락, 잘못된 타입을 거부합니다. Scoring은 0~100의 유한 숫자만 허용합니다. `is_correct`는 null을 허용하지만 키 자체는 필수입니다.
- HTTPX connect/read/write/pool timeout과 요청 전체 deadline을 모두 적용합니다. **120초는 요청 1회 기준**이며 형식 재시도가 있는 Task는 최대 2회 요청할 수 있습니다.
- 연결/HTTP/모델 실행 오류는 자동 재시도하지 않습니다. JSON·schema·응답 envelope 검증 실패만 Task 정책에 따라 한 번 재요청합니다. 실패한 원문을 prompt에 다시 붙이지 않습니다.
- Scoring 실패는 `LLMError`로 상위 계층에 전달합니다. Python fallback 자체는 Phase 7에서 구현하며, 정상 LLM 점수를 재계산하지 않습니다.
- 취소는 취소 상태 그대로 전달합니다. HTTP redirect를 따라가지 않고 환경변수의 proxy를 자동 사용하지 않습니다.
- 로그에는 Task 이름·시도 횟수·오류 단계/상태만 기록합니다. prompt, 문서 본문, LLM 응답, upstream 오류 본문은 로그나 API 오류에 넣지 않습니다.

| 오류 code | API status | 의미 |
| --- | --- | --- |
| `OLLAMA_UNAVAILABLE` | 503 | 연결/통신 실패 |
| `OLLAMA_TIMEOUT` | 504 | timeout 또는 요청 전체 deadline 초과 |
| `OLLAMA_MODEL_NOT_FOUND` | 503 | upstream 404, 모델/엔드포인트 확인 필요 |
| `OLLAMA_BUSY` | 503 | upstream 429 |
| `OLLAMA_REQUEST_FAILED` | 502 | 그 외 HTTP 오류/모델 실행 오류 |
| `LLM_RESPONSE_INVALID` | 502 | envelope/JSON/Pydantic 검증 실패 |

오류는 기존 `{code, message, detail}` 형식을 사용합니다. Service는 공통 `LLMError`를 잡을 수 있으므로 Ollama 예외 타입에 종속되지 않습니다.

### Ollama 없이 검증

아래 명령은 `backend/`에서 실행합니다.

```bash
uv sync --locked
uv run pytest -q tests/llm tests/test_config.py
uv run python scripts/smoke_llm.py
```

기본 smoke는 `httpx.MockTransport`로 Ollama adapter → JSON parse → Pydantic까지 검증하며 실제 HTTP 연결이 없습니다.

```json
{"mode":"mock","model":"qwen3.5:4b","result":{"status":"ok"}}
```

테스트는 Fake Provider와 MockTransport를 사용합니다. LLM 테스트 폴더의 fixture가 실제 HTTP transport 호출을 차단하므로 Ollama가 꺼져 있어도 실행할 수 있습니다. HTTP 요청 형태, timeout, 취소, HTTP 오류, 잘못된 envelope/JSON, schema 검증, 제한된 재시도, Scoring 실패 전달, DI/lifespan, 민감한 내용 미노출을 검사합니다.

### 실제 Ollama 연결은 선택적으로 확인

Ollama를 별도로 설치·실행하고 사용할 모델을 준비한 환경에서:

```bash
ollama serve                    # 이미 실행 중이라면 생략
ollama pull qwen3.5:4b           # 별도 터미널, 최초 한 번
uv run python scripts/smoke_llm.py --live
```

Live smoke도 SQL/문서를 생성하지 않고 `{"status":"ok"}` 응답만 요청합니다. 모델 선택에는 `SQL_MODEL`을 사용합니다. 연결·출력 검증 실패 시 공통 오류를 출력하고 종료 코드 1을 반환합니다. 이번 Phase의 자동 검증은 mock 기반이며 실제 Qwen3.5-4B 추론은 실행하지 않았습니다.

### Phase 3 검증 결과

- 시작 전 Phase 1~2: 50개 테스트 및 frontend build 통과
- 변경 후 전체 backend: **156 passed, 5 warnings** (기존 PyMuPDF SWIG deprecation)
- Mock HTTP 기반 smoke: `status=ok`
- Alembic schema check: 변경 없음, revision `0001` 유지
- 기존 frontend build 통과, frontend 파일 변경 없음
- 기존 PDF→DB 통합 테스트도 전체 테스트에 포함되어 통과
- 실제 Ollama/Qwen 추론 품질·성능은 미검증이며 live smoke로 별도 확인 가능

### Phase 3 파일

```text
backend/app/llm/
  __init__.py
  provider.py                         # abstract interface
  ollama_provider.py                  # async REST adapter
  errors.py                           # 공통 LLM 예외
  validation.py                       # JSON parse / Pydantic
  client.py                           # 구조화 응답 / 제한된 재시도
  dependencies.py                     # Provider 수명 / FastAPI DI
  prompts/{__init__,sql_generation,document_generation,question_generation,scoring}.py
  tasks/{__init__,base,sql_task,document_task,question_task,scoring_task}.py
backend/app/schemas/llm.py
backend/scripts/smoke_llm.py
backend/tests/llm/{conftest,test_ollama_provider,test_validation,test_client,test_dependencies}.py
```

기존 `main.py`, `core/config.py`, `.env.example`, `pyproject.toml`, `uv.lock`, `tests/test_config.py`, README도 갱신했습니다. 실제 생성 기능과 SQL Validator는 이후 Phase에서 이 기반을 사용해 구현합니다.

참고: [Ollama chat API](https://docs.ollama.com/api/chat), [Structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [HTTPX async](https://www.python-httpx.org/async/), [HTTPX MockTransport](https://www.python-httpx.org/advanced/transports/).

## Migration

Phase 2~3에서는 기존 6개 모델/테이블을 그대로 사용하며 **추가 migration은 없습니다**.

```bash
cd backend
uv run alembic upgrade head
uv run alembic current       # 0001
uv run alembic check
```

애플리케이션은 `create_all()`을 실행하지 않습니다. 테스트에서도 PDF→DB 통합 검증은 Alembic으로 빈 DB를 구성합니다. DB 직접 변경 대신 모델 변경 후 새 migration을 검토·적용하세요.

## 테스트와 실제 OCR 재현

```bash
cd backend
uv run pytest -q
```

일반 테스트는 **실제 PyMuPDF 렌더링 + OCR test double + 실제 parser + SQLite**를 사용하여 모델 다운로드 없이 실행합니다. Paddle adapter 생성 옵션/결과 변환도 별도로 검사합니다. 테스트용 metadata는 실제 운영 DB에 직접 INSERT하지 않습니다.

실제 모델 smoke 검증:

```bash
cd backend
export PADDLE_PDX_CACHE_HOME="$PWD/data/paddlex"
export PADDLE_PDX_MODEL_SOURCE=BOS
uv run python scripts/smoke_document_pipeline.py
```

매 실행은 `backend/data/smoke/<timestamp>/` 아래 별도 SQLite DB에 Alembic을 적용합니다. 실제 upload API를 통해 입력하고 실제 PaddleOCR를 실행합니다. 업로드 PDF·페이지 이미지·raw JSON·문서 조회 JSON·`report.json`을 보존하며 기존 `data/app.db`는 수정하지 않습니다. HTTP 202, 두 페이지 저장, 8개 목차 유형, 원본 파일과 DB JSON 일치를 assert합니다.

샘플 재생성은 `uv run python scripts/create_sample_pdf.py`로 가능합니다. macOS에서는 시스템 한글 글꼴을 사용하며 다른 환경에서는 PyMuPDF 내장 CJK 글꼴로 대체되어 OCR 결과가 달라질 수 있습니다. `sample-data/metadata/db-handover.expected.json`은 품질 비교용 정답 텍스트이며 DB 입력으로 사용하지 않습니다.

Frontend:

```bash
cd frontend
npm run build
```

### Phase 2 완료 시 검증 결과 (2026-10-01)

- 작업 시작 전 Phase 1: 17개 테스트, frontend build, Alembic schema check 통과
- 전체 backend 테스트: **50 passed, 5 warnings** (PyMuPDF SWIG deprecation)
- Frontend: TypeScript 검사 및 Vite production build 통과
- Alembic: 기존 revision `0001` 유지, `alembic check` 통과
- 브라우저: 실제 샘플 파일 선택/업로드 → 처리 중 표시 → 자동 완료 갱신 → 목록/상세/업무 필드/OCR 신뢰도·좌표 표시 확인
- 실제 PaddleOCR smoke: **2페이지, OCR 영역 13+9개, 섹션 9개, 업무 항목 9개**, OCR/parse 모두 completed
- 9개 섹션: 문서 제목 `other` + 명세의 8개 목차
- 두 페이지 raw JSON 파일과 DB JSON 일치 확인
- 재현 결과: `backend/data/smoke/20260930T171014895638/report.json` (로컬 산출물, Git 제외)
- 브라우저 검증 샘플은 기본 로컬 DB에 문서 ID 1로 보존했습니다.
- macOS arm64에서 실제 PP-OCRv5 한국어 모델 추론 성공
- PyMuPDF SWIG deprecation 및 Paddle의 ccache 미설치 안내가 있으나 처리/테스트 실패는 아님

## 주요 Phase 2 파일

```text
backend/app/api/documents.py                  # 업로드/목록/상세/섹션
backend/app/schemas/document.py               # API 응답 schema
backend/app/services/document_service.py      # 업로드 검증/파일 저장
backend/app/repositories/document_repository.py
backend/app/ocr/base.py                       # OcrEngine protocol
backend/app/ocr/pdf_renderer.py               # PDF 검증/이미지 렌더링
backend/app/ocr/paddle_ocr.py                  # 지연 로딩 adapter/정규화
backend/app/ocr/pipeline.py                   # 페이지 저장/구조화/실패 관리
backend/app/ocr/storage.py                    # atomic JSON 저장
backend/app/parsing/section_aliases.py
backend/app/parsing/section_mapper.py
backend/app/parsing/reading_order.py
backend/app/parsing/item_mapper.py
backend/tests/test_ocr.py
backend/tests/test_parsing.py
backend/tests/test_document_pipeline.py
backend/scripts/create_sample_pdf.py
backend/scripts/smoke_document_pipeline.py
frontend/src/api/client.ts
frontend/src/types/document.ts
frontend/src/pages/Upload.tsx
frontend/src/pages/Documents.tsx
frontend/src/pages/DocumentDetail.tsx
sample-data/scanned-pdfs/db-handover-scan.pdf
sample-data/metadata/db-handover.expected.json
```

기존 `app/main.py`, `core/config.py`, `.env.example`, Python/Node 의존성 및 lockfile, `App.tsx`, CSS, `.gitignore`, README를 갱신했습니다. Phase 1 ORM과 migration, 최우선 명세는 변경하지 않았습니다.

실제 양식의 표·목차에 대한 parser 정확도와 스캔 품질은 계속 평가해야 합니다. 다음 구현 단계는 Phase 4 SQL Retrieval이며, 생성된 SQL은 반드시 SQL Validator를 통과한 뒤에만 실행해야 합니다.

공식 참고: [PaddleOCR OCR 사용법](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html), [공식 한국어 모델](https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec), [PyMuPDF 이미지 렌더링](https://pymupdf.readthedocs.io/en/latest/recipes-images.html).
