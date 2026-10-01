# PROTOTYPE_SPEC.md

# 인수인계서 자동 작성 및 분석 시스템 — Prototype 구현 명세

## 0. 문서 목적

이 문서는 Codex가 본 프로젝트의 **동작 가능한 1차 프로토타입**을 구현하기 위한 단일 기준 문서다.

구현 목표는 다음과 같다.

1. **스캔 이미지 PDF**를 입력받는다.
2. PDF 페이지를 이미지로 변환하고 OCR을 수행한다.
3. OCR 결과를 인수인계서의 목차/필드 구조에 맞게 **구조화하여 SQLite에 저장**한다.
4. 사용자의 자연어 요청을 바탕으로 LLM이 **조회용 SQL을 생성**한다.
5. 생성된 SQL을 Python에서 검증한 뒤 SQLite에서 관련 데이터를 검색한다.
6. 검색 결과를 Context로 사용하여 LLM이 다음 작업을 수행한다.
   - 인수인계서 내용 생성
   - 문제 생성
   - 답안 평가 및 점수 계산
7. LLM 채점이 실패하면 **Python 기반 채점 로직으로 fallback**한다.
8. 생성된 인수인계서는 React 화면에서 Preview할 수 있어야 한다.
9. 생성된 인수인계서를 **PDF 파일로 Export**할 수 있어야 한다.
10. LLM 모델 또는 런타임이 변경되어도 비즈니스 로직의 수정이 최소화되도록 설계한다.
11. 기업 멘토가 요구한 **초기 데이터 구축 방식**을 프로토타입 범위에 포함한다.

---

# 1. 프로젝트 핵심 원칙

## 1.1 스캔 이미지 PDF 우선

Prototype v1의 입력 범위는 **스캔된 이미지 PDF**로 제한한다.

- 일반 Text PDF 지원은 Prototype 이후 확장 항목이다.
- PDF 자체에서 텍스트를 직접 추출하는 기능은 핵심 경로로 사용하지 않는다.
- PyMuPDF는 PDF 페이지를 이미지로 렌더링하는 용도로 사용한다.

기본 흐름:

```text
Scanned PDF
    ↓
PyMuPDF
    ↓
Page Images
    ↓
PaddleOCR
    ↓
OCR Result
    ↓
Document Structuring
    ↓
SQLite
```

---

## 1.2 LLM 비종속 구조

LLM을 시스템의 핵심 로직으로 취급하지 않는다.

LLM은 다음과 같은 **교체 가능한 AI Task 수행자**다.

- SQL Generation
- Document Generation
- Question Generation
- Scoring

실제 모델은 Prototype v1에서 하나를 공용으로 사용할 수 있지만,
코드 구조상 각 Task를 독립적인 논리 모듈로 구현한다.

```text
Business Service
    ↓
LLMProvider Interface
    ↓
OllamaLLMProvider
    ↓
Ollama Local API
    ↓
Qwen3.5-4B
```

향후 다음으로 교체할 수 있어야 한다.

- Qwen3.5-9B
- 다른 Local LLM
- 다른 Ollama 모델
- vLLM 기반 서버
- 사내 LLM API

비즈니스 서비스 코드가 Ollama SDK나 특정 모델 이름에 직접 의존하면 안 된다.

---

## 1.3 LLM 출력은 반드시 구조화 및 검증

LLM 응답은 가능한 한 자유 형식 문자열로 사용하지 않는다.

다음 계층을 반드시 거친다.

```text
LLM Output
    ↓
JSON Parse
    ↓
Pydantic Validation
    ↓
Business Logic
```

검증 실패 시:

- 재시도 가능한 Task는 1회 재시도
- Scoring Task는 Python fallback
- SQL Generation Task는 잘못된 SQL 실행 금지

---

## 1.4 Retrieval과 Generation 분리

RAG는 다음 두 단계로 구분한다.

```text
Retrieval
    +
Generation
```

Prototype v1의 기본 Retrieval 방식은 **SQLite + SQL Retrieval**이다.

Vector DB는 Prototype v1 필수 범위가 아니다.

향후 확장을 위해 인터페이스는 다음과 같이 설계한다.

```text
RetrievalStrategy
├── SqlRetrievalStrategy      # Prototype default
└── VectorRetrievalStrategy   # Future / Experimental
```

---

## 1.5 LLM 채점 실패 시 Python Fallback

채점 정책은 다음으로 확정한다.

```text
User Answer
    ↓
Scoring LLM
    ↓
Validation
    │
    ├── Success → LLM Result
    │
    └── Failure → Python Fallback
```

Python은 LLM 점수를 상시 재계산하거나 평균내기 위한 용도가 아니다.

Fallback 발생 조건은 다음과 같다.

