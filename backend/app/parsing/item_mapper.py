import re

from app.models import DocumentSection, HandoverItem


def map_handover_items(section: DocumentSection) -> list[HandoverItem]:
    """One grounded item per section; explicit 업무명 fields can split task records.

    Category is the known section type; do not invent a business domain or importance.
    Optional attributes are filled only from explicit labels or a matching section.
    """
    if not section.content.strip():
        return []
    blocks = re.split(r'(?m)(?=^업무명\s*[:：])', section.content)
    items = []
    labels = {
        '설명': 'description', '업무 절차': 'procedure', '절차': 'procedure',
        '주의사항': 'precaution', '주기': 'frequency', '관련 시스템': 'related_system',
        '연락처': 'contact_info', '담당자': 'contact_info', '중요도': 'importance',
    }
    for block in blocks:
        if not block.strip():
            continue
        values = {}
        task_name = section.section_title
        for line in block.splitlines():
            match = re.match(r'^([^:：]+)[:：]\s*(.*)$', line)
            if not match:
                continue
            label, value = match[1].strip(), match[2].strip()
            if label == '업무명' and value:
                task_name = value
            elif label in labels and value:
                field = labels[label]
                if field == 'importance':
                    if re.fullmatch('[1-5]', value):
                        values[field] = int(value)
                else:
                    values[field] = '\n'.join(filter(None, (values.get(field), value)))
        values.setdefault('description', block.strip())
        matching_field = {'procedures': 'procedure', 'precautions': 'precaution',
                          'systems': 'related_system', 'contacts': 'contact_info'}.get(section.section_type)
        if matching_field:
            values.setdefault(matching_field, block.strip())
        items.append(HandoverItem(document_id=section.document_id, section_id=section.id,
                                 category=section.section_type, task_name=task_name, **values))
    return items
