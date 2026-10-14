from pathlib import Path
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from .contracts import StartRequest, Decision, FlowError
from .store import Store
from .workflow import Workflow

ROOT=Path(__file__).resolve().parents[2]


def make_router(workflow=None, graph_workflow=None):
    router=APIRouter()
    active=workflow
    candidate=graph_workflow

    def host():
        nonlocal active
        if active is None:active=Workflow(Store(ROOT/'tmp/week4/state.sqlite3'))
        return active

    def graph_host():
        nonlocal candidate
        if candidate is None:
            from ..week5.workflow import GraphWorkflow
            candidate=GraphWorkflow(host().store)
        return candidate

    def run_host(run_id):
        run=host().store.get(run_id)
        return graph_host() if run.get('engine')=='langgraph' else host()

    def flow_http(error):
        status=404 if error.code=='RUN_NOT_FOUND' else 409 if error.code=='RUN_BUSY' else 503
        return HTTPException(status,error.code)

    def local_request(request):
        origin=request.headers.get('origin')
        if origin and origin!=str(request.base_url).rstrip('/'):
            raise HTTPException(403,'Cross-origin action denied')

    @router.get('/week4',response_class=HTMLResponse)
    @router.get('/week5',response_class=HTMLResponse)
    def page():
        return Path(__file__).with_name('ui.html').read_text(encoding='utf-8')

    @router.post('/assistant/week4/runs')
    async def start(payload:StartRequest,request:Request,engine:Literal['baseline','langgraph']='baseline'):
        local_request(request)
        return await (graph_host() if engine=='langgraph' else host()).start(payload)

    @router.get('/assistant/week4/runs/{run_id}')
    async def get(run_id:str):
        try:
            selected=run_host(run_id)
            return await selected.inspect(run_id) if hasattr(selected,'inspect') else selected.store.get(run_id)
        except FlowError as error:raise flow_http(error) from None

    @router.post('/assistant/week4/runs/{run_id}/decision')
    async def decide(run_id:str,payload:Decision,request:Request):
        local_request(request)
        try:return await run_host(run_id).decide(run_id,payload.accepted)
        except FlowError as error:raise flow_http(error) from None

    return router
