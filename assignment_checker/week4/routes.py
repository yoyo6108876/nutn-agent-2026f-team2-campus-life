from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from .contracts import StartRequest, Decision, FlowError
from .store import Store
from .workflow import Workflow

ROOT=Path(__file__).resolve().parents[2]


def make_router(workflow=None):
    router=APIRouter()
    active=workflow

    def host():
        nonlocal active
        if active is None:active=Workflow(Store(ROOT/'tmp/week4/state.sqlite3'))
        return active

    def local_request(request):
        origin=request.headers.get('origin')
        if origin and origin!=str(request.base_url).rstrip('/'):
            raise HTTPException(403,'Cross-origin action denied')

    @router.get('/week4',response_class=HTMLResponse)
    def page():
        return Path(__file__).with_name('ui.html').read_text(encoding='utf-8')

    @router.post('/assistant/week4/runs')
    async def start(payload:StartRequest,request:Request):
        local_request(request)
        return await host().start(payload)

    @router.get('/assistant/week4/runs/{run_id}')
    def get(run_id:str):
        try:return host().store.get(run_id)
        except FlowError:raise HTTPException(404,'RUN_NOT_FOUND') from None

    @router.post('/assistant/week4/runs/{run_id}/decision')
    async def decide(run_id:str,payload:Decision,request:Request):
        local_request(request)
        try:return await host().decide(run_id,payload.accepted)
        except FlowError:raise HTTPException(404,'RUN_NOT_FOUND') from None

    return router
