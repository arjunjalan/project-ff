from pydantic import BaseModel


class NewsItem(BaseModel):
    title: str
    summary: str
    link: str
    published: str | None = None


class MaterialityAssessment(BaseModel):
    item: NewsItem
    material: bool
    reason: str
