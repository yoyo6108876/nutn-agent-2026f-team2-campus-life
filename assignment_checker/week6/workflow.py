"""Evaluator–optimizer for the PDF precheck draft.

The Host gate's own rules evaluate each draft. Failures go back to the model as located findings,
the revision is evaluated by the same rules plus one revision contract, and the loop stops at
MAX_DRAFTS without a grade.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from ..pdf_review import evaluate_draft
from ..service import CheckFailure

MAX_DRAFTS = 2
REVISION_PROMPT_VERSION = 'pdf-revision-v2'
REVISION_PROMPT = Path(__file__).with_name('revision_prompt.txt').read_text(encoding='utf-8')
# A wrong-files verdict is a judgement about the upload, not a citation error; asking again only pressures it.
NOT_REVISABLE = {'document_roles'}
STOP_MESSAGES = {
    'MAX_DRAFTS_UNRESOLVED': '修訂後仍未通過來源與配分核對，已達草稿上限，未提供估分。',
    'NOT_REVISABLE': '模型判斷老師規格與學生作業可能放反或不屬於同一作業，不再修訂、不提供估分，請確認檔案。',
}
# Only provider and schema stages mean a request went out; configuration fails before any call.
STOP_FOR_STAGE = {'provider': 'PROVIDER_ERROR', 'response_schema': 'DRAFT_UNUSABLE',
                  'configuration': 'CONFIGURATION_ERROR'}


def call_record(metadata):
    return {key: metadata[key] for key in ('model', 'response_id', 'latency_seconds', 'usage',
                                           'llm_actually_called') if key in metadata}


def profile(draft):
    """Counts only, so a trace shows what a revision changed without model text or unconfirmed scores."""
    items = [*draft.criteria, *draft.checks]
    return {'document_roles_match': draft.document_roles_match, 'rubric_status': draft.rubric_status,
            'criteria': len(draft.criteria), 'checks': len(draft.checks),
            'check_status': dict(Counter(c.status for c in draft.checks)),
            'check_authority': dict(Counter(c.authority for c in draft.checks)),
            'student_evidence': dict(Counter(e.kind for item in items for e in item.student_evidence))}


def revision_issues(previous, draft):
    """Revision contract on top of the gate: an example inference may not come back as an explicit requirement.

    Relabelling is the one way to pass inference_not_uncertain that makes a stronger claim against the student;
    the safe fix (status uncertain) keeps the count.
    """
    count = lambda d: sum(c.authority == 'example_inference' for c in d.checks)
    if count(draft) < count(previous):
        return [{'code': 'UNGROUNDED_PDF_REPORT', 'where': 'checks', 'rule': 'revision_relabelled_inference',
                 'message': '修訂稿把僅從範例推測的要求改成明確要求，不採用。'}]
    return []


def revision_turns(draft, issues):
    findings = [{key: issue[key] for key in ('code', 'rule', 'where', 'reference', 'message', 'fix')
                 if issue.get(key) is not None} for issue in issues]
    return [{'role': 'assistant', 'content': draft.model_dump_json()},
            {'role': 'user', 'content': REVISION_PROMPT + '\n'
             + json.dumps({'host_findings': findings}, ensure_ascii=False)}]


def public_trace(trace):
    """The stored trace keeps each draft; responses and errors carry only its evaluation and counts."""
    result = deepcopy(trace)
    for entry in result['drafts']:
        entry.pop('content', None)
    return result


def revise_until_valid(provider, teacher, student, max_drafts=MAX_DRAFTS):
    trace = {'name': 'evaluator_optimizer', 'max_drafts': max_drafts,
             'revision_prompt_version': REVISION_PROMPT_VERSION, 'provider_calls': 0,
             'drafts': [], 'stop_reason': None}
    followup, previous = (), None
    for number in range(1, max_drafts + 1):
        try:
            draft = provider.draft(teacher, student, followup)
        except CheckFailure as error:
            # Provider, schema and configuration failures are not citation errors: stop with the original error.
            reason = STOP_FOR_STAGE.get(error.stage, 'DRAFT_UNUSABLE')
            trace['provider_calls'] += reason != 'CONFIGURATION_ERROR'
            trace.update(stop_reason=reason, failed_draft=number, error_code=error.code)
            error.workflow = public_trace(trace)
            raise
        trace['provider_calls'] += 1
        report, issues = evaluate_draft(draft, teacher, student)
        if previous is not None and (guard := revision_issues(previous, draft)):
            report, issues = None, issues + guard
        content = draft.model_dump()
        digest = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        trace['drafts'].append({
            'draft': number, 'call': call_record(provider.metadata), 'passed': report is not None,
            'issues': issues, 'profile': profile(draft), 'content': content, 'sha256': digest,
            'same_as_previous': bool(trace['drafts']) and trace['drafts'][-1]['sha256'] == digest,
        })
        if report is not None:
            trace['stop_reason'] = 'PASSED_FIRST_DRAFT' if number == 1 else 'PASSED_AFTER_REVISION'
            return report, trace
        if any(issue.get('rule') in NOT_REVISABLE for issue in issues):
            trace['stop_reason'] = 'NOT_REVISABLE'
            break
        followup, previous = revision_turns(draft, issues), draft
    else:
        trace['stop_reason'] = 'MAX_DRAFTS_UNRESOLVED'
    last = trace['drafts'][-1]['issues'][0]
    detail = '' if trace['stop_reason'] == 'NOT_REVISABLE' else last['message']
    raise CheckFailure(last['code'], 'grounding', STOP_MESSAGES[trace['stop_reason']] + detail,
                       workflow=public_trace(trace))
