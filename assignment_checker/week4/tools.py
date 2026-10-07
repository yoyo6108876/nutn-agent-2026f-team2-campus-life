"""Read current fixture report under Week 3 source and citation policy."""
from .contracts import ReadArgs, IDENTITY, FlowError
from ..retrieval import prepare, validate_answer, render, load_json, digest


def get_review(arguments):
    args = ReadArgs.model_validate(arguments)
    if args.model_dump() != IDENTITY:
        raise FlowError('SUBMISSION_NOT_FOUND', 'read_tool')
    bundle, trace = prepare('Q1')
    if trace['gate'] != 'ready':
        raise FlowError(trace['refusal_code'], 'rag_gate')
    validated = validate_answer(bundle, load_json('generator-fixtures.json')['Q1'])
    rows = render(bundle, validated)
    result = {**IDENTITY, 'source':'synthetic-review-v1',
              'review_origin':'authored fixture, not a new LLM grading result',
              'items':rows, 'evidence_hash':bundle.evidence_hash,
              'dataset_version':trace['dataset_version'],
              'needs_revision':[r['fact_id'] for r in rows if r['value'] in ('partial','missing')],
              'needs_confirmation':[r['fact_id'] for r in rows if r['value']=='uncertain']}
    result['report_hash'] = digest(result)
    return result, trace
