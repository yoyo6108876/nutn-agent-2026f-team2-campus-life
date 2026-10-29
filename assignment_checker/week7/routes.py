"""Local synthetic identities and scoped sessions. Not a production login system."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool
from pydantic import Field, model_validator
from pydantic import ValidationError

from ..models import StrictModel, CheckRequest, Document, Section, Requirement
from ..provider import OpenAIProvider
from ..service import ground_report
from ..week4.contracts import StartRequest, Decision, FlowError, IDENTITY
from ..week4.store import Store
from ..week4.tools import get_review
from .memory import SessionMemory
from .workflow import SessionWorkflow
from ..pdf_review import PDFPair, PDFPrechecks, MAX_BODY_BYTES
from ..service import CheckFailure
from ..week6.workflow import revise_until_valid

ROOT = Path(__file__).resolve().parents[2]
COOKIE = 'assignment_demo_session'


class Login(StrictModel):
    profile: Literal['student-a', 'student-b']


class Reset(StrictModel):
    session_id: str
    confirmed: Literal[True]


class ConfirmRubric(StrictModel):
    confirmed: bool


class ReviewInput(StrictModel):
    teacher_text: Annotated[str, Field(min_length=1, max_length=12000)]
    student_text: Annotated[str, Field(min_length=1, max_length=12000)]
    requirements: Annotated[list[str], Field(min_length=1, max_length=10)]
    requirements_confirmed: bool

    @model_validator(mode='after')
    def valid_document(self):
        if not self.requirements_confirmed:
            raise ValueError('Confirmed requirements are required')
        self.request()
        return self

    def request(self):
        return CheckRequest(
            assignment_id='HW-TEXT-01', submission_id='SUB-TEXT-01', submission_version=1,
            teacher_example=Document(sections=[Section(id='T1', text=self.teacher_text)]),
            student_submission=Document(sections=[Section(id='S1', text=self.student_text)]),
            confirmed_requirements=[Requirement(id=f'R{i+1}', description=text, teacher_section_id='T1')
                                    for i, text in enumerate(self.requirements)],
        )


class SessionService:
    def __init__(self, root=None, provider=None, review_provider=None, reader=None, pdf_provider=None):
        directory = Path(root or ROOT/'tmp/week7')
        self.store = Store(directory/'business.sqlite3')
        self.memory = SessionMemory(directory/'sessions.sqlite3')
        self.provider, self.review_provider, self.reader = provider, review_provider, reader
        self.pdf_prechecks = PDFPrechecks(self.memory, pdf_provider,
                                          workflows={'evaluator_optimizer': revise_until_valid})
        with self.memory.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS browser_tokens
                (digest TEXT PRIMARY KEY, owner_id TEXT NOT NULL, session_id TEXT NOT NULL, created_at REAL NOT NULL)''')

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def login(self, owner_id, old_token=None):
        session = self.memory.new_session(owner_id)
        opaque = secrets.token_urlsafe(32)
        with self.memory.db() as db:
            if old_token:
                db.execute('DELETE FROM browser_tokens WHERE digest=?', (self.digest(old_token),))
            db.execute('INSERT INTO browser_tokens VALUES (?,?,?,?)',
                       (self.digest(opaque), owner_id, session['session_id'], datetime.now(timezone.utc).timestamp()))
        return opaque, session

    def identify(self, opaque):
        if not opaque:
            raise HTTPException(401, 'DEMO_LOGIN_REQUIRED')
        with self.memory.db() as db:
            row = db.execute('SELECT * FROM browser_tokens WHERE digest=?', (self.digest(opaque),)).fetchone()
        if row is None or datetime.now(timezone.utc).timestamp()-row['created_at'] > 86400:
            raise HTTPException(401, 'DEMO_SESSION_EXPIRED')
        self.memory.require_active(row['session_id'], row['owner_id'])
        return dict(row)

    def host(self, principal):
        settings = {'provider': self.provider}
        if self.reader is not None:
            settings['reader'] = self.reader
        return SessionWorkflow(self.store, self.memory, principal['owner_id'], principal['session_id'], **settings)

    def reset(self, principal, expected_session_id):
        # The old ID must belong to this browser's owner and be on its reset chain.
        old = self.memory.get_session(expected_session_id, principal['owner_id'])
        cursor = old
        seen = set()
        while cursor['session_id'] != principal['session_id']:
            if cursor['active'] or not cursor['successor'] or cursor['session_id'] in seen:
                raise FlowError('SESSION_NOT_FOUND', 'memory')
            seen.add(cursor['session_id'])
            cursor = self.memory.get_session(cursor['successor'], principal['owner_id'])
        # A retried reset returns the existing successor without clearing its new memory.
        session = cursor if expected_session_id != principal['session_id'] else self.memory.clear_session(
            principal['session_id'], principal['owner_id'])
        with self.memory.db() as db:
            db.execute('UPDATE browser_tokens SET session_id=? WHERE digest=?',
                       (session['session_id'], principal['digest']))
        return session


def make_router(service=None):
    router = APIRouter()
    active = service

    def host():
        nonlocal active
        if active is None:
            active = SessionService()
        return active

    def principal(request):
        return host().identify(request.cookies.get(COOKIE))

    def local(request):
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'CROSS_ORIGIN_DENIED')

    @router.get('/week7', response_class=HTMLResponse)
    def page():
        return Path(__file__).with_name('ui.html').read_text(encoding='utf-8')

    @router.post('/assistant/week7/login')
    def login(payload: Login, request: Request, response: Response):
        local(request)
        opaque, session = host().login(payload.profile, request.cookies.get(COOKIE))
        response.set_cookie(COOKIE, opaque, httponly=True, samesite='strict', max_age=86400,
                            path='/assistant/week7')
        return {'session': session, 'identity_mode': 'synthetic_demo_selection_not_production_auth'}

    @router.get('/assistant/week7/session')
    def session(request: Request):
        who = principal(request)
        report, _ = get_review(IDENTITY)
        version = report['source']+':'+report['evidence_hash']
        return {'session': host().memory.get_session(who['session_id'], who['owner_id']),
                'context': host().memory.context(who['session_id'], who['owner_id'], version),
                'provider': 'openai', 'gemini_status': 'LIVE_NOT_RUN'}

    @router.post('/assistant/week7/session/reset')
    def reset(payload: Reset, request: Request):
        local(request)
        return {'session': host().reset(principal(request), payload.session_id),
                'message': '舊對話摘要已從模型 context 排除；交易與稽核紀錄仍保留在本機。'}

    @router.post('/assistant/week7/runs')
    async def start(payload: StartRequest, request: Request):
        local(request)
        return await host().host(principal(request)).start(payload)

    @router.get('/assistant/week7/runs/{run_id}')
    def get(run_id: str, request: Request):
        who = principal(request)
        host().memory.authorize_run(run_id, who['session_id'], who['owner_id'])
        return host().store.get(run_id)

    @router.post('/assistant/week7/runs/{run_id}/decision')
    async def decide(run_id: str, payload: Decision, request: Request):
        local(request)
        return await host().host(principal(request)).decide(run_id, payload.accepted)

    @router.post('/assistant/week7/review')
    def review(payload: ReviewInput, request: Request):
        local(request)
        who = principal(request)
        check = payload.request()
        provider = host().review_provider or OpenAIProvider()
        report = ground_report(check, provider.generate(check))
        host().memory.require_active(who['session_id'], who['owner_id'])
        return {'report': report.model_dump(), 'provider_metadata': provider.metadata,
                'provider': 'openai', 'live_status': 'LIVE_PASS',
                'scope': 'semantic_text_review_not_connected_to_demo_draft_snapshot'}

    @router.post('/assistant/week7/pdf/precheck')
    async def pdf_precheck(request: Request):
        local(request)
        who = principal(request)
        chunks = bytearray()
        async for chunk in request.stream():
            if len(chunks)+len(chunk)>MAX_BODY_BYTES:
                raise CheckFailure('UPLOAD_TOO_LARGE','pdf_input','兩份 PDF 上傳資料超過上限。',413)
            chunks.extend(chunk)
        try:
            payload = PDFPair.model_validate_json(bytes(chunks))
        except (ValidationError, ValueError):
            raise CheckFailure('INVALID_PDF_UPLOAD','pdf_input','請選擇老師與學生兩份 PDF，每份不超過 6 MiB。',422) from None
        return await run_in_threadpool(host().pdf_prechecks.start, who, payload)

    @router.get('/assistant/week7/pdf/prechecks/{run_id}')
    def get_pdf_precheck(run_id: str, request: Request):
        return host().pdf_prechecks.public(host().pdf_prechecks.get(principal(request),run_id))

    @router.post('/assistant/week7/pdf/prechecks/{run_id}/confirm')
    def confirm_pdf_rubric(run_id: str, payload: ConfirmRubric, request: Request):
        local(request)
        who = principal(request)
        if not payload.confirmed:
            raise CheckFailure('RUBRIC_CONFIRMATION_REQUIRED','grading','請核對老師配分後再顯示預估分數。',409)
        return host().pdf_prechecks.confirm(who,run_id)

    return router
