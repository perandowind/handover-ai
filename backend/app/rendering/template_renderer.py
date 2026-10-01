import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.schemas.generation import GeneratedDocument


class TemplateRenderer:
    def __init__(self):
        self.environment = Environment(
            loader=FileSystemLoader(Path(__file__).parent / 'templates'),
            autoescape=select_autoescape(['html']), undefined=StrictUndefined,
        )
        # Story can break at zero-width spaces even inside long URLs/identifiers.
        # This affects only layout; the original document is never modified.
        self.environment.filters['soft_wrap'] = lambda value, width=32: re.sub(
            rf'(\S{{{width}}})(?=\S)', lambda match: match[1] + '\u200b', value,
        )

    def render(self, document: GeneratedDocument) -> str:
        return self.environment.get_template('handover.html').render(document=document)
