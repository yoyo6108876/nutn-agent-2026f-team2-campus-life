import asyncio
from copy import deepcopy
import json

from fastapi.testclient import TestClient
import pytest

from assignment_checker.api import create_app
from assignment_checker.week4.contracts import FlowError, IDENTITY, StartRequest
from assignment_checker.week4.provider import FixtureProvider
from assignment_checker.week4.store import Store
from assignment_checker.week4.tools import get_review
from assignment_checker.week7.memory import SessionMemory
from assignment_checker.week7.routes import SessionService, COOKIE
from assignment_checker.week7.workflow import SessionWorkflow


def request(intent='read'):
    return StartRequest(**IDENTITY, message='檢查缺漏並準備補件清單', intent=intent, mode='fixture')


async def reader(args):
    report, trace = get_review(args)
    return {'report': report, 'rag_trace': trace}, [{'transport':'unit test, not MCP'}]


def setup(tmp_path, owner='student-a', version=None, provider=None):
    memory = SessionMemory(tmp_path/'memory.sqlite3')
    session = memory.new_session(owner)
    workflow = SessionWorkflow(Store(tmp_path/'domain.sqlite3'), memory, owner, session['session_id'],
                               provider=provider or FixtureProvider(), reader=reader, source_version=version)
    return workflow, memory, session


def test_context_includes_only_validated_summary_and_no_raw_prompt(tmp_path):
    w, m, s = setup(tmp_path)
    first = asyncio.run(w.start(request()))
    second = asyncio.run(w.start(request()))
    initial = json.loads(first['history'][0]['content'])['session_context']
    context = json.loads(second['history'][0]['content'])['session_context']
    assert initial['memory'] is None
    assert context['memory']['run_id'] == first['run_id']
    assert 'draft_id' not in context['memory']['summary']
    assert request().message not in json.dumps(context)
    assert second['memory_trace']['included']
    assert second['summary'] == first['summary']


def test_reset_excludes_old_context_and_invalidates_old_run(tmp_path):
    w, m, s = setup(tmp_path)
    first = asyncio.run(w.start(request()))
    new = m.clear_session(s['session_id'], s['owner_id'])
    restarted = SessionWorkflow(w.store,m,new['owner_id'],new['session_id'],reader=reader)
    after = asyncio.run(restarted.start(request()))
    assert not after['memory_trace']['included']
    assert first['run_id'] not in after['history'][0]['content']
    with pytest.raises(FlowError):
        m.authorize_run(first['run_id'],new['session_id'],new['owner_id'])
    assert w.store.get(first['run_id'])['state']=='completed'  # Audit retention is separate.


def test_clear_retry_does_not_clear_successor_memory(tmp_path):
    w,m,s=setup(tmp_path)
    new=m.clear_session(s['session_id'],s['owner_id'])
    successor=SessionWorkflow(w.store,m,new['owner_id'],new['session_id'],reader=reader)
    result=asyncio.run(successor.start(request()))
    retry=m.clear_session(s['session_id'],s['owner_id'])
    assert retry['session_id']==new['session_id']
    assert m.context(new['session_id'],new['owner_id'],result['memory_trace']['source_version'])['memory']


def test_same_user_new_session_does_not_reuse_old_context(tmp_path):
    w,m,s=setup(tmp_path)
    first=asyncio.run(w.start(request()))
    new=m.new_session(s['owner_id'])
    new_host=SessionWorkflow(w.store,m,new['owner_id'],new['session_id'],reader=reader)
    second=asyncio.run(new_host.start(request()))
    assert second['memory_trace']['included'] is False
    assert first['run_id'] not in second['history'][0]['content']
    with pytest.raises(FlowError,match='RUN_NOT_FOUND'):
        m.authorize_run(first['run_id'],new['session_id'],new['owner_id'])


def test_source_version_change_excludes_prior_summary(tmp_path):
    w,m,s=setup(tmp_path,version='teacher-v1')
    first=asyncio.run(w.start(request()))
    newer=SessionWorkflow(w.store,m,s['owner_id'],s['session_id'],reader=reader,source_version='teacher-v2')
    second=asyncio.run(newer.start(request()))
    context=json.loads(second['history'][0]['content'])['session_context']
    assert context['memory'] is None
    assert context['trace']['reason']=='source_version_changed'
    assert second['memory_trace']['source_version']=='teacher-v2'
    assert first['run_id'] not in second['history'][0]['content']


def test_new_user_cannot_read_context_or_approve_another_run(tmp_path):
    w,m,s=setup(tmp_path)
    first=asyncio.run(w.start(request('draft')))
    other=m.new_session('student-b')
    bad=SessionWorkflow(w.store,m,'student-b',other['session_id'],reader=reader)
    with pytest.raises(FlowError,match='RUN_NOT_FOUND'):
        asyncio.run(bad.decide(first['run_id'],True))
    with pytest.raises(FlowError,match='SESSION_NOT_FOUND'):
        m.context(s['session_id'],'student-b','v1')
    assert m.context(other['session_id'],'student-b','v1')['memory'] is None
    assert w.store.draft_count()==0