- Ollama 연결 실패
- timeout
- 모델 실행 오류
- JSON parsing 실패
- Pydantic validation 실패
- 필수 field 누락
- score 범위 오류

---

# 2. Prototype 범위

## 2.1 반드시 구현해야 하는 기능

### A. 문서 등록

- 스캔 이미지 PDF 업로드
- PyMuPDF 페이지 렌더링
- PaddleOCR 기반 OCR
- OCR Raw Result 저장
- 문서 구조화
- 구조화 데이터 SQLite 저장
- 문서 목록 조회
- 문서 상세 조회

### B. 인수인계서 자동 생성

사용자 입력 예시:

```text
"DB 운영 업무를 담당할 신규 인계자를 위한 인수인계서를 작성해줘."
```

흐름:

```text
User Request
    ↓
SQL Generation LLM
    ↓
SQL Validator
    ↓
SQLite Retrieval
    ↓
Context Builder
    ↓
Document Generation LLM
    ↓
Pydantic Validation
    ↓
React Preview
    ↓
PDF Export
```

### C. 문제 생성

사용자 입력 예시:

```text
"서버 운영과 장애 대응 내용으로 객관식 5문제 만들어줘."
```

결과:

- 객관식 또는 주관식 문제 생성 가능
- 최소한 객관식은 반드시 구현
- 각 문제는 원천 문서/섹션과 연결
- 정답과 해설 저장

### D. 채점

- 문제 및 정답 기준과 사용자 답변을 LLM에 전달
- LLM이 점수/정답 여부/근거 반환
- 출력 유효성 검사
- 실패 시 Python fallback

### E. 초기 Seed Data

- 실제 기업 인수인계서 양식을 참고한 더미 문서
- 최소 5개 이상의 스캔 이미지 PDF
- 최소 3개 업무 카테고리 포함
- OCR을 거쳐 저장된 Seed Data 제공

---

## 2.2 Prototype 이후 확장 항목

다음은 Prototype v1에서 필수 구현하지 않는다.

- 일반 Text PDF 직접 파싱
- Vector DB
- pgvector
- Elasticsearch
- BGE-M3 기반 Vector Retrieval
- bge-reranker-v2-m3
- DOCX Export
- Google Docs Export
- 여러 LLM 동시 상주
- Fine-tuning
- LoRA
- 사용자 계정/권한 시스템
- 복잡한 멀티테넌시
- Cloud deployment
- 대규모 Queue/Worker 시스템

---

# 3. 기술 스택

## 3.1 Frontend

- React
- TypeScript
- Vite
- React Router
- Axios 또는 Fetch API
- Prototype에서는 기본 CSS 또는 가벼운 UI library 사용 가능

권장:

```text
React + TypeScript + Vite
```

---

## 3.2 Backend

- Python 3.12
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- SQLite
- PyMuPDF
- PaddleOCR
- httpx
- Jinja2

---

## 3.3 LLM Runtime

기본:

```text
Ollama
```

Prototype 모델:

```text
Qwen3.5-4B
```

환경변수에서 모델명을 지정한다.

예:

```env
OLLAMA_BASE_URL=http://localhost:11434

SQL_MODEL=qwen3.5:4b
DOCUMENT_MODEL=qwen3.5:4b
QUESTION_MODEL=qwen3.5:4b
SCORING_MODEL=qwen3.5:4b
```

모든 Task가 현재는 같은 모델을 사용해도 된다.

---

## 3.4 OCR

Framework:

```text
PaddleOCR
```

기본 OCR 계열:

```text
PP-OCRv5
```

한국어 Recognition:

```text
korean_PP-OCRv5_mobile_rec
```

목적:

- 한국어
- 영어
- 숫자

인수인계서 스캔 PDF OCR.

문서 레이아웃/구조 분석은 OCR과 분리한다.
PP-StructureV3는 추후 비교 후보이며 Prototype v1의 필수 의존성으로 고정하지 않는다.

---

# 4. 전체 시스템 아키텍처

```text
┌───────────────────────────────────────┐
│                React                  │
│                                       │
│ PDF Upload / Document List            │
│ Document Preview                      │
│ Handover Generation                   │
│ Question Generation                   │
│ Quiz / Scoring                        │
│ PDF Export                            │
└───────────────────┬───────────────────┘
                    │ HTTP / JSON
                    ▼
┌───────────────────────────────────────┐
│               FastAPI                 │
│                                       │
│ API Layer                             │
│ Service Layer                         │
│ Pydantic Validation                   │
└──────┬──────────────────────┬─────────┘
       │                      │
       │                      │
       ▼                      ▼
Document Pipeline         AI Task Layer
       │                      │
       ▼                      ▼
PyMuPDF                LLMProvider
       │                      │
       ▼                      ▼
Page Image          OllamaLLMProvider
       │                      │
       ▼                      ▼
PaddleOCR               Ollama API
       │                      │
       ▼                      ▼
OCR Result            Qwen3.5-4B
       │
       ▼
Structure Parser
       │
       ▼
SQLite
       ▲
       │
SQL Retrieval
       ▲
       │
SQL Validator
       ▲
       │
SQL Generation LLM
```

