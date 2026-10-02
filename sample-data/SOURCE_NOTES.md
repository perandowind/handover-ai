# Phase 8A synthetic seed provenance

작성일: 2026-10-02 (Asia/Seoul)

공개 기업용 [인수인계규정 및 별지서식 소개](https://www.yesform.com/forms/vform_337838.php)의 업무 인계·인수 및 확인 개념을 참고했습니다. 공개 [업무 인수인계서 양식 설명](https://www.bizdang.com/%EC%9E%90%EB%A3%8C%EC%8B%A4/%EC%97%85%EB%AC%B4-%EC%9D%B8%EC%88%98%EC%9D%B8%EA%B3%84%EC%84%9C)의 인계·인수·입회 확인란 구성도 참고했습니다. 유료 양식이나 실제 기업 문서 본문은 다운로드·복제하지 않았습니다. 구체적인 8개 목차는 PROTOTYPE_SPEC.md를 따릅니다.

본문, 작업 시간, 식별자, 미결 사항과 역할은 모두 가상 데이터입니다. 기업명·직원 실명·비밀번호·실제 연락처는 사용하지 않았습니다. 기술 제품명은 업무 영역을 표현하기 위한 것이며 해당 업체의 내부 문서가 아닙니다. 연락처는 `example.invalid` 주소입니다.

- `sources/seed-*.json`: 가상 원문. PDF 생성기에만 입력합니다.
- `scanned-pdfs/seed-*.pdf`: 각 2페이지, 200 DPI 회색조 JPEG만 포함하는 이미지 PDF. 숨겨진 텍스트 레이어 없음.
- `metadata/seed-*.expected.json`: 제목, 영역, 페이지, 섹션별 키워드와 합격 기준. 검증기에만 입력하며 DB INSERT 용도로 사용하지 않습니다.
- `ocr-recordings/seed-*.json`: 실제 PaddleOCR 결과의 `rec_texts/rec_scores/rec_polys`를 그대로 추린 회귀 테스트 fixture. Ground truth에서 만든 가짜 OCR이 아닙니다. 전체 native raw는 실행 디렉터리의 `ocr/`에 보존합니다.
- `reports/`: 실행 결과 및 Phase 8A 검증 기록.

기존 parser는 머리말을 `other`로 보존하므로 DB에는 통상 9개 섹션이 생깁니다. 반복 머리말과 확인란은 인접 섹션 본문에 남을 수 있습니다. category는 기존 설계의 section_type이며 업무 영역 enum으로 변경하지 않았습니다.

현재 PDF는 깨끗한 스캔을 모사한 기준 데이터입니다. 실제 종이 스캔의 기울어짐·흐림·필기·복잡한 표를 포괄하지 않습니다. 키워드 검증은 공백/대소문자만 정규화한 포함 검사이며 전체 글자 정확도(CER)나 이메일·숫자의 완전 일치를 뜻하지 않습니다. 기준 키워드는 OCR 실행 전에 작성했으며 결과에 맞춰 축소하지 않았습니다.

## 재현 (backend 기준)

```bash
uv run python scripts/build_seed_pdfs.py
# 기존 모델 캐시가 있는 경우
export PADDLE_PDX_CACHE_HOME="$PWD/data/paddlex"
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
uv run python scripts/run_seed_pipeline.py
# 위 명령이 출력한 실제 성공 run 경로를 전달
uv run python scripts/record_seed_ocr.py data/seed-runs/<run-id>
uv run pytest -q
RUN_REAL_SEED_OCR=1 uv run pytest -q tests/seed/test_seed_pipeline.py
```

모델 캐시가 없으면 첫 OCR 실행 시 다운로드가 필요합니다. 버전은 report.json에 기록됩니다. PDF 생성에는 기존 PyMuPDF와 내장 한글 글꼴을 사용합니다.

실행마다 새 `backend/data/seed-runs/<run-id>/`에 migration을 적용한 후 기존 업로드 API를 호출합니다. TestClient가 BackgroundTasks 완료를 기다리므로 실제 OCR/구조화 결과를 검사합니다. `--run-dir`에는 존재하지 않는 새 경로만 지정할 수 있습니다. 기존 `data/app.db`는 변경하지 않습니다. 새 DB를 앱에서 열려면 report.json의 database_url과 동일 실행 폴더의 uploads/pages/ocr 경로를 환경변수에 설정하세요.

기본 pytest에서는 실제 모델이 필요한 테스트 1개만 skip합니다. 나머지 Seed integration test는 실제 OCR 녹화 결과를 adapter 위치에서 재생하고 PDF 렌더링·parser·SQLite 경로를 실행합니다. `RUN_REAL_SEED_OCR=1`이면 실제 PaddleOCR로 5개 PDF를 다시 처리합니다. 어느 경로에서도 metadata를 DB에 직접 INSERT하지 않습니다.

README 최종 정리와 LLM을 포함한 전체 End-to-End 검증은 Phase 8B에 남겨 둡니다.
