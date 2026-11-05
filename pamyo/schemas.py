from pydantic import BaseModel, Field


class Word(BaseModel):
    quote: str = Field(description="Copied exactly from one source, character for character")
    source: str = Field(description='"code", or the id of the commit the quote comes from, like 4f2a9c1')


class Answer(BaseModel):
    """What the model hands back. Its quotes are claims until verify.check has found them in the record."""

    silent: bool = Field(description="True when no source says why")
    words: list[Word] = Field(default_factory=list, description="At most 4 quotes, the most direct answer first")
