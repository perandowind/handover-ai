"""Create a synthetic image-only Korean PDF. Run from backend with uv run python scripts/create_sample_pdf.py.
This authoring helper is not part of the application's PDF processing path.
"""
import json
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
PAGES = [
    [
        'DB 운영 인수인계서',
        '1. 업무 개요',
        '운영 데이터베이스의 백업 상태를 매일 확인합니다.',
        '2. 주요 업무',
        '업무명: 일일 DB 백업 확인',
        '설명: 백업 결과와 저장 공간을 확인합니다.',
        '주기: 매일 09:00',
        '중요도: 5',
        '3. 관련 시스템',
        'PostgreSQL 운영 서버와 백업 저장소',
        '4. 업무 절차',
        '백업 로그를 확인합니다.',
        '실패한 작업이 있으면 담당자에게 알립니다.',
    ],
    [
        '5. 주의사항',
        '백업 파일은 확인 없이 삭제하지 않습니다.',
        '6. 장애 대응',
        '백업 실패 시 오류 로그를 확인하고 담당자에게 연락합니다.',
        '7. 담당자 및 연락처',
        '운영 담당자: 홍길동',
        '연락처: ops@example.com',
        '8. 참고자료',
        'DB 백업 운영 매뉴얼 1.0',
    ],
]


def main():
    output = ROOT / 'sample-data/scanned-pdfs/db-handover-scan.pdf'
    output.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as scan:
        for lines in PAGES:
            with pymupdf.open() as source:
                page = source.new_page(width=595, height=842)
                font = Path('/System/Library/Fonts/AppleSDGothicNeo.ttc')
                if font.exists():
                    page.insert_font(fontname='SampleKorean', fontfile=str(font))
                y = 70
                for line in lines:
                    heading = line[:1].isdigit() or line == 'DB 운영 인수인계서'
                    page.insert_text((45, y), line, fontname='SampleKorean' if font.exists() else 'korea', fontsize=17 if heading else 13)
                    y += 48 if heading else 36
                image = page.get_pixmap(dpi=200, colorspace=pymupdf.csRGB, alpha=False)
                scan_page = scan.new_page(width=595, height=842)
                scan_page.insert_image(scan_page.rect, stream=image.tobytes('png'))
        scan.save(output, deflate=True)
    metadata = ROOT / 'sample-data/metadata/db-handover.expected.json'
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(json.dumps({'synthetic': True, 'pages': PAGES,
        'expected_sections': ['other', 'overview', 'responsibilities', 'systems', 'procedures',
                              'precautions', 'troubleshooting', 'contacts', 'references']},
        ensure_ascii=False, indent=2), encoding='utf-8')
    with pymupdf.open(output) as pdf:
        assert len(pdf) == 2
        assert all(not page.get_text().strip() and page.get_images() for page in pdf)
        pdf[0].get_pixmap(dpi=100).save('/tmp/handover-sample-page1.png')
        pdf[1].get_pixmap(dpi=100).save('/tmp/handover-sample-page2.png')
    print(output)


if __name__ == '__main__':
    main()