---

# 5. Backend Layering

Backend는 다음 구조를 권장한다.

```text
app/
├── api/
├── core/
├── db/
├── models/
├── schemas/
├── repositories/
├── services/
├── llm/
├── ocr/
├── retrieval/
├── parsing/
├── scoring/
├── rendering/
└── utils/
```

역할:

### api
FastAPI Router.

### core
- config
- logging
- exceptions

### db
- SQLAlchemy session
- engine
- migrations

### models
SQLAlchemy ORM Models.

### schemas
Pydantic request/response models.

### repositories
DB access.

### services
비즈니스 로직.

### llm
LLM 추상화 및 Ollama 구현.

### ocr
PyMuPDF + PaddleOCR pipeline.

### retrieval
SQL / 향후 Vector Retrieval.

### parsing
OCR 결과를 도메인 구조로 변환.

### scoring
Python fallback scoring.

### rendering
Jinja2 및 PDF Export.

---

# 6. 권장 프로젝트 디렉터리 구조

```text
handover-ai/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── documents.py
│   │   │   ├── generation.py
│   │   │   ├── questions.py
│   │   │   └── scoring.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   └── exceptions.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   └── seed.py
│   │   ├── models/
│   │   │   ├── document.py
│   │   │   ├── section.py
│   │   │   ├── handover_item.py
│   │   │   ├── question.py
│   │   │   └── scoring.py
│   │   ├── schemas/
│   │   │   ├── document.py
│   │   │   ├── generation.py
│   │   │   ├── question.py
│   │   │   ├── scoring.py
│   │   │   └── llm.py
│   │   ├── repositories/
│   │   │   ├── document_repository.py
│   │   │   ├── section_repository.py
│   │   │   └── question_repository.py
│   │   ├── services/
│   │   │   ├── document_service.py
│   │   │   ├── handover_generation_service.py
│   │   │   ├── question_service.py
│   │   │   └── scoring_service.py
│   │   ├── llm/
│   │   │   ├── provider.py
│   │   │   ├── ollama_provider.py
│   │   │   ├── prompts/
│   │   │   │   ├── sql_generation.py
│   │   │   │   ├── document_generation.py
│   │   │   │   ├── question_generation.py
│   │   │   │   └── scoring.py
│   │   │   └── tasks/
│   │   │       ├── sql_task.py
│   │   │       ├── document_task.py
│   │   │       ├── question_task.py
│   │   │       └── scoring_task.py
│   │   ├── ocr/
│   │   │   ├── pdf_renderer.py
│   │   │   ├── paddle_ocr.py
│   │   │   └── pipeline.py
│   │   ├── parsing/
│   │   │   ├── structure_parser.py
│   │   │   └── section_mapper.py
│   │   ├── retrieval/
│   │   │   ├── base.py
│   │   │   ├── sql_retrieval.py
│   │   │   └── sql_validator.py
│   │   ├── scoring/
│   │   │   └── python_fallback.py
│   │   ├── rendering/
│   │   │   ├── template_renderer.py
│   │   │   ├── pdf_exporter.py
│   │   │   └── templates/
│   │   │       └── handover.html
│   │   └── utils/
│   ├── tests/
│   ├── alembic/
│   ├── data/
│   │   ├── uploads/
│   │   ├── pages/
│   │   ├── ocr/
│   │   ├── exports/
│   │   └── seed/
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── types/
│   │   └── routes/
│   ├── package.json
│   └── vite.config.ts
│
├── sample-data/
│   ├── scanned-pdfs/
│   └── metadata/
│
├── docker-compose.yml
├── .gitignore
└── PROTOTYPE_SPEC.md
```

---

# 7. Database 설계

Prototype v1은 SQLite를 사용한다.

## 7.1 documents

```text
documents
---------
id                  INTEGER PK
title               VARCHAR
document_type       VARCHAR
department          VARCHAR NULL
source_filename     VARCHAR
source_path         VARCHAR
ocr_status          VARCHAR
parse_status        VARCHAR
created_at          DATETIME
updated_at          DATETIME
```

상태 예:

```text
ocr_status:
- pending
- processing
- completed
- failed

parse_status:
- pending
- completed
- failed
```

---

## 7.2 document_pages

