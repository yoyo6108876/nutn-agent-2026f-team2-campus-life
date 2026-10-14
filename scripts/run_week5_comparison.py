"""Compare Week 4 hand-written orchestration with Week 5 LangGraph.

Default runs are authored fixtures with real read-only MCP, except the explicitly
injected missing source. --live opts into two paired OpenAI scenarios. Every action
runs in a new Python process; both SQLite files survive between those actions.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from time import perf_counter

from assignment_checker.week4.contracts import FlowError, IDENTITY, StartRequest
from assignment_checker.week4.mcp_client import read_over_mcp
from assignment_checker.week4.provider import FixtureProvider
from assignment_checker.week4.store import Store
from assignment_checker.week4.tools import get_review
from assignment_checker.week4.workflow import Workflow


ROOT = Path(__file__).resolve().parents[1]
MESSAGE = '請讀取這份作業的缺漏報告，整理補件與待確認項目；若需寫入，先讓我確認草稿。'
ENGINES = ('baseline', 'langgraph')
CASES = [
    {'case': 'read-only', 'group': 'normal-read', 'intent': 'read', 'state': 'completed'},
    {'case': 'restart-confirm-replay', 'group': 'restart-confirm-replay', 'intent': 'draft',
     'decision': True, 'state': 'completed', 'writes': 1},
    {'case': 'decline-replay', 'group': 'decline-and-expiry', 'intent': 'draft',
     'decision': False, 'state': 'declined'},
    {'case': 'expired-confirmation', 'group': 'decline-and-expiry', 'intent': 'draft',
     'decision': True, 'mutation': 'expire', 'state': 'stopped', 'error': 'PROPOSAL_EXPIRED'},
    {'case': 'source-unavailable', 'group': 'source-and-api-errors', 'intent': 'draft',
     'fault': 'source_unavailable', 'state': 'stopped', 'error': 'EVIDENCE_UNAVAILABLE'},
    {'case': 'provider-429', 'group': 'source-and-api-errors', 'intent': 'draft',
     'fault': 'provider429', 'state': 'stopped', 'error': 'PROVIDER_429'},
    {'case': 'invalid-arguments', 'group': 'source-and-api-errors', 'intent': 'draft',
     'fault': 'missing_field', 'state': 'stopped', 'error': 'INVALID_TOOL_ARGUMENTS'},
    {'case': 'summary-failed-after-write', 'group': 'write-recovery', 'intent': 'draft',
     'decision': True, 'fault': 'summary_timeout', 'state': 'written', 'writes': 1,
     'error': 'PROVIDER_TIMEOUT_OR_CONNECTION'},
    {'case': 'write-response-lost', 'group': 'write-recovery', 'intent': 'draft',
     'decision': True, 'fault': 'after_write', 'state': 'written', 'writes': 1,
     'error': 'INJECTED_WRITE_RESPONSE_LOST'},
]


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def provenance():
    packages = {}
    for package in ('openai', 'mcp', 'langgraph', 'langgraph-checkpoint-sqlite', 'aiosqlite'):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = 'NOT_INSTALLED'
    return {
        'tested_commit_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'tracked_files_dirty': bool(subprocess.check_output(
            ['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, text=True).strip()),
        'python_version': sys.version.split()[0], 'installed_versions': packages,
    }


def injected_source_unavailable(arguments):
    raise FlowError('EVIDENCE_UNAVAILABLE', 'readiness')


class ExpiredClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime.now(tz) + timedelta(seconds=601)


async def worker(args):
    """One process performs one action and then exits, closing its checkpoint DB."""
    started = perf_counter()
    store = Store(args.state_dir / 'business.sqlite3')
    provider = None if args.live else FixtureProvider(
        None if args.fault in ('after_write', 'source_unavailable') else args.fault)
    import assignment_checker.week4.workflow as baseline_module
    if args.fault == 'source_unavailable':
        baseline_module.get_review = injected_source_unavailable
    kwargs = {'provider': provider, 'reader': read_over_mcp,
              'fault': 'after_write' if args.fault == 'after_write' else None}
    if args.engine == 'langgraph':
        from assignment_checker.week5.workflow import GraphWorkflow
        service = GraphWorkflow(store, checkpoint_path=args.state_dir / 'checkpoints.sqlite3', **kwargs)
    else:
        service = Workflow(store, **kwargs)
    if args.operation == 'start':
        payload = json.loads(args.request_file.read_text(encoding='utf-8'))
        run = await service.start(StartRequest.model_validate(payload))
    elif args.operation == 'inspect':
        run = store.get(args.run_id)
    else:
        if args.mutation == 'expire':
            # Advance only the host expiry clock; the confirmed proposal stays sealed.
            baseline_module.datetime = ExpiredClock
        run = await service.decide(args.run_id, args.accepted == 'true')
    if args.engine == 'langgraph':
        inspected = await service.inspect(run['run_id'])
        # Preserve transient replay flags from decide while including actual graph state.
        run = {**inspected, **run}
    return {
        'engine': args.engine, 'operation': args.operation, 'pid': os.getpid(),
        'captured_at': timestamp(), 'elapsed_seconds': round(perf_counter() - started, 6),
        'mutation': args.mutation, 'draft_count': store.draft_count(), 'run': run,
    }


def run_worker(engine, state_dir, request_file, operation, *, live, fault=None,
               run_id=None, decision=None, mutation=None):
    command = [sys.executable, '-m', 'scripts.run_week5_comparison', '--worker',
               '--engine', engine, '--state-dir', str(state_dir), '--operation', operation,
               '--request-file', str(request_file)]
    if live:
        command.append('--live')
    for flag, value in (('--fault', fault), ('--run-id', run_id), ('--mutation', mutation)):
        if value is not None:
            command.extend([flag, value])
    if decision is not None:
        command.extend(['--accepted', 'true' if decision else 'false'])
    started = perf_counter()
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=225)
    except subprocess.TimeoutExpired:
        return {'engine': engine, 'operation': operation, 'worker_error': 'WORKER_TIMEOUT',
                'elapsed_seconds': round(perf_counter() - started, 6)}
    try:
        body = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        # stderr and SDK exception messages are intentionally excluded from artifacts.
        return {'engine': engine, 'operation': operation, 'worker_error': 'INVALID_WORKER_OUTPUT',
                'exit_code': result.returncode,
                'elapsed_seconds': round(perf_counter() - started, 6)}
    body['process_elapsed_seconds'] = round(perf_counter() - started, 6)
    body['exit_code'] = result.returncode
    return body


def canonical_facts(run):
    """Only volatile IDs/times and engine diagnostics are excluded from A/B facts."""
    report = run.get('report')
    receipt = run.get('receipt')
    summary = run.get('summary')
    result = {
        'state': run.get('state'), 'error': run.get('error'),
        'live_status': run.get('live_status'), 'model_rounds': run.get('model_rounds'),
        'report': None, 'receipt': None, 'summary': None,
    }
    if report:
        result['report'] = {key: report[key] for key in (
            'assignment_id', 'submission_id', 'submission_version', 'source',
            'dataset_version', 'evidence_hash', 'report_hash', 'needs_revision',
            'needs_confirmation', 'items')}
    if receipt:
        result['receipt'] = {key: value for key, value in receipt.items()
                             if key not in ('draft_id', 'request_id', 'created_at')}
        result['receipt'].update(draft_id='<draft-id>', request_id='<run-id>')
    if summary:
        result['summary'] = {**summary, 'draft_id': '<draft-id>' if summary.get('draft_id') else None}
    return result


def metrics(run):
    audit = run.get('audit', [])
    metadata = run.get('provider_metadata', [])
    usages = [entry['usage'] for entry in metadata if isinstance(entry.get('usage'), dict)]
    return {
        'model_rounds': run.get('model_rounds', 0),
        'model_attempts': sum(event.get('event') == 'model_attempt' for event in audit),
        'successful_provider_responses': len(metadata),
        'actual_llm_responses': sum(entry.get('llm_actually_called') is True for entry in metadata),
        'read_executions': sum(event.get('event') == 'read_executed' for event in audit),
        'read_errors': sum(event.get('event') == 'read_error' for event in audit),
        'write_commits': sum(event.get('event') == 'write_committed' for event in audit),
        'provider_metadata': metadata,
        'tokens': {key: sum(usage.get(key, 0) or 0 for usage in usages)
                  for key in ('input_tokens', 'output_tokens', 'total_tokens')} if usages else None,
    }


def evaluate(case, operations, expected_report, live):
    checks = []

    def check(name, actual, expected):
        checks.append({'check': name, 'expected': expected, 'actual': actual, 'passed': actual == expected})

    check('worker_processes_succeeded', all('worker_error' not in op and op.get('exit_code') == 0
                                          for op in operations), True)
    successful = [op for op in operations if 'run' in op]
    if not successful:
        return checks
    first, final = successful[0], successful[-1]
    run = final['run']
    expected_count = case.get('writes', 0)
    check('terminal_state', run.get('state'), case['state'])
    check('error_code', (run.get('error') or {}).get('code'), case.get('error'))
    check('draft_count', final['draft_count'], expected_count)
    check('no_write_during_start', first['draft_count'], 0)
    pids = [op['pid'] for op in successful]
    check('fresh_process_for_each_action', len(set(pids)), len(pids))
    if 'decision' in case:
        check('proposal_waits_for_confirmation', first['run'].get('state'), 'awaiting_confirmation')
        reopened = next((op for op in successful if op['operation'] == 'inspect'), None)
        check('restart_preserves_wait', reopened['run'].get('state') if reopened else None,
              'awaiting_confirmation')
        check('restart_preserves_run_id', reopened['run'].get('run_id') if reopened else None,
              first['run'].get('run_id'))
        if first.get('engine') == 'langgraph':
            initial_graph = first['run'].get('orchestration', {})
            reopened_graph = reopened['run'].get('orchestration', {}) if reopened else {}
            check('real_checkpoint_created', bool(initial_graph.get('checkpoint_id')), True)
            check('real_interrupt_created', len(initial_graph.get('interrupts', [])), 1)
            check('checkpoint_survives_process_restart', reopened_graph.get('checkpoint_id'),
                  initial_graph.get('checkpoint_id'))
            check('interrupt_survives_process_restart', reopened_graph.get('interrupts'),
                  initial_graph.get('interrupts'))
            check('terminal_graph_has_no_pending_interrupt',
                  run.get('orchestration', {}).get('interrupts'), [])
        if len(successful) >= 4:
            decided, replayed = successful[-2:]
            check('replay_preserves_receipt', replayed['run'].get('receipt'), decided['run'].get('receipt'))
            check('replay_preserves_state', replayed['run'].get('state'), decided['run'].get('state'))
            check('replay_preserves_write_count', replayed['draft_count'], decided['draft_count'])
    if run.get('report'):
        for key in ('report_hash', 'needs_revision', 'needs_confirmation'):
            check('report_' + key, run['report'].get(key), expected_report[key])
    if case['state'] == 'completed':
        check('summary_facts', run.get('summary'), {
            'submission_id': IDENTITY['submission_id'], 'submission_version': IDENTITY['submission_version'],
            'needs_revision': expected_report['needs_revision'],
            'needs_confirmation': expected_report['needs_confirmation'],
            'draft_id': (run.get('receipt') or {}).get('draft_id'),
            'status': 'draft_created' if expected_count else 'reviewed',
        })
    else:
        check('no_unverified_summary', run.get('summary'), None)
    if expected_count:
        receipt = run.get('receipt') or {}
        check('receipt_uses_run_id', receipt.get('request_id'), run.get('run_id'))
        check('draft_remains_local', receipt.get('delivery'), 'local_only_not_sent')
    if case.get('fault') == 'provider429':
        check('provider_retry_budget', metrics(run)['model_attempts'], 2)
    if case.get('fault') == 'source_unavailable':
        check('missing_source_stops_before_model', metrics(run)['model_attempts'], 0)
    if case.get('fault') == 'summary_timeout':
        check('summary_retry_budget', sum(event.get('event') == 'model_attempt' and
              event.get('phase') == 'summary' for event in run.get('audit', [])), 2)
    if live:
        check('real_openai_success', run.get('live_status'), 'LIVE_PASS')
        check('actual_llm_responses', metrics(run)['actual_llm_responses'], 2 if case['intent'] == 'read' else 3)
    else:
        check('fixtures_are_not_live', metrics(run)['actual_llm_responses'], 0)
        check('fixture_live_status', run.get('live_status'), 'LIVE_NOT_RUN')
    return checks


def collect(output_dir, live=False):
    output_dir.mkdir(parents=True, exist_ok=True)
    source = provenance()
    cases = CASES[:2] if live else CASES
    expected_report, _ = get_review(IDENTITY)
    index = []
    for case in cases:
        paired = {}
        request = StartRequest(**IDENTITY, message=MESSAGE, intent=case['intent'],
                               mode='live' if live else 'fixture').model_dump()
        for engine in ENGINES:
            with tempfile.TemporaryDirectory(prefix='week5-' + engine + '-') as temporary:
                state_dir = Path(temporary)
                request_file = state_dir / 'request.json'
                request_file.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
                options = {'live': live, 'fault': case.get('fault')}
                operations = [run_worker(engine, state_dir, request_file, 'start', **options)]
                run_id = operations[0].get('run', {}).get('run_id')
                if run_id and 'decision' in case:
                    operations.append(run_worker(engine, state_dir, request_file, 'inspect',
                                                 run_id=run_id, **options))
                    operations.append(run_worker(engine, state_dir, request_file, 'decide', run_id=run_id,
                                                 decision=case['decision'], mutation=case.get('mutation'), **options))
                    operations.append(run_worker(engine, state_dir, request_file, 'decide',
                                                 run_id=run_id, decision=True, **options))
                checks = evaluate(case, operations, expected_report, live)
                final = next((op['run'] for op in reversed(operations) if 'run' in op), {})
                paired[engine] = {'operations': operations, 'checks': checks,
                                  'matches_expected': bool(checks) and all(item['passed'] for item in checks),
                                  'canonical_facts': canonical_facts(final), 'metrics': metrics(final),
                                  'total_process_seconds': round(sum(op.get('process_elapsed_seconds',
                                      op.get('elapsed_seconds', 0)) for op in operations), 6)}
        equal = paired['baseline']['canonical_facts'] == paired['langgraph']['canonical_facts']
        execution_equal = all(paired['baseline']['metrics'][key] == paired['langgraph']['metrics'][key]
                              for key in ('model_attempts', 'read_executions', 'write_commits', 'actual_llm_responses'))
        passed = equal and execution_equal and all(result['matches_expected'] for result in paired.values())
        record = {**source, 'case': case['case'], 'group': case['group'], 'captured_at': timestamp(),
                  'mode': 'live' if live else 'fixture', 'request': request,
                  'expected': {'state': case['state'], 'draft_count': case.get('writes', 0),
                               'error_code': case.get('error')},
                  'failure_injection': case.get('fault') or case.get('mutation'),
                  'expiry_injection_method': 'Advance shared host confirmation clock by 601 seconds; proposal timestamp unchanged'
                      if case.get('mutation') == 'expire' else None,
                  'write_response_loss_method': 'Week 4 after_write fault after atomic commit; process exits and replay opens DB anew'
                      if case.get('fault') == 'after_write' else None,
                  'data_source': 'synthetic assignment and submission only',
                  'approval_source': 'automated sandbox test decision, not an external user approval',
                  'shared_source': {key: expected_report[key] for key in ('source', 'dataset_version', 'evidence_hash', 'report_hash')},
                  'baseline': paired['baseline'], 'langgraph': paired['langgraph'],
                  'canonical_facts_equal': equal, 'execution_counts_equal': execution_equal,
                  'matches_expected': passed}
        (output_dir / (case['case'] + '.json')).write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        index.append({'case': case['case'], 'group': case['group'], 'matches_expected': passed,
                      'canonical_facts_equal': equal,
                      'execution_counts_equal': execution_equal,
                      'baseline_passed': paired['baseline']['matches_expected'],
                      'langgraph_passed': paired['langgraph']['matches_expected']})
        print(case['case'], 'PASS' if passed else 'FAIL', flush=True)
    result = {**source, 'captured_at': timestamp(), 'mode': 'live' if live else 'fixture',
              'cases': index, 'all_passed': all(case['matches_expected'] for case in index)}
    (output_dir / 'index.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0 if result['all_passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Make actual OpenAI requests for two paired scenarios')
    parser.add_argument('--output-dir', type=Path, default=Path('tmp/week5-comparison'))
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--engine', choices=ENGINES)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--operation', choices=('start', 'inspect', 'decide'))
    parser.add_argument('--request-file', type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--fault', choices=('provider429', 'missing_field', 'summary_timeout', 'after_write', 'source_unavailable'))
    parser.add_argument('--mutation', choices=('expire',))
    parser.add_argument('--accepted', choices=('true', 'false'))
    args = parser.parse_args()
    if args.worker:
        try:
            result = asyncio.run(worker(args))
        except Exception as error:
            result = {'engine': args.engine, 'operation': args.operation, 'pid': os.getpid(),
                      'worker_error': type(error).__name__}
            print(json.dumps(result, ensure_ascii=False), flush=True)
            return 1
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    return collect(args.output_dir, args.live)


if __name__ == '__main__':
    raise SystemExit(main())
