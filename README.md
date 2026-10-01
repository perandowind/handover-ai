# Handover AI — Prototype v1

스캔 이미지 PDF 기반 인수인계서 자동 작성 및 분석 시스템입니다.
최우선 명세는 [PROTOTYPE_SPEC.md](PROTOTYPE_SPEC.md)이며, 현재 **Phase 1~6 — Project Skeleton / Document Pipeline / LLM Infrastructure / SQL Retrieval / Handover Generation / PDF Export**까지 구현했습니다.

## 현재 범위

```text
PDF 업로드 → 파일 검증 → 페이지 PNG 렌더링 → PaddleOCR
→ 페이지별 Raw JSON/SQLite 보존 → SectionMapper → sections/handover_items 저장
```

- FastAPI + Pydantic v2, SQLite + SQLAlchemy 2.x, Alembic
- PyMuPDF 이미지 렌더링 (기본 200 DPI)
- PaddleOCR 3.3.3 + PaddlePaddle 3.2.2 CPU
- `PP-OCRv5_mobile_det` + `korean_PP-OCRv5_mobile_rec`
- React + TypeScript + Vite + React Router: Upload, Documents, 문서 상세, Generate/Preview
- LLMProvider 추상화, Ollama REST adapter, 공통 JSON/Pydantic 검증, Task별 설정·프롬프트 구현
- 자연어 → SQL Generation → SQL Validator → 읽기 전용 SQLite 조회 → Context 구성
- 조회 Context 기반 인수인계서 생성, 기본 8개 목차 검증, React Preview
- Jinja2 HTML → PyMuPDF Story PDF 및 React 다운로드
- 문제 생성, 채점/Python fallback은 이후 Phase 범위
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
| `POST /api/retrieval/search` | 자연어 요청으로 검증된 SQL 조회 및 Context 반환 |
| `POST /api/generation/handover` | 조회 Context 기반 인수인계서 JSON 생성 |
| `POST /api/generation/handover/pdf` | 기존 GeneratedDocument JSON을 PDF로 다운로드 |

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

출력 contract의 역할은 타입·필수 필드·점수 범위 등의 구조 검증입니다. `SQLGenerationOutput`을 통과해도 SQL이 안전하다는 뜻이 아닙니다. Phase 4는 이 출력에 별도 SQL Validator를 적용한 뒤에만 조회합니다. 질문 수·정답/선택지 관계·원천 section 존재 여부 같은 비즈니스 검증도 해당 Phase에서 추가합니다.

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

기존 `main.py`, `core/config.py`, `.env.example`, `pyproject.toml`, `uv.lock`, `tests/test_config.py`, README도 갱신했습니다. Phase 4의 SQL Generation/Validator와 Phase 5의 DocumentGenerationTask가 이 기반을 사용하며, 문제 생성과 채점은 이후 Phase 범위입니다.