```text
document_pages
--------------
id              INTEGER PK
document_id     INTEGER FK
page_number     INTEGER
image_path      VARCHAR
raw_text        TEXT
ocr_json        TEXT
created_at      DATETIME
```

`ocr_json`에는 bounding box 및 confidence를 포함한 OCR 원본 JSON을 저장한다.

---

## 7.3 document_sections

```text
document_sections
-----------------
id              INTEGER PK
document_id     INTEGER FK
section_type    VARCHAR
section_title   VARCHAR
content         TEXT
sequence        INTEGER
source_page     INTEGER NULL
created_at      DATETIME
```

예상 `section_type`:

```text
overview
responsibilities
systems
procedures
precautions
contacts
troubleshooting
schedule
references
other
```

---

## 7.4 handover_items

```text
handover_items
--------------
id                  INTEGER PK
document_id         INTEGER FK
section_id          INTEGER FK NULL
category            VARCHAR
task_name           VARCHAR
description         TEXT
procedure           TEXT NULL
precaution          TEXT NULL
importance          INTEGER NULL
frequency           VARCHAR NULL
related_system      VARCHAR NULL
contact_info        TEXT NULL
created_at          DATETIME
```

`importance` 권장 범위:

```text
1 ~ 5
```

---

## 7.5 questions

```text
questions
---------
id                  INTEGER PK
document_id         INTEGER FK NULL
section_id          INTEGER FK NULL
question_type       VARCHAR
question_text       TEXT
choices_json        TEXT NULL
correct_answer      TEXT
explanation         TEXT NULL
difficulty          VARCHAR NULL
created_at          DATETIME
```

`question_type`:

```text
multiple_choice
short_answer
```

---

## 7.6 scoring_results

```text
scoring_results
---------------
id                  INTEGER PK
question_id         INTEGER FK
user_answer         TEXT
score               REAL
is_correct          BOOLEAN NULL
reason              TEXT NULL
scoring_method      VARCHAR
created_at          DATETIME
```

`scoring_method`:

```text
llm
python_fallback
```

---

# 8. OCR Pipeline

## 8.1 PDF Render

PyMuPDF 사용.

Pseudo Flow:

```python
pdf = fitz.open(pdf_path)

for page_number, page in enumerate(pdf):
    pixmap = page.get_pixmap(dpi=200)
    save_image(...)
```

기본 DPI:

```text
200
```

필요 시 300 DPI까지 조정 가능하게 한다.

환경변수:

```env
PDF_RENDER_DPI=200
```

---

## 8.2 PaddleOCR

PaddleOCR를 이용한다.

기본 Recognition 모델:

```text
korean_PP-OCRv5_mobile_rec
```

OCR 결과는 최소 다음 값을 보존한다.

```json
{
  "text": "정기 DB 백업",
  "confidence": 0.98,
  "bbox": []
}
```

Raw OCR 결과를 버리지 않는다.

이유:

- 구조화 실패 시 재처리 가능
- OCR 성능 분석 가능
- 향후 다른 Parser 적용 가능

---

# 9. 문서 구조화

OCR 결과를 바로 LLM에 넘겨 DB에 저장하지 않는다.

Prototype 기본 방식:

```text
OCR Result
    ↓
Rule / Template based Section Mapper
    ↓
Structured Sections
    ↓
SQLite
```

## 9.1 Section Mapping

기본적으로 인식할 제목 키워드:

```text
업무 개요
주요 업무
담당 업무
시스템 정보
업무 절차
업무 방법
주의사항
장애 대응
비상 연락망
담당자
일정
참고자료
```

이 목록은 코드에 산재해서 하드코딩하지 말고 설정 파일 또는 중앙 상수로 관리한다.

예:

```yaml
section_aliases:
  overview:
    - 업무 개요
    - 개요
  responsibilities:
    - 주요 업무
    - 담당 업무
  precautions:
    - 주의사항
    - 유의사항
```

Prototype에서 완전 자동 구조화가 어려운 경우, raw OCR 결과를 보존하고 section parser를 교체 가능하게 설계한다.

---

# 10. LLM Provider 설계

## 10.1 Interface

예시:

```python
from abc import ABC, abstractmethod

class LLMProvider(ABC):

    @abstractmethod
    async def generate(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: type | None = None,
    ):
        ...
```

Business Service에서 직접 Ollama를 호출하지 않는다.

---

## 10.2 Ollama Provider

`OllamaLLMProvider`가 Ollama REST API를 호출한다.

기본 URL:

```text
http://localhost:11434
```

timeout을 설정한다.

환경변수:

```env
OLLAMA_TIMEOUT_SECONDS=120
```

---

# 11. SQL Generation

## 11.1 목적

사용자의 자연어 요청을 DB 조회 SQL로 변환한다.

예:

