"""Ensure A/B normalization removes run IDs without concealing semantic changes."""
from copy import deepcopy

from scripts.run_week5_comparison import canonical_facts


def run():
    return {
        'run_id': 'run-a', 'state': 'completed', 'live_status': 'LIVE_NOT_RUN', 'model_rounds': 3,
        'receipt': {'draft_id': 'draft-a', 'request_id': 'run-a', 'created_at': '2026-10-14',
                    'report_hash': 'source-hash', 'needs_revision': ['failure_case'],
                    'needs_confirmation': ['appendix'], 'delivery': 'local_only_not_sent'},
        'summary': {'draft_id': 'draft-a', 'needs_revision': ['failure_case'],
                    'needs_confirmation': ['appendix'], 'status': 'draft_created'},
    }


def test_canonical_comparison_ignores_only_volatile_ids_times_and_engine_diagnostics():
    baseline = run()
    candidate = deepcopy(baseline)
    candidate.update(run_id='run-b', engine='langgraph', orchestration={'checkpoint_id': 'checkpoint-b'})
    candidate['receipt'].update(draft_id='draft-b', request_id='run-b', created_at='2026-10-15')
    candidate['summary']['draft_id'] = 'draft-b'
    assert canonical_facts(baseline) == canonical_facts(candidate)
    assert baseline['receipt']['draft_id'] == 'draft-a'  # Raw evidence must remain intact.


def test_canonical_comparison_preserves_summary_and_source_mismatches():
    baseline = run()
    candidate = deepcopy(baseline)
    candidate['summary']['needs_revision'] = []
    assert canonical_facts(baseline) != canonical_facts(candidate)
    candidate = deepcopy(baseline)
    candidate['receipt']['report_hash'] = 'other-source'
    assert canonical_facts(baseline) != canonical_facts(candidate)


def test_canonical_comparison_preserves_error_state_and_retry_budget():
    baseline = run()
    candidate = deepcopy(baseline)
    candidate.update(state='written', error={'code': 'PROVIDER_TIMEOUT', 'layer': 'provider', 'retryable': True})
    assert canonical_facts(baseline) != canonical_facts(candidate)
    candidate = deepcopy(baseline)
    candidate['model_rounds'] = 4
    assert canonical_facts(baseline) != canonical_facts(candidate)
