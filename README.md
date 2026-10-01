# Handover AI — Prototype v1

스캔 이미지 PDF 기반 인수인계서 자동 작성 및 분석 시스템입니다.
최우선 명세는 [PROTOTYPE_SPEC.md](PROTOTYPE_SPEC.md)이며, 현재 **Phase 1 + Phase 2 — Document Pipeline**까지 구현했습니다.

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
- LLM, Ollama, SQL Generation/Retrieval, 문서·문제 생성, 채점, PDF Export는 미구현
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

## Migration

Phase 2에서는 기존 6개 모델/테이블을 그대로 사용하며 **추가 migration은 없습니다**.

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

### 2026-10-01 검증 결과

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

이후에는 실제 양식의 표·목차에 대한 parser 정확도와 스캔 품질을 평가해야 합니다. LLMProvider/Ollama 작업은 Phase 3 범위입니다.

공식 참고: [PaddleOCR OCR 사용법](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html), [공식 한국어 모델](https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec), [PyMuPDF 이미지 렌더링](https://pymupdf.readthedocs.io/en/latest/recipes-images.html).