```text
사용자:
"DB 운영 및 백업과 관련된 업무 내용을 찾아줘."
```

LLM 출력:

```json
{
  "sql": "SELECT task_name, description, precaution FROM handover_items WHERE category = 'Database' LIMIT 100",
  "reason": "DB 운영과 백업 관련 데이터를 검색하기 위한 쿼리"
}
```

---

## 11.2 LLM에 Schema 제공

LLM에게 DB schema를 명시적으로 제공한다.

예:

```text
Allowed tables:

documents(...)
document_sections(...)
handover_items(...)
```

LLM이 Schema를 추측하게 두지 않는다.

---

# 12. SQL Validator

LLM이 생성한 SQL은 **절대 바로 실행하지 않는다.**

반드시 Validator를 통과해야 한다.

## 12.1 검사 항목

### 허용

```text
SELECT
```

### 금지

```text
INSERT
UPDATE
DELETE
DROP
ALTER
CREATE
REPLACE
PRAGMA
ATTACH
DETACH
```

### 추가 검사

- 존재하는 Table인지
- 존재하는 Column인지
- 허용된 Table만 사용하는지
- 다중 Statement가 아닌지
- semicolon 뒤 추가 명령 없는지
- LIMIT가 없는 경우 최대 LIMIT 강제 적용 가능

권장 최대 row:

```text
100
```

---

## 12.2 SQL Validation 실패

실패하면:

```text
1회 LLM 재생성
```

재생성에도 실패하면 API error를 반환한다.

잘못된 SQL을 강제 실행하면 안 된다.

가능하면 regex만으로 검증하지 말고 SQL parser를 사용한다.

---

# 13. Retrieval

Prototype:

```text
SqlRetrievalStrategy
```

Interface 예:

```python
class RetrievalStrategy(ABC):

    @abstractmethod
    async def retrieve(self, query: str) -> list["RetrievedItem"]:
        ...
```

향후:

```text
VectorRetrievalStrategy
```

추가 가능.

---

# 14. Context Builder

DB 결과를 그대로 LLM에 던지지 않는다.

LLM Context로 변환한다.

예:

```text
[업무 1]
업무명: 일일 DB 백업 확인
카테고리: Database
설명: ...
주의사항: ...

[업무 2]
...
```

Context 길이가 너무 길면:

1. 관련성이 높은 데이터 우선
2. 최대 Row 제한
3. 최대 문자/토큰 제한

Prototype에서는 간단한 문자 길이 제한으로 구현 가능.

---

# 15. Document Generation

## 15.1 입력

- 사용자 요청
- Retrieved Context
- 목표 문서 목차
- Output Schema

---

## 15.2 출력 Schema

예:

```python
class GeneratedSection(BaseModel):
    section_type: str
    title: str
    content: str

class GeneratedDocument(BaseModel):
    title: str
    sections: list[GeneratedSection]
```

LLM 출력은 반드시 위 구조로 Parsing한다.

---

## 15.3 기본 문서 목차

Prototype 기본 인수인계서:

```text
1. 업무 개요
2. 주요 업무
3. 관련 시스템
4. 업무 절차
5. 주의사항
6. 장애 대응
7. 담당자 및 연락처
8. 참고자료
```

없는 정보는 임의 생성하지 않도록 Prompt에 명시한다.

Prototype 기본 정책:

```text
관련 정보 없음
```

으로 표기한다.

---

# 16. Question Generation

## 16.1 입력

- Retrieved Context
- 문제 수
- 문제 유형
- 난이도

---

## 16.2 Output Schema

```python
class GeneratedQuestion(BaseModel):
    question_type: Literal["multiple_choice", "short_answer"]
    question: str
    choices: list[str] | None
    correct_answer: str
    explanation: str
    source_section_id: int | None
```

응답:

```python
class QuestionGenerationResult(BaseModel):
    questions: list[GeneratedQuestion]
```

---

## 16.3 Prototype 기본값

```text
문제 유형: multiple_choice
문제 수: 5
```

문제 생성 시 저장된 문서 Context 밖의 사실을 정답 근거로 사용하지 않도록 Prompt에 명시한다.

---

# 17. Scoring

## 17.1 정책

**LLM First, Python Fallback**

```text
User Answer
    ↓
Scoring LLM
    ↓
Validation
    │
    ├── Success → LLM Result
    │
    └── Failure → Python Fallback
```

Python과 LLM 점수를 항상 동시에 계산하지 않는다.

---

## 17.2 LLM Scoring Output

```python
class ScoringResult(BaseModel):
    score: float
    is_correct: bool | None
    reason: str
```

score 범위:

```text
0 ~ 100
```

---

## 17.3 Python Fallback

### 객관식

```text
사용자 선택 == correct_answer
→ 100

그 외
→ 0
```

