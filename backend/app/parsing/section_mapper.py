import re
from dataclasses import dataclass
from typing import Protocol

from app.parsing.section_aliases import SECTION_ALIASES


@dataclass
class ParsedSection:
    section_type: str
    section_title: str
    content: str
    sequence: int
    source_page: int


class SectionParser(Protocol):
    def parse(self, pages: list[tuple[int, str]]) -> list[ParsedSection]: ...


class SectionMapper:
    def __init__(self):
        self.headings = {
            re.sub(r'\s+', '', alias): (kind, alias)
            for kind, aliases in SECTION_ALIASES.items() for alias in aliases
        }

    def heading(self, line: str) -> tuple[str, str, str] | None:
        clean = re.sub(r'^\s*(?:#{1,6}\s*|\d+\s*[.)]\s*|[■□▶●]\s*)', '', line).strip()
        title, separator, body = clean.replace('：', ':').partition(':')
        key = re.sub(r'\s+', '', title.strip().strip('[]').strip())
        if key in self.headings:
            kind, canonical = self.headings[key]
            return kind, canonical, body.strip() if separator else ''
        return None

    def parse(self, pages: list[tuple[int, str]]) -> list[ParsedSection]:
        sections: list[ParsedSection] = []
        current: ParsedSection | None = None
        for page_number, text in sorted(pages):
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                heading = self.heading(line)
                if heading and current and current.section_type == heading[0] and (':' in line or '：' in line):
                    heading = None  # A labeled field within its own section is content.
                if heading:
                    kind, title, inline_content = heading
                    current = ParsedSection(kind, title, inline_content, len(sections) + 1, page_number)
                    sections.append(current)
                else:
                    if current is None:
                        current = ParsedSection('other', '미분류', '', len(sections) + 1, page_number)
                        sections.append(current)
                    current.content = '\n'.join(filter(None, (current.content, line)))
        return sections
