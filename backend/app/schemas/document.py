import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.common import ErrorResponse


class OrmSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DocumentSummary(OrmSchema):
    id: int
    title: str
    document_type: str
    department: str | None
    source_filename: str
    ocr_status: str
    parse_status: str
    created_at: datetime
    updated_at: datetime


class DocumentPageRead(OrmSchema):
    id: int
    page_number: int
    raw_text: str
    ocr_json: dict[str, Any]

    @field_validator('ocr_json', mode='before')
    @classmethod
    def decode_json(cls, value):
        return json.loads(value) if isinstance(value, str) else value


class DocumentSectionRead(OrmSchema):
    id: int
    document_id: int
    section_type: str
    section_title: str
    content: str
    sequence: int
    source_page: int | None


class HandoverItemRead(OrmSchema):
    id: int
    section_id: int | None
    category: str
    task_name: str
    description: str
    procedure: str | None
    precaution: str | None
    importance: int | None
    frequency: str | None
    related_system: str | None
    contact_info: str | None


class DocumentDetail(DocumentSummary):
    pages: list[DocumentPageRead]
    sections: list[DocumentSectionRead]
    handover_items: list[HandoverItemRead]
    processing_error: ErrorResponse | None = None


class UploadResponse(BaseModel):
    document_id: int
    status: Literal['processing'] = 'processing'