### 단답형

Prototype에서는 normalized exact match.

Normalization:

- trim
- English lower-case
- 다중 whitespace 정리

향후 fuzzy matching 가능.

---

# 18. React 화면

Prototype 최소 페이지:

```text
/
├── Documents
├── Upload
├── Generate
├── Questions
└── Quiz
```

---

## 18.1 Documents

기능:

- 저장 문서 목록
- 문서 상태
- 문서 상세
- OCR 결과 확인
- 구조화 Section 확인

---

## 18.2 Upload

기능:

- PDF 선택
- 업로드
- OCR 진행 결과
- Parsing 상태

Prototype에서는 polling 방식 가능.

---

## 18.3 Generate

입력:

- 사용자 요청
- 대상 document 선택 optional

출력:

- 인수인계서 Preview
- PDF Export button

---

## 18.4 Questions

입력:

- 대상 문서
- 문제 수
- 문제 유형

출력:

- 생성 문제
- 정답/해설 표시 토글

---

## 18.5 Quiz

- 문제 표시
- 사용자 답 입력
- Submit
- 점수
- 채점 방식 표시

예:

```text
채점 방식: LLM
```

또는

```text
채점 방식: Python fallback
```

---

# 19. API 명세

## 19.1 Health

### GET /api/health

Response:

```json
{
  "status": "ok"
}
```

---

## 19.2 Documents

### POST /api/documents/upload

multipart/form-data

```text
file: PDF
```

response:

```json
{
  "document_id": 1,
  "status": "processing"
}
```

### GET /api/documents

문서 목록.

### GET /api/documents/{document_id}

문서 상세.

### GET /api/documents/{document_id}/sections

구조화 Section.

---

## 19.3 Generation

### POST /api/generation/handover

request:

```json
{
  "prompt": "DB 운영 업무를 위한 인수인계서를 작성해줘.",
  "document_ids": [1, 2]
}
```

response:

```json
{
  "title": "...",
  "sections": []
}
```

### POST /api/generation/handover/pdf

생성된 Document JSON을 입력받아 PDF 반환.

Content-Type:

```text
application/pdf
```

---

## 19.4 Questions

### POST /api/questions/generate

request:

```json
{
  "document_ids": [1],
  "question_type": "multiple_choice",
  "count": 5,
  "prompt": "장애 대응 내용을 중심으로 문제를 만들어줘."
}
```

---

## 19.5 Scoring

### POST /api/scoring/evaluate

request:

```json
{
  "question_id": 1,
  "answer": "2"
}
```

response:

```json
{
  "score": 100,
  "is_correct": true,
  "reason": "...",
  "scoring_method": "llm"
}
```

---

# 20. PDF Export

Jinja2 Template으로 HTML을 생성한다.

```text
GeneratedDocument
    ↓
Jinja2
    ↓
HTML
    ↓
PDF Exporter
    ↓
PDF
```

PDF 생성 library는 Prototype 구현 시 macOS 로컬 환경에서 설치 및 사용이 안정적인 방식을 선택한다.

중요:

- PDF Export layer를 별도 interface로 작성
- PDF 생성 코드가 LLM service에 들어가면 안 됨
- 나중에 DOCX exporter 추가 가능해야 함

예:

```text
DocumentExporter
├── PdfExporter
├── DocxExporter          # future
└── GoogleDocsExporter    # future
```

---

# 21. 초기 데이터 구축

기업 멘토 요구사항에 따라 초기 데이터 구축 과정을 Prototype에 포함한다.

## 21.1 Seed Document 작성

실제 기업에서 사용하는 인수인계서 구조를 참고하되 실제 기업 기밀 데이터는 사용하지 않는다.

최소 5개.

권장 카테고리:

```text
Database
Backend
Infrastructure
Network
Operations
```

예:

```text
1. DB 운영 인수인계서
2. 백엔드 API 운영 인수인계서
3. Linux 서버 운영 인수인계서
4. 네트워크 장애 대응 인수인계서
5. 배포/모니터링 인수인계서
```

각 Seed 문서는 다음 항목을 가능한 한 포함한다.

```text
업무 개요
주요 업무
관련 시스템
업무 절차
주의사항
장애 대응
담당자
참고자료
```

---

## 21.2 Seed Pipeline

Seed 데이터를 DB에 직접 INSERT하는 것으로 끝내지 않는다.

가능하면 실제 시스템 입력 흐름을 거친다.

```text
Seed Source Document
    ↓
PDF
    ↓
Image / Scan Style
    ↓
OCR
    ↓
Structuring
    ↓
SQLite
```

이렇게 해야 OCR부터 데이터 저장까지 전체 Pipeline을 검증할 수 있다.

