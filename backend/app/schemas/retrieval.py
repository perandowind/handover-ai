from pydantic import BaseModel, ConfigDict, Field


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=4000)


class RetrievalResponse(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    sql: str
    rows: list[dict[str, str | int | float | bool | None]]
    row_count: int
    context: str
    context_truncated: bool
