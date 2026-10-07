from typing import Annotated, Literal
from pydantic import Field
from ..models import StrictModel, Identifier


class ReadArgs(StrictModel):
    assignment_id: Identifier
    submission_id: Identifier
    submission_version: Annotated[int, Field(ge=1)]


class DraftArgs(ReadArgs):
    requirement_ids: Annotated[list[Identifier], Field(min_length=1, max_length=10)]


class StartRequest(ReadArgs):
    message: Annotated[str, Field(min_length=1, max_length=1000)]
    intent: Literal['read', 'draft']
    mode: Literal['fixture', 'live'] = 'fixture'


class Decision(StrictModel):
    accepted: bool


class Summary(StrictModel):
    submission_id: str
    submission_version: int
    needs_revision: list[str]
    needs_confirmation: list[str]
    draft_id: str | None
    status: Literal['reviewed', 'draft_created']


class FlowError(Exception):
    def __init__(self, code, layer='validation', retryable=False):
        super().__init__(code)
        self.code, self.layer, self.retryable = code, layer, retryable

    def body(self):
        return {'code': self.code, 'layer': self.layer, 'retryable': self.retryable}


TOOLS = [
    {'type':'function','name':'get_submission_review','strict':True,
     'description':'唯讀查詢所選作業版本的既有缺漏報告與證據；必須先執行，不建立草稿。',
     'parameters':ReadArgs.model_json_schema()},
    {'type':'function','name':'create_revision_draft','strict':True,
     'description':'提案建立本機補件清單草稿。先取得匹配報告，包含所有待補件及待確認項目。Host 另向使用者確認後才寫入。',
     'parameters':DraftArgs.model_json_schema()},
]
IDENTITY = {'assignment_id':'HW-DEMO-01','submission_id':'SUB-DEMO-01','submission_version':1}


def identity(value):
    return {key:value[key] for key in IDENTITY}