다만 테스트 편의를 위해 **정답 기준용 canonical metadata**는 별도 JSON/YAML로 유지해도 된다.

예:

```text
sample-data/
├── scanned-pdfs/
└── metadata/
    ├── db_handover.expected.json
    └── network_handover.expected.json
```

이 metadata는 OCR 결과 품질을 비교하기 위한 ground truth 성격이며,
실제 운영 흐름의 입력으로 DB에 직접 넣지 않는다.

---

# 22. 환경 변수

`.env.example`

```env
APP_ENV=development

DATABASE_URL=sqlite:///./data/app.db

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_TIMEOUT_SECONDS=120

SQL_MODEL=qwen3.5:4b
DOCUMENT_MODEL=qwen3.5:4b
QUESTION_MODEL=qwen3.5:4b
SCORING_MODEL=qwen3.5:4b

PDF_RENDER_DPI=200

UPLOAD_DIR=./data/uploads
PAGE_IMAGE_DIR=./data/pages
OCR_RESULT_DIR=./data/ocr
EXPORT_DIR=./data/exports

MAX_RETRIEVAL_ROWS=100
MAX_CONTEXT_CHARS=20000
```

---

# 23. Error Handling

공통 Error schema:

```json
{
  "code": "ERROR_CODE",
  "message": "Human readable message",
  "detail": {}
}
```

예:

```text
OCR_FAILED
OLLAMA_UNAVAILABLE
LLM_RESPONSE_INVALID
SQL_GENERATION_FAILED
SQL_VALIDATION_FAILED
DOCUMENT_NOT_FOUND
PDF_EXPORT_FAILED
```

Stack trace를 Frontend에 노출하지 않는다.

---

# 24. Logging

최소 다음 이벤트를 로그로 기록한다.

```text
PDF upload
OCR start/end
OCR failure
Document parsing start/end
LLM request task type
LLM response validation error
Generated SQL
SQL validation result
Retrieval row count
Scoring fallback
PDF export
```

민감한 문서 전체 본문은 Production log에 출력하지 않는 구조를 권장한다.

Prototype에서는 Debug logging을 환경변수로 on/off할 수 있게 한다.

---

# 25. Test 요구사항

## 25.1 Unit Test

필수:

```text
SQL Validator
Section Mapper
Python Fallback Scoring
Pydantic Output Validation
Context Builder
```

---

## 25.2 Integration Test

최소 다음 Flow를 테스트한다.

### Test 1

```text
PDF Upload
→ OCR
→ SQLite
```

### Test 2

```text
Natural Language
→ SQL Generation
→ SQL Validator
→ Retrieval
```

LLM은 mock 가능.

### Test 3

```text
Retrieval Context
→ Document Generation
→ Pydantic validation
```

### Test 4

```text
Scoring LLM Failure
→ Python Fallback
```

### Test 5

```text
GeneratedDocument
→ PDF Export
```

---

# 26. SQL Validator Test Cases

반드시 포함한다.

### 허용

```sql
SELECT task_name, description
FROM handover_items
WHERE category = 'Database';
```

### 차단

```sql
DROP TABLE handover_items;
```

```sql
DELETE FROM handover_items;
```

```sql
SELECT nonexistent_column
FROM handover_items;
```

```sql
SELECT *
FROM nonexistent_table;
```

```sql
SELECT * FROM handover_items;
DROP TABLE documents;
```

---

# 27. Acceptance Criteria

Prototype 완료 기준.

## 27.1 OCR

스캔 PDF를 업로드하면:

- 각 페이지 이미지 생성
- OCR 실행
- Raw OCR 결과 저장
- DB 문서 생성

## 27.2 Structuring

OCR 결과가 최소한 다음 형태로 저장되어야 한다.

```text
document_sections
handover_items
```

## 27.3 Retrieval

사용자 요청으로 LLM이 SQL을 생성하고:

- Validator 통과
- SQLite 조회
- Context 생성

까지 동작해야 한다.

## 27.4 Document Generation

사용자 요청에 따라:

```text
Structured GeneratedDocument
```

를 생성한다.

React에서 Preview 가능해야 한다.

## 27.5 PDF

GeneratedDocument를 PDF로 내려받을 수 있어야 한다.

## 27.6 Question

저장된 문서 내용을 기반으로 문제를 생성할 수 있어야 한다.

## 27.7 Scoring

정답 제출 시:

1. LLM 채점 우선
2. LLM 실패 시 Python fallback

이 동작해야 한다.

DB에는 scoring method가 저장되어야 한다.

## 27.8 Model Replacement

환경변수의 모델명을 변경하면 Business Service 수정 없이 다른 Ollama 모델을 사용할 수 있어야 한다.

---

# 28. 구현 우선순위

Codex는 다음 순서로 구현한다.

