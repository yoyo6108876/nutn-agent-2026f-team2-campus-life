import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path

from fastapi.testclient import TestClient
import httpx
from openai import AsyncOpenAI
import pytest

from assignment_checker.api import create_app
from assignment_checker.week4.contracts import StartRequest, IDENTITY, FlowError
from assignment_checker.week4.mcp_client import read_over_mcp
from assignment_checker.week4.provider import FixtureProvider, ToolProvider
from assignment_checker.week4.store import Store
from assignment_checker.week4.tools import get_review
from assignment_checker.week4.workflow import Workflow


def request(intent='draft',mode='fixture',**changes):
    return StartRequest(**{**IDENTITY,'message':'幫我查缺漏並準備補件草稿','intent':intent,'mode':mode,**changes})


def host(tmp_path,fault=None,**kwargs):
    return Workflow(Store(tmp_path/'state.sqlite3'),provider=FixtureProvider(fault),**kwargs)


async def local_reader(args):
    report,trace=get_review(args)
    return {'report':report,'rag_trace':trace},[{'transport':'unit-test direct read, not MCP'}]


def test_real_stdio_mcp_lists_only_read_tool_and_returns_grounded_report():
    result,trace=asyncio.run(read_over_mcp(IDENTITY))
    assert [e['method'] for e in trace]==['initialize','tools/list','tools/call']
    listed=trace[1]['result']['tools']
    assert [t['name'] for t in listed]==['get_submission_review']
    assert listed[0]['inputSchema']['additionalProperties'] is False
    assert listed[0]['annotations']['readOnlyHint'] is True
    assert result['report']['needs_revision']==['failure_case']
    assert result['rag_trace']['gate']=='ready'


def test_read_only_never_writes_and_returns_tool_result_to_model(tmp_path):
    service=host(tmp_path,reader=local_reader)
    run=asyncio.run(service.start(request('read')))
    assert run['state']=='completed'
    assert run['model_rounds']==2
    assert service.store.draft_count()==0
    outputs=[r for r in run['history'] if r.get('type')=='function_call_output']
    assert len(outputs)==1
    assert json.loads(outputs[0]['output'])['report_hash']==run['report']['report_hash']
    assert run['summary']['draft_id'] is None


def test_confirmation_is_required_and_persists_across_restart(tmp_path):
    service=host(tmp_path,reader=local_reader)
    run=asyncio.run(service.start(request()))
    assert run['state']=='awaiting_confirmation'
    assert service.store.draft_count()==0
    restarted=host(tmp_path,reader=local_reader)
    done=asyncio.run(restarted.decide(run['run_id'],True))
    assert done['state']=='completed'
    assert done['receipt']['request_id']==run['run_id']
    assert done['receipt']['delivery']=='local_only_not_sent'
    assert done['summary']['draft_id']==done['receipt']['draft_id']
    replay=asyncio.run(restarted.decide(run['run_id'],True))
    assert replay['receipt']['draft_id']==done['receipt']['draft_id']
    assert restarted.store.draft_count()==1


def test_decline_is_terminal_even_if_later_replayed_as_accepted(tmp_path):
    service=host(tmp_path,reader=local_reader)
    run=asyncio.run(service.start(request()))
    refused=asyncio.run(service.decide(run['run_id'],False))
    replay=asyncio.run(service.decide(run['run_id'],True))
    assert refused['state']==replay['state']=='declined'
    assert service.store.draft_count()==0
    assert any(e.get('accepted') is False and e['executed'] is False for e in refused['audit'])


@pytest.mark.parametrize('fault,code', [('missing_field','INVALID_TOOL_ARGUMENTS'),
    ('wrong_version','REQUEST_MISMATCH'),('model_confirmation','INVALID_TOOL_ARGUMENTS'),
    ('wrong_items','REPORT_MISMATCH'),('provider429','PROVIDER_429')])
def test_invalid_model_proposals_never_create_drafts(tmp_path,fault,code):
    service=host(tmp_path,fault,reader=local_reader)
    run=asyncio.run(service.start(request()))
    assert run['state']=='stopped'
    assert run['error']['code']==code
    assert service.store.draft_count()==0
    if fault=='provider429':
        assert len([e for e in run['audit'] if e['event']=='model_attempt'])==2


def test_summary_failure_preserves_write_and_never_repeats_it(tmp_path):
    service=host(tmp_path,'summary_timeout',reader=local_reader)
    run=asyncio.run(service.start(request()))
    result=asyncio.run(service.decide(run['run_id'],True))
    assert result['state']=='written'
    assert result['error']['layer']=='provider'
    assert result['summary'] is None
    assert service.store.draft_count()==1
    replay=asyncio.run(service.decide(run['run_id'],True))
    assert replay['replayed']
    assert service.store.draft_count()==1
    assert len([e for e in result['audit'] if e['event']=='model_attempt' and e['phase']=='summary'])==2


