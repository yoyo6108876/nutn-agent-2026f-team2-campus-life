"""Versioned request and response contracts; no provider credentials here."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(min_length=1, max_length=12000, pattern=r"\S")]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"^\S+$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Section(StrictModel):
    id: Identifier
    text: Text


class Document(StrictModel):
    sections: Annotated[list[Section], Field(min_length=1, max_length=30)]

    @model_validator(mode="after")
    def unique_sections(self):
        ids = [section.id for section in self.sections]
        if len(ids) != len(set(ids)):
            raise ValueError("section IDs must be unique within each document")
        return self


class Requirement(StrictModel):
    id: Identifier
    description: Text
    teacher_section_id: Identifier


class CheckRequest(StrictModel):
    assignment_id: Identifier
    submission_id: Identifier
    submission_version: Annotated[int, Field(ge=1)]
    teacher_example: Document
    student_submission: Document
    confirmed_requirements: Annotated[list[Requirement], Field(min_length=1, max_length=10)]

    @model_validator(mode="after")
    def validate_references_and_size(self):
        ids = [requirement.id for requirement in self.confirmed_requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("requirement IDs must be unique")
        teacher_ids = {section.id for section in self.teacher_example.sections}
        if any(requirement.teacher_section_id not in teacher_ids
               for requirement in self.confirmed_requirements):
            raise ValueError("requirement references an unknown teacher section")
        size = sum(len(section.text) for document in [self.teacher_example, self.student_submission]
                   for section in document.sections)
        size += sum(len(item.description) for item in self.confirmed_requirements)
        if size > 20000:
            raise ValueError("combined document and requirement text exceeds 20000 characters")
        return self


class Evidence(StrictModel):
    section_id: Identifier
    quote: Text


class Check(StrictModel):
    requirement_id: Identifier
    status: Literal["met", "partial", "missing", "uncertain"]
    teacher_evidence: Evidence
    student_evidence: list[Evidence]
    reason: Text
    suggestion: Text


class ModelReport(StrictModel):
    assignment_id: Identifier
    submission_id: Identifier
    submission_version: int
    checks: list[Check]


class Notice(StrictModel):
    needs_revision: list[str]
    needs_confirmation: list[str]


class CheckResponse(ModelReport):
    student_notice: Notice
    teacher_notice: Notice