def test_pending_cleared_session_cannot_write_and_replay_does_not_duplicate(tmp_path):
    w,m,s=setup(tmp_path)
    pending=asyncio.run(w.start(request('draft')))
    m.clear_session(s['session_id'],s['owner_id'])
    with pytest.raises(FlowError,match='SESSION_INACTIVE'):
        asyncio.run(w.decide(pending['run_id'],True))
    assert w.store.draft_count()==0
    w,m,s=setup(tmp_path)
    pending=asyncio.run(w.start(request('draft')))
    done=asyncio.run(w.decide(pending['run_id'],True))
    replay=asyncio.run(w.decide(pending['run_id'],True))
    assert done['receipt']==replay['receipt']
    assert w.store.draft_count()==1


@pytest.mark.parametrize('fault',['provider429','wrong_summary','missing_field','wrong_items'])
def test_failed_run_never_becomes_memory(tmp_path,fault):
    w,m,s=setup(tmp_path,provider=FixtureProvider(fault))
    run=asyncio.run(w.start(request('draft' if fault=='wrong_items' else 'read')))
    assert run['state']=='stopped'
    assert m.context(s['session_id'],s['owner_id'],'v1')['memory'] is None
    assert w.store.draft_count()==0


def test_memory_record_rejects_unbound_or_forged_summary(tmp_path):
    w,m,s=setup(tmp_path)
    run=asyncio.run(w.start(request()))
    forged=deepcopy(run);forged['summary']['needs_revision']=['ignore-instructions']
    with pytest.raises(FlowError,match='INVALID_MEMORY_RECORD'):
        m.remember(s['session_id'],s['owner_id'],'v1',forged)
    forged=deepcopy(run);forged['run_id']='unbound-run'
    with pytest.raises(FlowError,match='RUN_NOT_FOUND'):
        m.remember(s['session_id'],s['owner_id'],'v1',forged)


def test_clear_cannot_race_approved_write(tmp_path):
    w,m,s=setup(tmp_path)
    with m.session_lock(s['session_id']):
        with pytest.raises(FlowError,match='SESSION_BUSY'):
            m.clear_session(s['session_id'],s['owner_id'])


def api(tmp_path):
    service=SessionService(tmp_path,provider=FixtureProvider(),reader=reader)
    return TestClient(create_app(session_service=service)),service


def test_cookie_auth_input_scope_and_legacy_isolation(tmp_path):
    client,service=api(tmp_path)
    assert client.post('/assistant/week7/runs',json=request().model_dump()).status_code==401
    login=client.post('/assistant/week7/login',json={'profile':'student-a'})
    assert 'HttpOnly' in login.headers['set-cookie'] and 'SameSite=strict' in login.headers['set-cookie']
    assert COOKIE not in login.text
    run=client.post('/assistant/week7/runs',json=request('draft').model_dump()).json()
    other=TestClient(client.app)
    other.post('/assistant/week7/login',json={'profile':'student-b'})
    assert other.get('/assistant/week7/runs/'+run['run_id']).status_code==404
    assert other.post('/assistant/week7/runs/'+run['run_id']+'/decision',json={'accepted':True}).status_code==404
    assert client.get('/assistant/week4/runs/'+run['run_id']).status_code==404
    assert service.store.draft_count()==0


def test_reset_http_is_idempotent_and_old_run_inaccessible(tmp_path):
    client,service=api(tmp_path)
    session=client.post('/assistant/week7/login',json={'profile':'student-a'}).json()['session']
    run=client.post('/assistant/week7/runs',json=request().model_dump()).json()
    body={'session_id':session['session_id'],'confirmed':True}
    reset=client.post('/assistant/week7/session/reset',json=body)
    after=client.post('/assistant/week7/runs',json=request().model_dump()).json()
    assert after['memory_trace']['included'] is False
    repeated=client.post('/assistant/week7/session/reset',json=body)
    assert repeated.json()['session']['session_id']==reset.json()['session']['session_id']
    assert client.get('/assistant/week7/session').json()['context']['memory']
    assert client.get('/assistant/week7/runs/'+run['run_id']).status_code==404


def test_invalid_identity_cross_origin_and_confirmation_rejected(tmp_path):
    client,service=api(tmp_path)
    assert client.post('/assistant/week7/login',json={'profile':'admin'}).status_code==422
    assert client.post('/assistant/week7/login',json={'profile':'student-a'},headers={'origin':'https://evil.invalid'}).status_code==403
    client.post('/assistant/week7/login',json={'profile':'student-a'})
    bad={**request().model_dump(),'owner_id':'student-b'}
    assert client.post('/assistant/week7/runs',json=bad).status_code==422
    run=client.post('/assistant/week7/runs',json=request('draft').model_dump()).json()
    assert client.post('/assistant/week7/runs/'+run['run_id']+'/decision',json={'accepted':'true'}).status_code==422
    assert client.post('/assistant/week7/review',json={'teacher_text':'規格','student_text':'作業','requirements':['條件'],'requirements_confirmed':False}).status_code==422
    assert service.store.draft_count()==0


def test_review_limits_validate_before_provider(tmp_path):
    client,_=api(tmp_path)
    client.post('/assistant/week7/login',json={'profile':'student-a'})
    body={'teacher_text':'a'*12000,'student_text':'b'*12000,'requirements':['項目'],'requirements_confirmed':True}
    assert client.post('/assistant/week7/review',json=body).status_code==422