def test_wrong_summary_is_not_published(tmp_path):
    service=host(tmp_path,'wrong_summary',reader=local_reader)
    result=asyncio.run(service.start(request('read')))
    assert result['error']['code']=='SUMMARY_MISMATCH'
    assert result['summary'] is None


def test_write_response_lost_is_reconciled_by_request_id(tmp_path):
    service=Workflow(Store(tmp_path/'state.sqlite3'),FixtureProvider(),local_reader,fault='after_write')
    run=asyncio.run(service.start(request()))
    result=asyncio.run(service.decide(run['run_id'],True))
    assert result['state']=='written'
    assert any(e['event']=='write_result_reconciled' for e in result['audit'])
    assert service.store.draft_count()==1
    assert asyncio.run(service.decide(run['run_id'],True))['replayed']


def test_stale_report_blocks_write(tmp_path,monkeypatch):
    service=host(tmp_path,reader=local_reader)
    run=asyncio.run(service.start(request()))
    original=get_review(IDENTITY)
    changed=deepcopy(original);changed[0]['report_hash']='changed'
    monkeypatch.setattr('assignment_checker.week4.workflow.get_review',lambda _:changed)
    result=asyncio.run(service.decide(run['run_id'],True))
    assert result['error']['code']=='STALE_REPORT'
    assert service.store.draft_count()==0


def test_expired_confirmation_does_not_write(tmp_path):
    service=host(tmp_path,reader=local_reader)
    run=asyncio.run(service.start(request()))
    run['proposal_created_at']='2020-01-01T00:00:00+00:00';service.store.save(run)
    result=asyncio.run(service.decide(run['run_id'],True))
    assert result['error']['code']=='PROPOSAL_EXPIRED'
    assert service.store.draft_count()==0


def test_parallel_replay_writes_once(tmp_path):
    service=host(tmp_path,reader=local_reader)
    run=asyncio.run(service.start(request()))
    def decide(_):return service.store.decide(run['run_id'],True,run['report']['report_hash'])
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(decide,range(4)))
    assert sum(created for _,created in results)==1
    assert len({r['receipt']['draft_id'] for r,_ in results})==1
    assert service.store.draft_count()==1


def test_read_retry_has_finite_budget(tmp_path):
    count=0
    async def broken(args):
        nonlocal count
        count+=1
        raise FlowError('READ_TIMEOUT','mcp',True)
    service=host(tmp_path,reader=broken)
    run=asyncio.run(service.start(request()))
    assert count==2
    assert run['error']['code']=='READ_TIMEOUT'
    assert service.store.draft_count()==0


def test_request_mismatch_is_rejected_before_model(tmp_path):
    service=host(tmp_path,reader=local_reader)
    run=asyncio.run(service.start(request(message='查看 SUB-OTHER-01 的缺漏')))
    assert run['error']['code']=='MESSAGE_TARGET_MISMATCH'
    assert run['model_rounds']==0


def test_api_schema_and_cross_origin_protect_decision(tmp_path):
    service=host(tmp_path,reader=local_reader)
    with TestClient(create_app(workflow=service)) as client:
        r=client.post('/assistant/week4/runs',json=request().model_dump())
        assert r.status_code==200
        run=r.json()
        url='/assistant/week4/runs/'+run['run_id']+'/decision'
        assert client.post(url,json={'accepted':'yes'}).status_code==422
        assert client.post(url,json={'accepted':True,'request_id':'invented'}).status_code==422
        assert client.post(url,json={'accepted':True},headers={'Origin':'https://other.example'}).status_code==403
        assert service.store.draft_count()==0
        assert client.post(url,json={'accepted':True}).json()['state']=='completed'
        assert client.get('/week4').status_code==200


@pytest.mark.parametrize('http_status,code,expected,retry',[
    (401,'invalid_api_key','PROVIDER_AUTH_FAILED',False),
    (429,'rate_limit_exceeded','PROVIDER_429',True),
    (429,'insufficient_quota','PROVIDER_QUOTA',False),
    (503,'server_error','PROVIDER_HTTP_ERROR',True)])
def test_openai_adapter_errors_are_sanitized_without_hidden_retries(monkeypatch,http_status,code,expected,retry):
    seen=[]
    def transport(req):
        seen.append(req)
        return httpx.Response(http_status,json={'error':{'message':'must-not-leak','code':code,'type':code}})
    monkeypatch.setattr('assignment_checker.week4.provider.local_settings',lambda:('fake-test-key','gpt-4.1-mini-2025-04-14'))
    monkeypatch.setattr('assignment_checker.week4.provider.AsyncOpenAI',lambda **kwargs:
        AsyncOpenAI(**kwargs,http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport))))
    with pytest.raises(FlowError) as error:asyncio.run(ToolProvider().next([],'proposal'))
    assert error.value.code==expected and error.value.retryable==retry
    assert 'must-not-leak' not in str(error.value)
    assert len(seen)==1
    body=json.loads(seen[0].content)
    assert body['store'] is False and body['parallel_tool_calls'] is False
    assert 'confirmed' not in body['tools'][1]['parameters']['properties']
