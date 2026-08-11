from pydantic import BaseModel


class BriefSection(BaseModel):
    title: str
    word_target: int | None = None
    body: str


class DesignBrief(BaseModel):
    concept_id: str
    format_hint: str | None = None
    status: str | None = None
    target_audiences: list[str] = []
    headline: str
    intro: str
    sections: list[BriefSection]
    closing_title: str | None = None
    closing_body: str | None = None
    source_path: str
