"""Create image-only synthetic PDFs; no DB access. Run from backend with uv run python scripts/build_seed_pdfs.py."""
from pathlib import Path
import json
import pymupdf

ROOT = Path(__file__).resolve().parents[2] / 'sample-data'


def build(source: dict, destination: Path):
    # Built-in Korean font avoids a machine-specific font dependency.
    with pymupdf.open() as vector, pymupdf.open() as scanned:
        for index in range(2):
            page = vector.new_page(width=595, height=842)
            def text(x, y, value, size=12):
                if pymupdf.get_text_length(value, fontname='korea', fontsize=size) > 500:
                    raise ValueError(f'Line too long: {value}')
                page.insert_text((x,y), value, fontname='korea', fontsize=size, color=(0.12,)*3)
            text(46, 50, source['title'], 20)
            text(46, 78, f"문서번호: {source['id']} / 업무 영역: {source['domain']}", 10)
            text(46, 98, '가상 실습 조직 SEED / 인계일: 2026-10-02 / 합성 데이터', 10)
            page.draw_line((46,112),(549,112),color=(0.4,)*3)
            y=150
            for number, section in enumerate(source['sections'][index*4:index*4+4],start=index*4+1):
                text(46,y,f"{number}. {section['title']}",15)
                for j,line in enumerate(section['lines']):
                    text(54,y+27+j*23,line)
                y += 144
            text(46,752,'확인란: 인계 역할 / 인수 역할 / 검토 역할 (모두 가상)',10)
            text(46,776,'실제 기업, 직원, 고객 정보 및 비밀정보를 포함하지 않습니다.',10)
            text(490,808,f'{index+1} / 2',10)
            pix=page.get_pixmap(dpi=200,colorspace=pymupdf.csGRAY,alpha=False)
            target=scanned.new_page(width=595,height=842)
            target.insert_image(target.rect,stream=pix.tobytes('jpeg',jpg_quality=92))
        scanned.set_metadata({'title':source['title'],'subject':'Synthetic OCR seed, image-only','author':'Synthetic Seed Generator'})
        scanned.save(destination,garbage=4,deflate=True)
    with pymupdf.open(destination) as pdf:
        assert len(pdf)==2 and all(not p.get_text().strip() and p.get_images() for p in pdf)


def main():
    output=ROOT/'scanned-pdfs'
    output.mkdir(exist_ok=True,parents=True)
    for path in sorted((ROOT/'sources').glob('seed-*.json')):
        doc=json.loads(path.read_text())
        build(doc,output/f"{doc['id']}.pdf")
        print(output/f"{doc['id']}.pdf")

if __name__=='__main__':
    main()
