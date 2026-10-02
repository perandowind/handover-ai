# Phase 8A 결과 — 2026-10-02

## 수행 범위

Synthetic PDF → 기존 Upload API → PyMuPDF → 실제 PaddleOCR → 기존 SectionMapper → SQLite까지만 검증했습니다. LLM 호출, 생성·채점·Export를 연결하는 전체 End-to-End 시나리오는 수행하지 않았습니다. 기존 unit/integration 회귀 테스트는 모두 실행했습니다. README와 애플리케이션 코드는 변경하지 않았습니다.

원문/참고 양식/재현 절차는 [SOURCE_NOTES](../SOURCE_NOTES.md)를 참조하세요. 다섯 문서 모두 가상 조직/역할과 example.invalid 연락처를 사용하며 실제 기업·직원·기밀정보를 포함하지 않습니다.

## PDF와 적재 결과

모두 `sample-data/scanned-pdfs/` 아래에 있으며 각 2페이지입니다. 200 DPI 회색조 이미지로 PDF를 구성했습니다. 텍스트 레이어가 없음을 검사하고 Poppler로 렌더링한 10페이지를 모두 시각적으로 확인했습니다.

| 업무 영역 | 문서 | PDF | OCR/Parsing | DB 섹션/업무 항목 | 키워드 |
| --- | --- | --- | --- | --- | --- |
| Database | DB 운영 인수인계서 | seed-database.pdf | completed/completed | 9/9 | 18/18 |
| Backend | 백엔드 API 운영 인수인계서 | seed-backend.pdf | completed/completed | 9/9 | 18/18 |
| Infrastructure | Linux 서버 운영 인수인계서 | seed-infrastructure.pdf | completed/completed | 9/9 | 18/18 |
| Network | 네트워크 장애 대응 인수인계서 | seed-network.pdf | completed/completed | 9/9 | 18/18 |
| Operations | 배포 및 모니터링 인수인계서 | seed-operations.pdf | completed/completed | 9/9 | 18/18 |

합계: documents 5, document_pages 10, document_sections 45, handover_items 45. 질문/채점 테이블은 모두 0행입니다. foreign_key_check 오류와 업무 항목/섹션 간 문서 ID 불일치는 모두 0입니다.

각 문서의 필수 8개 section_type과 source_page를 확인했습니다. 나머지 1개는 기존 parser가 보존한 머리말 `other`입니다. 제목 OCR도 확인했습니다. 전체 90개 기준 키워드가 해당 섹션 본문에서 확인됐습니다. 합격 기준은 각 문서 키워드 90% 이상, 모든 필수 섹션 및 source_page 존재, 제목 인식, Raw OCR 보존, 페이지 수와 업무 항목 연결 정상입니다. 기준은 OCR 실행 전에 작성했습니다.

키워드는 공백 제거/대소문자 정규화 후 포함 여부로 검사합니다. **100%는 키워드 recall이며 전체 문자의 OCR 정확도(CER)가 아닙니다.** 이메일/식별자/숫자의 완전 일치 검사는 포함하지 않습니다.

## 보존 위치

성공한 실제 실행의 영구 로컬 경로:

```text
backend/data/seed-runs/20261002T080355249351/
├── app.db
├── uploads/                  # 실제 업로드 PDF 사본
├── pages/<document_id>/      # Pipeline이 렌더링한 PNG
├── ocr/<document_id>/        # native raw_results + text/confidence/bbox
├── seed-*.document.json      # 서비스 상세 API 응답
└── report.json
```

동일 Raw OCR JSON이 `document_pages.ocr_json`과 파일에 보존되는 것을 검사했습니다. 기존 `data/app.db`에는 INSERT하지 않았습니다. Seed metadata는 기대값 비교에만 사용했습니다. 위 런타임 파일들은 Git에서 제외합니다. 재현 가능한 PDF/원문/ground truth/실제 OCR 녹화 결과는 버전 관리 대상입니다.

기계 판독 결과: [phase8a-ocr.json](phase8a-ocr.json). PDF와 metadata SHA-256, 모델명, 라이브러리 버전, 문서별 섹션/키워드 결과를 포함합니다. PaddleOCR 3.3.3, PaddlePaddle 3.2.2, PyMuPDF 1.28.2, PP-OCRv5_mobile_det + korean_PP-OCRv5_mobile_rec, CPU, 200 DPI로 실행했습니다.

## 테스트 결과

backend에서 실행:

```bash
RUN_REAL_SEED_OCR=1 \
PADDLE_PDX_CACHE_HOME="$PWD/data/paddlex" \
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
uv run pytest -q
```

**418 passed, 0 failed, 0 skipped, 6 warnings / 98.07초**

- 기존 398개 테스트 모두 통과.
- 신규 20개: PDF/metadata 계약 5, 비교기 unit 9, 녹화 OCR→SQLite integration 5, 실제 PaddleOCR로 5문서 처리 integration 1.
- Unit 중심 suite: 242 passed. Integration 중심 suite: 176 passed. 기존 테스트에 전역 marker 구분이 없어 파일/테스트 단위로 분류했습니다. Integration 파일에 포함된 보조 unit 검사는 해당 suite에 함께 집계했습니다. 정확한 파일별 개수 및 분류는 [phase8a-tests.json](phase8a-tests.json)을 참조하세요.
- 신규 비교기 테스트는 키워드 누락, 잘못된 source_page, 제목 누락, 처리 실패, raw 파일 불일치, 끊어진 section 연결, 이미지 누락을 의도적으로 만들어 실패 판정을 확인합니다.
- 실제 OCR 통합 테스트는 CLI 성공 실행과 별개로 pytest 임시 DB에서 5개 PDF를 다시 처리했습니다. 모델/실제 OCR을 모킹하지 않았습니다.
- 기본 pytest에서는 실제 OCR 테스트 1개만 opt-in으로 skip됩니다. 녹화 OCR 재생을 실제 모델 실행으로 보고하지 않습니다.
- 경고: 기존 PyMuPDF SWIG deprecation 5개, Paddle의 선택적 ccache 부재 1개. 첫 CLI 실행에서 sandbox의 sysctl 조회 제한 메시지도 있었지만 추론·적재는 정상 완료됐습니다.

## 발견 사항과 Phase 8B 전 확인

개발 중 새 검증 스크립트가 API에 노출하지 않는 `page.image_path` 및 `item.document_id`를 참조해 KeyError가 발생했습니다. 실행 설정의 page 디렉터리와 API가 제공하는 section 연결로 수정했고, DB의 문서 연결은 별도 읽기 전용 조회로 검사합니다. 수정 후 CLI 및 전체 테스트가 통과했습니다. 기존 서비스 오류로 인한 수정은 없었습니다.

8B를 막는 실패는 없습니다. 다만 다음 사항을 알고 진행해야 합니다.

- 기준 데이터는 깨끗한 스캔을 모사합니다. 흐림·회전·수기·복잡한 표 성능을 일반화할 수 없습니다.
- 반복 머리말/꼬리말은 인접 섹션 본문에 남을 수 있습니다. 기존 규칙 기반 parser 동작을 유지했습니다.
- `handover_items.category`는 기존 section_type이며 Database 등의 업무 영역으로 자동 변경하지 않습니다. 각 업무 영역은 원문 및 ground truth에 명시되어 있습니다.
- LLM을 포함한 전체 시나리오와 최종 README 정리는 8B에서 수행해야 합니다.