## Phase 1 — Skeleton

1. Backend / Frontend 프로젝트 생성
2. Config
3. SQLite 연결
4. SQLAlchemy models
5. Alembic migration
6. 기본 API health check

## Phase 2 — Document Pipeline

1. PDF upload
2. PyMuPDF renderer
3. PaddleOCR adapter
4. OCR storage
5. Structure parser
6. DB persistence
7. React Upload / Documents UI

## Phase 3 — LLM Infrastructure

1. LLMProvider
2. Ollama Provider
3. Pydantic output schemas
4. Model config
5. Task-specific prompts

## Phase 4 — Retrieval

1. Schema description generator
2. SQL Generation task
3. SQL Validator
4. SqlRetrievalStrategy
5. Context Builder

## Phase 5 — Document Generation

1. Retrieval
2. Document Generation Task
3. Preview API
4. React Preview

## Phase 6 — PDF Export

1. Jinja2 template
2. HTML render
3. PDF Exporter
4. Download API
5. React Download button

## Phase 7 — Question / Scoring

1. Question Generation
2. Questions DB
3. Quiz UI
4. LLM Scoring
5. Python fallback
6. scoring_results persistence

## Phase 8 — Seed / Test / Polish

1. Seed PDF 5개 준비
2. Seed pipeline 실행
3. Unit tests
4. Integration tests
5. Error handling
6. README 정리

---

# 29. Codex 구현 지침

Codex는 다음 지침을 반드시 따른다.

1. 한 번에 전체 시스템을 거대한 파일로 구현하지 않는다.
2. Layer와 responsibility를 분리한다.
3. Model 이름을 Business Service에 하드코딩하지 않는다.
4. Ollama 호출을 Service 곳곳에 직접 작성하지 않는다.
5. SQL을 LLM 출력 그대로 실행하지 않는다.
6. OCR Raw Result를 삭제하지 않는다.
7. LLM 출력은 Pydantic으로 검증한다.
8. Scoring LLM 실패 시 Python fallback을 반드시 구현한다.
9. Vector DB를 임의로 추가하지 않는다.
10. Fine-tuning을 구현하지 않는다.
11. General PDF parsing을 Prototype 핵심 범위로 확장하지 않는다.
12. 구현 중 명세가 애매한 경우 가장 단순한 Prototype 구현을 선택한다.
13. 기능 추가보다 Acceptance Criteria 충족을 우선한다.
14. 테스트 가능한 구조를 유지한다.
15. 각 Phase 완료 시 해당 Phase의 테스트가 통과해야 다음 Phase로 진행한다.

---

# 30. Prototype에서 아직 비교가 필요한 항목

다음은 구현 가능하게 인터페이스를 열어두되 하나로 영구 확정하지 않는다.

## OCR / 문서 구조화

```text
현재 기본:
PaddleOCR PP-OCRv5
+
Rule / Template based parser

비교 후보:
PP-StructureV3
기타 문서 구조 분석 방식
```

## Retrieval

```text
현재 기본:
SQLite SQL Retrieval

향후 비교:
BGE-M3 Vector Retrieval
Hybrid Retrieval
```

## 생성 모델 크기

```text
현재:
Qwen3.5-4B

향후 비교:
Qwen3.5-9B 이상
```

반면 다음은 현재 설계에서 확정한다.

```text
LLM Runtime:
Ollama

Scoring:
LLM first → failure 시 Python fallback

Backend:
FastAPI + Pydantic

Database:
SQLite

Frontend:
React

PDF Processing:
PyMuPDF

Template:
Jinja2
```

---

# 31. 완료 후 확인해야 할 대표 시나리오

최종적으로 다음 End-to-End Demo가 가능해야 한다.

```text
1. 사용자가 스캔된 인수인계서 PDF 업로드

2. 시스템이 PDF를 페이지 이미지로 변환

3. PaddleOCR가 텍스트 추출

4. Parser가 목차/업무 데이터를 구조화

5. SQLite에 저장

6. 사용자가
   "DB 운영 인수인계서를 만들어줘."
   입력

7. LLM이 조회 SQL 생성

8. SQL Validator가 SQL 검증

9. SQLite에서 관련 데이터 조회

10. Context Builder가 LLM Context 생성

11. Document Generation LLM이 인수인계서 생성

12. Pydantic이 결과 검증

13. React에서 Preview

14. PDF Export

15. 같은 문서 데이터로 문제 5개 생성

16. 사용자가 문제 풀이

17. LLM이 채점

18. LLM 채점 실패를 강제로 발생시키는 테스트에서
    Python fallback 정상 동작
```

이 시나리오가 처음부터 끝까지 동작하면 Prototype v1의 핵심 목표를 달성한 것으로 본다.