참고: [Ollama chat API](https://docs.ollama.com/api/chat), [Structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [HTTPX async](https://www.python-httpx.org/async/), [HTTPX MockTransport](https://www.python-httpx.org/advanced/transports/).

## Migration

Phase 2~6에서는 기존 6개 모델/테이블을 그대로 사용하며 **추가 migration은 없습니다**.

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

실제 양식의 표·목차에 대한 parser 정확도와 스캔 품질은 계속 평가해야 합니다. Phase 4 SQL Retrieval과 Phase 5 문서 생성은 아래에 설명합니다. 문서 생성에는 검증된 조회 결과로 구성한 Context를 사용합니다.

공식 참고: [PaddleOCR OCR 사용법](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html), [공식 한국어 모델](https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec), [PyMuPDF 이미지 렌더링](https://pymupdf.readthedocs.io/en/latest/recipes-images.html).


## Phase 4 — SQL Generation / Retrieval

`POST /api/retrieval/search`는 자연어 `query`만 받습니다. API에서 SQL 직접 입력은 받지 않습니다.

```bash
curl -sS http://127.0.0.1:8000/api/retrieval/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"DB 운영 및 백업 관련 업무를 중요도 순으로 찾아줘"}'
```

응답 필드:

| 필드 | 의미 |
| --- | --- |
| `sql` | Validator가 정규화하고 LIMIT를 적용한 실제 조회 SQL |
| `rows`, `row_count` | 조회 결과와 반환 행 수 |
| `context` | 업무명·설명·주의사항 등 의미 있는 라벨로 구성한 근거 |
| `context_truncated` | 조회된 결과로 만든 Context가 row/문자 제한 때문에 축약되었는지 |

SQL의 LIMIT로 DB에서 제외된 행 수는 계산하지 않습니다. 검색 결과가 없으면 HTTP 200, `rows: []`, `context: ""`입니다. 검색 전 문서의 OCR/parse 완료를 확인하세요. 명시적으로 요청한 정렬을 우선하며 ContextBuilder는 조회 순서를 유지합니다. 별도의 relevance 점수나 reranker는 구현하지 않습니다.

### 처리와 검증 경계

1. `RetrievalSchema`가 ORM에서 `documents`, `document_sections`, `handover_items`의 컬럼·타입·FK 정보를 가져옵니다. 같은 allowlist를 LLM 프롬프트, Validator, 실행 계층에서 공유합니다. `document_pages`, `questions`, `scoring_results`, SQLite 시스템 테이블은 제외합니다.
2. `SQLGenerationTask`가 기존 `StructuredLLMClient`/`LLMProvider`와 `SQL_MODEL`을 사용합니다. Phase 3의 `SQLGenerationOutput(sql, reason)` Pydantic schema를 재사용합니다.
3. SQLGlot AST로 단일 SELECT인지, 모든 테이블·컬럼이 허용되는지 검사합니다. 별칭, 모호한 컬럼, HAVING 참조까지 검증하며 `*`는 허용 컬럼으로 확장합니다. **원본 SQL은 DB에 실행하지 않습니다.**
4. JSON/Pydantic 또는 SQL 검증 실패를 합쳐 **총 두 번까지만** 모델을 호출합니다. 한 번 재생성 후에도 실패하면 HTTP 502 `SQL_GENERATION_FAILED`입니다. Provider 연결/timeout 오류 및 DB 실행 실패는 재생성 대상이 아닙니다.
5. `SqlRetrievalStrategy`는 검증된 SQL만 `SQLiteReader`에 전달합니다. 별도 `mode=ro` 연결, `query_only`, SQLite authorizer로 쓰기·외부 DB·미허용 테이블/함수를 재차 차단합니다. ORM의 쓰기용 연결에는 영향을 주지 않습니다. 동기 SQLite 작업은 thread pool에서 실행합니다.
6. `ContextBuilder`가 조회 결과에 라벨을 붙이고 문자열 값을 인용·이스케이프하여 최대 문자 수 안으로 제한합니다. 향후 생성 Task에서도 이 Context를 신뢰할 수 없는 근거 데이터로 취급해야 합니다.

지원 SELECT 범위는 WHERE/LIKE/IN/BETWEEN/NULL 비교, ORDER BY, LIMIT/OFFSET, ON 조건을 명시한 INNER/LEFT JOIN, GROUP BY/HAVING입니다. 함수는 LOWER/UPPER/LENGTH/COALESCE 및 COUNT/MIN/MAX/SUM/AVG로 제한합니다. 결과 컬럼명은 중복되지 않아야 합니다.

INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, REPLACE, PRAGMA, ATTACH, DETACH 및 다중 statement는 거부합니다. CTE·서브쿼리·UNION·window·CROSS JOIN·임의 함수도 Prototype의 지원 범위 밖으로 거부합니다. 금지어가 단순 문자열 값이나 주석에 있는 경우에는 명령으로 취급하지 않습니다.

### 환경설정과 오류

```env
SQL_MODEL=qwen3.5:4b
MAX_RETRIEVAL_ROWS=100
MAX_CONTEXT_CHARS=20000
RETRIEVAL_TIMEOUT_SECONDS=5
```

LIMIT가 없으면 최대 행 수를 추가하고, 더 큰 LIMIT는 최대 행 수로 낮춥니다. `LIMIT 0`도 보존합니다. 조회 실행은 기본 5초의 SQLite progress deadline으로 제한하며, SQLite 값/행의 최대 크기는 1 MB로 제한합니다. 이 상한에 걸린 데이터는 잘라서 반환하지 않고 오류로 처리합니다.

파일 기반 SQLite가 필요합니다. 메모리 DB에 대한 Retrieval은 HTTP 503 `RETRIEVAL_DATABASE_UNSUPPORTED`입니다. 파일이 없으면 새 DB를 만들지 않고 `RETRIEVAL_FAILED`를 반환합니다. Migration을 먼저 적용하세요. 기타 DB 오류는 `RETRIEVAL_FAILED`, 실행 deadline은 `RETRIEVAL_TIMEOUT`이며 기존 `{code, message, detail}` 오류 형식을 사용합니다.

앱 시작/health/OCR은 Ollama 없이 계속 동작합니다. 실제 Retrieval 요청에는 실행 중인 Ollama와 `SQL_MODEL`이 필요합니다. 모델 준비는 위 Phase 3 설명을 따르세요. `DEBUG_LOGGING=true`일 때 생성 SQL이 로그에 기록되므로 검색어가 포함될 수 있습니다. 기본 로그에는 검증 결과와 row 수만 남깁니다.

### 테스트 / 검증 결과 (2026-10-01)

```bash
cd backend
uv sync --locked
uv run alembic upgrade head
uv run pytest -q tests/retrieval
uv run pytest -q
uv run alembic check
```

- Phase 4 테스트: **105 passed** — 금지 명령, 테이블/컬럼·별칭, 다중 statement, 함수, LIMIT, Context, 재생성 횟수, 실행 전 검증, 읽기 전용 방어, deadline 검증.
- 전체 backend: **261 passed, 5 warnings**. 기존 PyMuPDF SWIG deprecation warning만 발생했습니다.
- 통합 테스트: Alembic으로 생성한 임시 SQLite + Mock Provider + 실제 Validator/Reader/ContextBuilder/API를 사용합니다. 외부 HTTP 호출은 테스트 fixture에서 금지하며 Ollama가 꺼져 있어도 실행됩니다.
- Frontend TypeScript/Vite build 및 Alembic schema check 통과. 추가 migration은 없으며 revision `0001`을 유지합니다.
- 기존 Phase 2의 실제 OCR 샘플 DB(문서 ID 1)에 Mock Provider를 연결한 읽기 전용 smoke에서 백업 관련 **7행**과 Context를 확인했습니다. 샘플 DB는 수정하지 않았습니다.
- 이번 Phase에서 실제 Qwen 모델의 SQL 생성 정확도는 검증하지 않았습니다. 다음 Phase 전에는 실제 모델로 한국어 검색어·정렬·JOIN 생성 품질을 확인해야 합니다.

### Phase 4 파일

```text
backend/app/api/retrieval.py
backend/app/schemas/retrieval.py
backend/app/services/retrieval_service.py
backend/app/retrieval/{__init__,base,schema,validator,executor,sql_strategy,context,dependencies}.py
backend/tests/retrieval/{conftest,test_validator,test_context,test_integration}.py
```

기존 `app/llm/tasks/sql_task.py`, `app/llm/prompts/sql_generation.py`, `app/main.py`, `app/core/config.py`, `.env.example`, `pyproject.toml`, `uv.lock`, README를 수정했습니다. 프런트엔드·ORM·migration·최우선 명세는 변경하지 않았습니다. Phase 4 시점에는 Vector Retrieval/DB 및 문서·문제 생성을 구현하지 않았습니다.


## Phase 5 — Handover Document Generation

사용자 요청 → Phase 4 Retrieval → ContextBuilder → DocumentGenerationTask → JSON/Pydantic 검증 → React Preview를 연결했습니다. 저장된 원문을 조회하며 생성 결과는 API 응답과 화면 상태로만 유지합니다. 결과 저장용 테이블이나 PDF Export는 추가하지 않았습니다.

### 사용 방법

기존 backend/frontend 실행 명령을 그대로 사용합니다. Ollama에 `SQL_MODEL`과 `DOCUMENT_MODEL`이 준비되어 있어야 하며, 기본값은 각각 `qwen3.5:4b`입니다. 별도 의존성·환경변수·migration 추가는 없습니다.

1. PDF를 업로드하고 OCR/구조화 완료를 확인합니다.
2. React의 **인수인계서 생성** 메뉴(`/generate`)로 이동합니다.
3. 작성 요청을 입력하고 필요하면 대상 문서를 선택합니다. 문서는 20개씩 조회하며 여러 페이지의 선택을 유지합니다.
4. **인수인계서 생성**을 누르면 조회와 생성이 순차 실행됩니다. 대기 중에는 중복 제출과 입력을 막습니다.
5. 기본 8개 목차의 결과를 미리보기에서 확인합니다. 본문은 HTML 실행 없이 평문과 줄바꿈으로 표시합니다.

```bash
curl -sS http://127.0.0.1:8000/api/generation/handover \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"DB 운영 업무를 담당할 신규 인계자를 위한 인수인계서를 작성해줘.","document_ids":[1]}'
```

요청의 `prompt`는 공백 제거 후 1~4,000자입니다. `document_ids`는 선택 사항이며 생략/null/빈 배열이면 전체 범위에서 검색합니다. 지정하는 경우 중복 없는 양의 정수 ID를 최대 100개 받습니다. 존재하지 않는 ID는 HTTP 404 `DOCUMENT_NOT_FOUND`, OCR/구조화 미완료 문서는 HTTP 409 `DOCUMENT_NOT_READY`로 LLM 호출 전에 거부합니다.

선택 ID는 프롬프트에만 전달하지 않습니다. SQL Validator가 모든 조회 테이블의 문서 ID에 대해 AST 조건을 추가하여 정렬/집계/LIMIT 전에 범위를 제한합니다. LEFT JOIN은 ON 조건을 제한하여 오른쪽 문서가 없는 왼쪽 결과는 보존합니다. 기존 `/api/retrieval/search`의 비선택 검색 동작은 유지합니다.

응답은 명세의 `GeneratedDocument`입니다.

```json
{
  "title": "DB 운영 인수인계서",
  "sections": [
    {"section_type":"overview", "title":"업무 개요", "content":"관련 정보 없음"},
    {"section_type":"responsibilities", "title":"주요 업무", "content":"관련 정보 없음"},
    {"section_type":"systems", "title":"관련 시스템", "content":"관련 정보 없음"},
    {"section_type":"procedures", "title":"업무 절차", "content":"관련 정보 없음"},
    {"section_type":"precautions", "title":"주의사항", "content":"관련 정보 없음"},
    {"section_type":"troubleshooting", "title":"장애 대응", "content":"관련 정보 없음"},
    {"section_type":"contacts", "title":"담당자 및 연락처", "content":"관련 정보 없음"},
    {"section_type":"references", "title":"참고자료", "content":"관련 정보 없음"}
  ]
}
```

### 생성 정책과 검증

- 기본 목차는 `core/handover.py`에 중앙 관리합니다. 기존 `GeneratedDocument`/`GeneratedSection`에 8개 목차의 순서·중복·제목 일치 검증을 추가했습니다. 문서 제목은 최대 200자, 섹션 본문은 최대 12,000자이며 공백 본문·잘못된 타입·추가 필드는 거부합니다.
- 사용자 요청은 작성 목적이며 사실 근거가 아닙니다. DocumentGenerationTask는 원문 조회로 만든 제한된 Context와 목차를 JSON 데이터로 묶어 전달합니다. 서비스는 Ollama나 모델명을 직접 사용하지 않고 기존 Provider/Task 설정을 사용합니다.
- 프롬프트에 Context 밖의 사실, 일반 지식/권장사항, 임의의 담당자·연락처·명령어·시스템·일정·수치를 추가하지 말라고 명시했습니다. 원문과 사용자 요청 안의 규칙 변경 지시도 따르지 않도록 합니다.
- 섹션 근거가 없으면 정확히 **관련 정보 없음**, 부분 근거만 있으면 확인된 내용만 사용하도록 지시합니다. 축약된 Context의 생략 내용도 추측하지 않습니다.
- 조회 Context가 비어 있으면 Document LLM을 호출하지 않고 8개 섹션 전체를 **관련 정보 없음**으로 구성한 Pydantic 객체를 반환합니다. SQL Retrieval 단계는 그대로 수행합니다.
- Document JSON/스키마 검증 실패는 같은 Context로 **1회 재시도**하며 Retrieval은 반복하지 않습니다. 두 번째 실패는 HTTP 502 `LLM_RESPONSE_INVALID`; Provider 연결/timeout은 기존 오류를 그대로 반환합니다.
- Pydantic은 형식과 목차를 검증합니다. 비어 있지 않은 Context에 대한 **문장의 사실 일치까지 자동 보증하지는 않습니다**. 실제 모델이 근거 없는 세부사항을 보충하는지 평가하고 원문과 대조해야 합니다.

### Phase 5 검증 결과 (2026-10-01)

```bash
cd backend
uv run pytest -q tests/generation
uv run pytest -q
uv run alembic check
```

프런트엔드 빌드는 `cd frontend && npm run build`입니다.

- Phase 5 신규 unit/integration 테스트: **52 passed**.
- 전체 backend: **313 passed, 5 warnings**. 기존 PyMuPDF SWIG deprecation warning만 있습니다.
- 실제 임시 SQLite/Alembic + Mock Provider로 자연어 요청 → 검증된 SQL → 조회/Context → DocumentGenerationTask → Pydantic → API 응답을 확인했습니다.
- 선택 ID 누락/OR 우회 시도, JOIN/LEFT JOIN/집계의 문서 범위, Context 제한, 빈 결과, 잘못된 목차, 재시도 횟수, Provider 오류, 원본 DB 미변경을 검증했습니다.
- 기존 Phase 3 테스트의 'Generation API 없음' 및 임시 단일 섹션 contract 기대값을 이번 Phase의 API/8개 목차 정책에 맞게 갱신했습니다.
- TypeScript/Vite build 및 Alembic schema check 통과. 기존 revision `0001` 유지.
- 브라우저에서 대상 문서 선택, 생성 대기/버튼 비활성화, 8개 목차 Preview, 관련 정보 없음, 실패 메시지와 버튼 복구를 확인했습니다. 기존 실제 OCR 샘플 DB의 **임시 복사본 + Mock Provider**를 사용했으며 운영 DB는 수정하지 않았습니다.
- 실제 Qwen 모델의 생성 품질과 hallucination 비율은 이번 검증에 포함하지 않았습니다. 다음 Phase 전에는 실제 모델로 한국어 요청·정보 부족·문서 안의 지시문 사례를 확인해야 합니다.

### Phase 5 파일

신규:

```text
backend/app/core/handover.py
backend/app/schemas/generation.py
backend/app/api/generation.py
backend/app/services/handover_generation_service.py
backend/tests/generation/{conftest,test_task,test_generation_integration}.py
frontend/src/types/generation.ts
frontend/src/pages/Generate.tsx
frontend/src/components/GeneratedDocumentPreview.tsx
```

수정:

```text
backend/app/llm/prompts/document_generation.py
backend/app/llm/tasks/{document_task,sql_task}.py
backend/app/schemas/llm.py
backend/app/services/retrieval_service.py
backend/app/retrieval/{base,sql_strategy,validator}.py
backend/app/main.py
backend/tests/llm/{test_dependencies,test_validation}.py
frontend/src/{App.tsx,style.css}
README.md
```


## Phase 6 — PDF Export

기존 `GeneratedDocument`와 `GeneratedSection` 구조·검증은 그대로 유지합니다. PDF 요청은 이미 생성된 JSON을 받아 `DocumentExporter` → `PdfExporter` → Jinja2 HTML → PyMuPDF Story → PDF 순서로 처리합니다. LLM이나 Retrieval을 다시 호출하지 않습니다.

### Renderer 선택과 설치

이미 OCR 페이지 렌더링에 사용하는 **PyMuPDF Story**를 HTML-to-PDF renderer로 재사용합니다. macOS arm64의 현재 Python 3.12 환경에서 추가 Chromium/WebKit 실행 파일이나 Cairo/Pango 설치 없이 동작하는 것을 확인했습니다. Story의 내장 CJK fallback 글꼴을 사용하고 PDF에 subset으로 포함하여 한글을 표시합니다. 새 의존성은 Jinja2뿐입니다.

```bash
cd backend
uv sync --locked
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

기존 `.env`에는 필요하면 아래 설정을 병합하세요.

```env
EXPORT_DIR=./data/exports
PDF_EXPORT_TIMEOUT_SECONDS=60
```

기본값을 그대로 써도 됩니다. DB/migration 변경은 없습니다.

렌더링은 요청별 별도 Python subprocess에서 수행하여 API/OCR 스레드와 native renderer 상태를 공유하지 않습니다. FastAPI의 동기 endpoint가 thread pool에서 기다리며, 지정된 timeout이 지나면 자식 프로세스를 종료하고 오류를 반환합니다. 별도 장기 실행 worker나 queue는 추가하지 않았습니다.

공식 근거: [PyMuPDF Stories](https://pymupdf.readthedocs.io/en/latest/recipes-stories.html), [Story 및 내장 글꼴 설명](https://pymupdf.readthedocs.io/en/latest/tutorial.html).

### 다운로드

React Generate 화면에서 생성 결과의 **PDF 다운로드** 버튼을 누르세요. 현재 Preview JSON을 전송하며, 처리 중에는 버튼을 비활성화합니다. 실패 시 오류를 표시하고 다시 시도할 수 있습니다. 화면 이동이나 생성 결과 교체 시 이전 다운로드 요청은 취소합니다.

API 직접 호출:

```bash
# generated-document.json은 POST /api/generation/handover에서 받은 전체 JSON
curl --fail-with-body http://127.0.0.1:8000/api/generation/handover/pdf \
  -H 'Content-Type: application/json' \
  --data-binary @generated-document.json \
  --output handover.pdf
```

성공 응답은 `application/pdf`, `Content-Disposition: attachment; filename="handover.pdf"`, `Cache-Control: no-store`입니다. 잘못된 JSON/목차는 기존 Pydantic 정책에 따라 HTTP 422로 거부합니다. 생성 실패는 HTTP 500 `PDF_EXPORT_FAILED`, timeout은 HTTP 504 `PDF_EXPORT_FAILED`이며 공통 JSON 오류 형식을 사용합니다. API를 curl로 호출할 때는 HTTP 성공 여부도 확인하세요.

A4, 8개 기본 목차, 한글/영문 본문, 줄바꿈, 자동 페이지 나눔, 페이지 번호를 지원합니다. 긴 URL/식별자에는 HTML 표시 단계에서 보이지 않는 줄바꿈 기회를 넣으며 원본 JSON은 수정하지 않습니다. PDF에서 복사한 긴 문자열에는 줄바꿈/공백이 들어갈 수 있습니다. Jinja2 autoescape를 사용하여 본문의 HTML·script·파일 URL을 마크업으로 실행하지 않고 평문으로 표시합니다. 외부 asset Archive는 제공하지 않습니다.

### Export 파일 관리

- `EXPORT_DIR` 아래에 접근 권한을 제한한 고유 `handover-export-*` 임시 디렉터리를 요청마다 생성합니다.
- 제목이나 사용자 입력을 파일 경로에 사용하지 않습니다. HTML은 stdin으로만 전달하고 디스크에 저장하지 않습니다.
- PDF를 생성·검사한 후 응답 bytes로 읽고 임시 디렉터리를 삭제합니다. 생성 실패/timeout에서도 정리하며 동시 요청은 파일을 공유하지 않습니다.
- 렌더링은 최대 100페이지, 응답 파일은 최대 20 MiB로 제한합니다. 초과 시 불완전한 PDF를 내려보내지 않고 오류로 반환합니다.
- 서버에 다운로드 이력을 영구 보관하지 않습니다. 사용자가 받은 파일은 브라우저 다운로드 위치에 남습니다.
- 강제 종료/전원 차단 시 임시 폴더가 남을 수 있습니다. 모든 서버/렌더러를 중지한 뒤 `EXPORT_DIR`의 해당 `handover-export-*` 잔여 폴더만 수동 정리할 수 있습니다. 자동으로 다른 파일을 삭제하는 정책은 없습니다.

### Phase 6 검증 결과 (2026-10-02)

```bash
cd backend
uv run pytest -q tests/rendering
uv run pytest -q
uv run alembic check
```

프런트엔드는 `cd frontend && npm run build`로 검사합니다.

- 신규 PDF 테스트 **18 passed**, 전체 backend **331 passed, 5 warnings**. 기존 PyMuPDF SWIG deprecation warning만 발생했습니다.
- 실제 PDF 생성/한글 추출/글꼴 포함/페이지 번호, 긴 본문과 긴 식별자의 줄바꿈·페이지 경계, HTML escape, 동시 export 격리, 성공·실패·timeout 파일 정리, 잘못된 API 입력 및 LLM 미호출을 검증했습니다.
- TypeScript/Vite build 및 Alembic schema check 통과. 기존 revision `0001` 유지.
- Poppler로 단일 페이지 및 5페이지 출력 전체를 이미지로 렌더링하여 한글 글꼴·여백·페이지 번호·본문 잘림을 시각적으로 확인했습니다. Poppler는 검증용 도구이며 애플리케이션 의존성이 아닙니다.
- 브라우저에서 기존 OCR 샘플의 임시 DB 복사본 + Mock Provider로 Preview를 만든 뒤, 실제 PDF renderer를 통해 다운로드한 37,412-byte PDF의 제목과 페이지를 확인했습니다. PDF Export 자체에는 Mock renderer를 사용하지 않았습니다.
- Phase 5의 'PDF endpoint 없음' 기대값 두 곳만 새 endpoint 존재 확인으로 갱신했습니다. 기존 GeneratedDocument schema는 변경하지 않았습니다.

### Phase 6 파일

신규:

```text
backend/app/rendering/{__init__,base,template_renderer,pdf_exporter,pdf_worker}.py
backend/app/rendering/templates/handover.html
backend/tests/rendering/test_pdf_export.py
frontend/src/components/PdfDownloadButton.tsx
```

수정:

```text
backend/app/api/generation.py
backend/app/core/config.py
backend/app/main.py
backend/.env.example
backend/pyproject.toml
backend/uv.lock
backend/tests/llm/test_dependencies.py
backend/tests/generation/test_generation_integration.py
frontend/src/api/client.ts
frontend/src/components/GeneratedDocumentPreview.tsx
README.md
```

DOCX/Google Docs Export는 구현하지 않았습니다. 이후 Phase 전에는 실제 업무 문서의 글자 종류·최대 본문 길이·원하는 출력 양식으로 확인하세요. 임의 CSS/표/이미지를 입력하는 범용 HTML 변환 API는 제공하지 않습니다.
