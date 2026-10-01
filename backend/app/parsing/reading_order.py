from app.ocr.paddle_ocr import OcrLine


def page_text(lines: list[OcrLine]) -> str:
    """Join horizontally split OCR boxes on the same row for simple single-column forms.

    Native recognition boxes/text remain untouched in raw JSON. This is deliberately
    not a table or multi-column layout parser.
    """
    rows: list[list[tuple[float, float, float, str]]] = []
    boxes = []
    for line in lines:
        if not line.text.strip():
            continue
        xs, ys = zip(*line.bbox)
        boxes.append((min(xs), (min(ys) + max(ys)) / 2, max(ys) - min(ys), line.text))
    for box in sorted(boxes, key=lambda box: (box[1], box[0])):
        if rows:
            row = rows[-1]
            center = sum(item[1] for item in row) / len(row)
            height = min(item[2] for item in row)
            if abs(box[1] - center) <= .5 * max(1, min(height, box[2])):
                row.append(box)
                continue
        rows.append([box])
    return '\n'.join(' '.join(box[3] for box in sorted(row)) for row in rows)
