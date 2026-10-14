"""Week 5 graph persistence and resume safety, without live provider requests."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import sqlite3

from fastapi.testclient import TestClient
import pytest

from assignment_checker.api import create_app
from assignment_checker.week4.contracts import FlowError, IDENTITY, StartRequest
from assignment_checker.week4.provider import FixtureProvider
from assignment_checker.week4.store import Store
from assignment_checker.week4.tools import get_review
from assignment_checker.week4.workflow import Workflow
from assignment_checker.week5.workflow import GraphWorkflow


def request(intent='draft', **changes):
    return StartRequest(**{
        **IDENTITY,
        'message': '幫我查缺漏並準備補件草稿',
        'intent': intent,
        'mode': 'fixture',
        **changes,
    })


async def local_reader(arguments):
    report, trace = get_review(arguments)
    return {'report': report, 'rag_trace': trace}, [
        {'transport': 'unit-test direct read, not MCP'},
    ]


def host(tmp_path, provider_fault=None, **changes):
    settings = {
        'checkpoint_path': tmp_path / 'checkpoints.sqlite3',
        'provider': FixtureProvider(provider_fault),
        'reader': local_reader,
        **changes,
    }
    return GraphWorkflow(Store(tmp_path / 'state.sqlite3'), **settings)


async def failed_decision(service, run_id):
    """A failure may be raised at the host boundary or persisted on the run."""
    try:
        result = await service.decide(run_id, True)
    except FlowError as error:
        return error.body()
    assert 'error' in result, result
    return result['error']


def test_actual_graph_checkpoint_survives_new_host_without_writing(tmp_path):
    service = host(tmp_path)
    pending = asyncio.run(service.start(request()))
    assert pending['state'] == 'awaiting_confirmation'
    assert service.store.draft_count() == 0
    orchestration = pending['orchestration']
    assert orchestration['engine'] == 'langgraph'
    assert orchestration['thread_id'] == pending['run_id']
    assert orchestration['checkpoint_id']
    assert orchestration['next']
    assert orchestration['interrupts']

    # This is a real SQLite checkpointer, rather than JSON describing a pause.
    with sqlite3.connect(tmp_path / 'checkpoints.sqlite3') as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'checkpoints' in tables
        assert db.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0] > 0

    restarted = host(tmp_path)
    recovered = asyncio.run(restarted.inspect(pending['run_id']))
    assert recovered['proposal'] == pending['proposal']
    assert recovered['orchestration']['thread_id'] == orchestration['thread_id']
    assert recovered['orchestration']['checkpoint_id'] == orchestration['checkpoint_id']
    assert recovered['state'] == 'awaiting_confirmation'
    assert restarted.store.draft_count() == 0


def test_restart_resume_accepts_once_and_replays_same_receipt(tmp_path):
    pending = asyncio.run(host(tmp_path).start(request()))
    service = host(tmp_path)
    done = asyncio.run(service.decide(pending['run_id'], True))
    assert done['state'] == 'completed'
    assert done['summary']['draft_id'] == done['receipt']['draft_id']
    assert done['receipt']['request_id'] == pending['run_id']
    assert done['orchestration']['thread_id'] == pending['run_id']
    assert not done['orchestration']['next']
    assert not done['orchestration']['interrupts']
    assert service.store.draft_count() == 1

    replay = asyncio.run(host(tmp_path).decide(pending['run_id'], True))
    assert replay['replayed']
    assert replay['receipt'] == done['receipt']
    assert replay['model_rounds'] == done['model_rounds'] == 3
    assert service.store.draft_count() == 1


def test_declined_graph_remains_terminal_after_accepted_replay(tmp_path):
    service = host(tmp_path)
    pending = asyncio.run(service.start(request()))
    declined = asyncio.run(service.decide(pending['run_id'], False))
    replay = asyncio.run(host(tmp_path).decide(pending['run_id'], True))
    assert declined['state'] == replay['state'] == 'declined'
    assert not declined['orchestration']['next']
    assert 'receipt' not in replay
    assert service.store.draft_count() == 0


def test_read_only_does_not_schedule_write_confirmation(tmp_path):
    service = host(tmp_path)
    result = asyncio.run(service.start(request('read')))
    assert result['state'] == 'completed'
    assert result['summary']['draft_id'] is None
    assert result['model_rounds'] == 2
    assert result['engine'] == 'langgraph'
    assert not (tmp_path / 'checkpoints.sqlite3').exists()
    assert service.store.draft_count() == 0


@pytest.mark.parametrize('fault, expected', [
    ('missing_field', 'INVALID_TOOL_ARGUMENTS'),
    ('model_confirmation', 'INVALID_TOOL_ARGUMENTS'),
    ('wrong_items', 'REPORT_MISMATCH'),
    ('provider429', 'PROVIDER_429'),
])
def test_failed_proposals_never_enter_approval_graph(tmp_path, fault, expected):
    service = host(tmp_path, fault)
    result = asyncio.run(service.start(request()))
    assert result['state'] == 'stopped'
    assert result['error']['code'] == expected
    assert result['engine'] == 'langgraph'
    assert not (tmp_path / 'checkpoints.sqlite3').exists()
    assert service.store.draft_count() == 0
    if fault == 'provider429':
        assert len([event for event in result['audit'] if event['event'] == 'model_attempt']) == 2


def test_expiry_is_rechecked_after_checkpoint_restart(tmp_path, monkeypatch):
    pending = asyncio.run(host(tmp_path).start(request()))

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = datetime.fromisoformat(pending['proposal_created_at']) + timedelta(seconds=601)
            return instant.astimezone(tz or timezone.utc)

    monkeypatch.setattr('assignment_checker.week4.workflow.datetime', Later)
    service = host(tmp_path)
    result = asyncio.run(service.decide(pending['run_id'], True))
    assert result['state'] == 'stopped'
    assert result['error']['code'] == 'PROPOSAL_EXPIRED'
    assert service.store.draft_count() == 0


def test_changed_source_report_prevents_checkpointed_write(tmp_path, monkeypatch):
    pending = asyncio.run(host(tmp_path).start(request()))
    changed = deepcopy(get_review(IDENTITY))
    changed[0]['report_hash'] = 'changed-after-confirmation-was-requested'
    monkeypatch.setattr('assignment_checker.week4.workflow.get_review', lambda _: changed)
    service = host(tmp_path)
    result = asyncio.run(service.decide(pending['run_id'], True))
    assert result['state'] == 'stopped'
    assert result['error']['code'] == 'STALE_REPORT'
    assert service.store.draft_count() == 0


def test_mutated_pending_proposal_cannot_reuse_previous_approval_checkpoint(tmp_path):
    service = host(tmp_path)
    pending = asyncio.run(service.start(request()))
    mutated = service.store.get(pending['run_id'])
    mutated['proposal']['requirement_ids'] = ['target_user']
    service.store.save(mutated)
    error = asyncio.run(failed_decision(host(tmp_path), pending['run_id']))
    assert error['code'] == 'PROPOSAL_CHANGED'
    assert service.store.draft_count() == 0


@pytest.mark.parametrize('damage, expected', [
    ('missing', 'CHECKPOINT_MISSING'),
    ('corrupt', 'CHECKPOINT_INVALID'),
])
def test_unusable_checkpoint_fails_closed(tmp_path, damage, expected):
    service = host(tmp_path)
    pending = asyncio.run(service.start(request()))
    checkpoint = tmp_path / 'checkpoints.sqlite3'
    if damage == 'missing':
        checkpoint.unlink()
    else:
        checkpoint.write_bytes(b'This is not a SQLite checkpoint database.')
    error = asyncio.run(failed_decision(host(tmp_path), pending['run_id']))
    assert error['code'] == expected
    assert service.store.draft_count() == 0
    assert 'receipt' not in service.store.get(pending['run_id'])


@pytest.mark.parametrize('provider_fault, host_fault, expected', [
    ('summary_timeout', None, 'PROVIDER_TIMEOUT_OR_CONNECTION'),
    (None, 'after_write', 'INJECTED_WRITE_RESPONSE_LOST'),
])
def test_failure_after_write_keeps_receipt_and_replay_does_not_write_again(
    tmp_path, provider_fault, host_fault, expected,
):
    service = host(tmp_path, provider_fault, fault=host_fault)
    pending = asyncio.run(service.start(request()))
    result = asyncio.run(service.decide(pending['run_id'], True))
    assert result['state'] == 'written'
    assert result['error']['code'] == expected
    assert result['summary'] is None
    assert service.store.draft_count() == 1
    replay = asyncio.run(host(tmp_path).decide(pending['run_id'], True))
    assert replay['replayed']
    assert replay['receipt'] == result['receipt']
    assert replay['model_rounds'] == result['model_rounds']
    assert service.store.draft_count() == 1


def test_simultaneous_pending_resume_is_locked_before_write(tmp_path, monkeypatch):
    original_decide = Workflow.decide

    async def scenario():
        service = host(tmp_path)
        other_host = host(tmp_path)
        pending = await service.start(request())
        entered, release = asyncio.Event(), asyncio.Event()

        async def paused_decide(self, run_id, accepted):
            entered.set()
            await release.wait()
            return await original_decide(self, run_id, accepted)

        monkeypatch.setattr(Workflow, 'decide', paused_decide)
        first = asyncio.create_task(service.decide(pending['run_id'], True))
        try:
            await asyncio.wait_for(entered.wait(), timeout=3)
            assert service.store.draft_count() == 0
            error = await failed_decision(other_host, pending['run_id'])
            assert error['code'] == 'RUN_BUSY'
        finally:
            release.set()
            result = await first
        assert result['state'] == 'completed'
        assert service.store.draft_count() == 1

    asyncio.run(scenario())


def api_client(tmp_path):
    store = Store(tmp_path / 'state.sqlite3')
    baseline = Workflow(store, FixtureProvider(), local_reader)
    candidate = GraphWorkflow(
        store, checkpoint_path=tmp_path / 'checkpoints.sqlite3',
        provider=FixtureProvider(), reader=local_reader,
    )
    return TestClient(create_app(workflow=baseline, graph_workflow=candidate)), store


@pytest.mark.parametrize('page', ['/week4', '/week5'])
def test_both_ui_entry_points_expose_same_engine_selector(tmp_path, page):
    client, _ = api_client(tmp_path)
    with client:
        response = client.get(page)
    assert response.status_code == 200
    assert 'id="engine"' in response.text
    assert 'value="baseline"' in response.text
    assert 'value="langgraph"' in response.text


def test_api_candidate_start_and_get_expose_real_pending_checkpoint(tmp_path):
    client, store = api_client(tmp_path)
    with client:
        response = client.post('/assistant/week4/runs?engine=langgraph', json=request().model_dump())
        assert response.status_code == 200
        pending = response.json()
        assert pending['state'] == 'awaiting_confirmation'
        assert pending['orchestration']['interrupts']
        assert pending['orchestration']['checkpoint_id']
        assert store.draft_count() == 0
        recovered = client.get('/assistant/week4/runs/' + pending['run_id']).json()
        assert recovered['orchestration'] == pending['orchestration']
        assert recovered['engine'] == store.get(pending['run_id'])['engine'] == 'langgraph'
        done = client.post(
            '/assistant/week4/runs/' + pending['run_id'] + '/decision', json={'accepted': True},
        ).json()
        assert done['state'] == 'completed'
        assert not done['orchestration']['next']
        assert store.draft_count() == 1


def test_api_cannot_bypass_persisted_engine_using_decision_query(tmp_path):
    client, store = api_client(tmp_path)
    with client:
        pending = client.post('/assistant/week4/runs?engine=langgraph', json=request().model_dump()).json()
        (tmp_path / 'checkpoints.sqlite3').unlink()
        # Routing must use the saved run, even when a client requests the other engine.
        response = client.post(
            '/assistant/week4/runs/' + pending['run_id'] + '/decision?engine=baseline',
            json={'accepted': True},
        )
        assert response.status_code == 200
        assert response.json()['error']['code'] == 'CHECKPOINT_MISSING'
        assert response.json()['engine'] == 'langgraph'
        assert store.draft_count() == 0


def test_api_baseline_remains_default_and_rejects_invalid_inputs(tmp_path):
    client, store = api_client(tmp_path)
    with client:
        assert client.post(
            '/assistant/week4/runs?engine=unknown', json=request().model_dump(),
        ).status_code == 422
        pending = client.post('/assistant/week4/runs', json=request().model_dump()).json()
        assert pending['state'] == 'awaiting_confirmation'
        assert pending.get('engine', 'baseline') == 'baseline'
        assert not (tmp_path / 'checkpoints.sqlite3').exists()
        decision_url = '/assistant/week4/runs/' + pending['run_id'] + '/decision'
        for extra in [{'confirmed': True}, {'request_id': 'invented'}, {'engine': 'langgraph'}]:
            assert client.post(decision_url, json={'accepted': True, **extra}).status_code == 422
        assert store.draft_count() == 0
        result = client.post(decision_url, json={'accepted': True}).json()
        assert result['state'] == 'completed'
        assert result.get('engine', 'baseline') == 'baseline'
        assert not (tmp_path / 'checkpoints.sqlite3').exists()
        assert store.draft_count() == 1
