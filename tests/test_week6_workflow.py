"""Week 6 evaluator–optimizer: same rules as the gate, one revision, bounded stop, honest labels."""
import base64
from copy import deepcopy
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from assignment_checker.api import create_app
from assignment_checker.pdf_review import (PDFDraftReport, PDFInput, PDFReviewProvider, ParsedPDF,
    evaluate_draft, parse_pdf, resolve_draft)
from assignment_checker.service import CheckFailure
from assignment_checker.week6.workflow import MAX_DRAFTS, REVISION_PROMPT, revise_until_valid
from assignment_checker.week7.routes import SessionService
from scripts.run_week6_comparison import DRAFTS, EXAMPLES, Recorder, ScriptedSDK, costs, pdf, relabelled, timeout


def documents():
    def load(name):
        data = base64.b64encode((EXAMPLES / f'{name}.pdf').read_bytes()).decode()
        return parse_pdf(PDFInput(filename=f'{name}.pdf', data_base64=data))
    return load('teacher'), load('student')


def draft(name='valid'):
    return deepcopy(DRAFTS[name])


def faults():
    """Each mutation breaks one gate rule; together they cover every rule the evaluator reports."""
    def text(start, end=None):
        return {'kind': 'text', 'text_reference': {'start': start, 'end': end or start}, 'visual_page': None,
                'observation': None}
    cases = {'valid': draft(), 'invalid_refs': draft('invalid_refs'), 'roles': draft('roles_mismatch')}
    def mutate(name, change):
        value = draft(); change(value); cases[name] = value
    mutate('reversed_range', lambda d: d['checks'][0]['teacher_evidence'].update(start='T1L7', end='T1L6'))
    mutate('mixed_fields', lambda d: d['checks'][0]['student_evidence'][0].update(observation='paraphrase'))
    mutate('blank_line', lambda d: d['checks'][0]['teacher_evidence'].update(start='T1L11', end='T1L11'))
    mutate('rubric_total', lambda d: d['criteria'].pop())
    mutate('rubric_absent', lambda d: d.update(rubric_status='not_found_or_ambiguous'))
    mutate('duplicate_id', lambda d: d['criteria'][1].update(id='G1'))
    mutate('duplicate_name', lambda d: d['criteria'][1].update(name='程式功能正確性'))
    mutate('duplicate_source', lambda d: d['criteria'][1].update(teacher_evidence={'start': 'T2L2', 'end': 'T2L2'}))
    mutate('points_not_quoted', lambda d: d['criteria'][0].update(teacher_evidence={'start': 'T2L3', 'end': 'T2L3'}))
    mutate('score_without_evidence', lambda d: d['criteria'][1].update(student_evidence=[]))
    mutate('inference', lambda d: d['checks'][0].update(authority='example_inference'))
    mutate('status_without_evidence', lambda d: d['checks'][0].update(student_evidence=[]))
    mutate('visual_page', lambda d: d['checks'][1]['student_evidence'][0].update(visual_page=9))
    mutate('two_rules', lambda d: (d['checks'][0].update(student_evidence=[]),
                                   d['checks'][5].update(authority='example_inference', status='missing')))
    mutate('student_range', lambda d: d['checks'][2]['student_evidence'].append(text('S2L1', 'S3L1')))
    mutate('roles_with_bad_ref', lambda d: (d.update(document_roles_match=False),
                                            d['checks'][2].update(teacher_evidence={'start': 'S1L1', 'end': 'S1L1'})))
    return cases


@pytest.mark.parametrize('name', list(faults()))
def test_evaluator_accepts_exactly_what_the_gate_accepts(name):
    teacher, student = documents()
    # One spare blank teacher line so a reference can resolve to whitespace only.
    teacher = ParsedPDF(teacher.filename, teacher.data, [teacher.pages[0] + '\n ', teacher.pages[1]])
    value = PDFDraftReport.model_validate(faults()[name])
    report, issues = evaluate_draft(value, teacher, student)
    try:
        expected, gate = resolve_draft(value, teacher, student), None
    except CheckFailure as error:
        expected, gate = None, error
    assert (report is None) == (gate is not None) == bool(issues)
    if gate:
        assert issues[0]['code'] == gate.code
        if gate.code != 'INVALID_PDF_REPORT':
            assert issues[0]['message'] == gate.message
    else:
        assert report == expected
    if name == 'two_rules':
        assert [i['rule'] for i in issues] == ['status_without_evidence', 'inference_not_uncertain']
    if name == 'invalid_refs':
        assert [i['reference'] for i in issues] == ['T1L10–T2L5', 'S1L1–S1L1', 'S1L1–S1L13']
    if name == 'roles_with_bad_ref':
        assert [i['rule'] for i in issues] == ['source_reference', 'document_roles']


def loop(*steps):
    sdk = ScriptedSDK(*steps)
    return sdk, PDFReviewProvider(client=sdk)


def test_first_draft_that_passes_costs_one_call():
    sdk, provider = loop('valid', 'valid')
    report, trace = revise_until_valid(provider, *documents())
    assert len(sdk.requests) == 1 and len(sdk.requests[0]['input']) == 2
    assert trace['stop_reason'] == 'PASSED_FIRST_DRAFT' and trace['provider_calls'] == 1
    assert report.criteria[0].teacher_evidence.quote == '程式功能正確性 40%'


def test_revision_keeps_A_sends_located_findings_and_same_inputs():
    sdk, provider = loop('invalid_refs', 'valid')
    report, trace = revise_until_valid(provider, *documents())
    first, second = sdk.requests
    assert second['model'] == first['model'] and second['store'] is False
    assert second['input'][:2] == first['input']  # same system prompt, source lines and both PDFs
    assert [m['role'] for m in second['input']] == ['system', 'user', 'assistant', 'user']
    assert second['input'][2]['content'] == PDFDraftReport.model_validate(DRAFTS['invalid_refs']).model_dump_json()
    feedback = second['input'][3]['content']
    assert feedback.startswith(REVISION_PROMPT)
    findings = json.loads(feedback.split('\n')[-1])['host_findings']
    assert [f['where'] for f in findings] == ['criteria[3].teacher_evidence', 'checks[2].teacher_evidence',
                                              'checks[4].student_evidence[0]']
    assert 'student-a' not in json.dumps(second, default=str)  # no identity or Session context
    assert trace['stop_reason'] == 'PASSED_AFTER_REVISION' and trace['provider_calls'] == 2
    assert [d['passed'] for d in trace['drafts']] == [False, True]
    assert trace['drafts'][0]['content'] == DRAFTS['invalid_refs']
    assert trace['drafts'][0]['sha256'] != trace['drafts'][1]['sha256']


def test_mixed_evidence_fields_get_a_field_level_fix_while_the_gate_message_stays():
    # The live gpt-4.1-mini shape: text evidence with a paraphrase in `observation`.
    value = draft()
    value['checks'][0]['student_evidence'][0]['observation'] = '學生說明以 C++17 撰寫。'
    sdk, provider = loop(value, 'valid')
    _, trace = revise_until_valid(provider, *documents())
    issue = trace['drafts'][0]['issues'][0]
    assert issue['message'] == '文字引用與圖像觀察的欄位不可混用。'
    assert issue['fix'].startswith('observation 必須為 null')
    sent = json.loads(sdk.requests[1]['input'][3]['content'].split('\n')[-1])['host_findings']
    assert sent[0]['fix'] == issue['fix']


def test_limit_stops_without_grade_even_when_another_draft_would_pass():
    sdk, provider = loop('invalid_refs', 'invalid_refs', 'valid')
    with pytest.raises(CheckFailure) as error:
        revise_until_valid(provider, *documents())
    assert MAX_DRAFTS == 2 and len(sdk.requests) == 2 and sdk.steps == ['valid']
    flow = error.value.workflow
    assert [d['same_as_previous'] for d in flow['drafts']] == [False, True]
    assert flow['stop_reason'] == 'MAX_DRAFTS_UNRESOLVED' and error.value.code == 'INVALID_SOURCE_REFERENCE'
    assert error.value.status_code == 502
    body = json.dumps(error.value.body(), ensure_ascii=False)
    assert 'content' not in flow['drafts'][0] and 'score_low' not in body and '程式功能' not in body


def roles_with_bad_ref():
    value = draft('roles_mismatch')
    value['checks'][2]['teacher_evidence'] = {'start': 'S1L1', 'end': 'S1L1'}
    return value


@pytest.mark.parametrize('first', ['roles_mismatch', roles_with_bad_ref()])
def test_wrong_files_verdict_is_not_sent_back_for_revision(first):
    sdk, provider = loop(first, 'valid')
    with pytest.raises(CheckFailure) as error:
        revise_until_valid(provider, *documents())
    assert len(sdk.requests) == 1 and error.value.workflow['stop_reason'] == 'NOT_REVISABLE'
    assert sdk.steps == ['valid']


def test_roles_verdict_on_the_revision_stops_without_claiming_no_revision():
    sdk, provider = loop('invalid_refs', 'roles_mismatch')
    with pytest.raises(CheckFailure) as error:
        revise_until_valid(provider, *documents())
    assert len(sdk.requests) == 2 and error.value.workflow['stop_reason'] == 'NOT_REVISABLE'
    assert '未進行修訂' not in error.value.message


def test_revision_cannot_pass_by_relabelling_an_example_inference():
    sdk, provider = loop(*relabelled())
    with pytest.raises(CheckFailure) as error:
        revise_until_valid(provider, *documents())
    flow = error.value.workflow
    assert flow['stop_reason'] == 'MAX_DRAFTS_UNRESOLVED' and len(sdk.requests) == 2
    assert [i['rule'] for i in flow['drafts'][1]['issues']] == ['revision_relabelled_inference']
    assert flow['drafts'][0]['profile']['check_authority'] != flow['drafts'][1]['profile']['check_authority']


def test_configuration_failure_sends_no_request_and_is_labelled_as_such():
    class Unconfigured:
        metadata = {}
        def draft(self, *args):
            raise CheckFailure('MISSING_API_KEY', 'configuration', '請在專案 .env 設定 OPENAI_API_KEY。', 503)
    with pytest.raises(CheckFailure) as error:
        revise_until_valid(Unconfigured(), *documents())
    assert error.value.workflow['stop_reason'] == 'CONFIGURATION_ERROR'
    assert error.value.workflow['provider_calls'] == 0 and error.value.status_code == 503


def test_unparsed_billed_response_still_counts_as_a_call():
    sdk, provider = loop(ValueError('truncated JSON'))
    with pytest.raises(CheckFailure) as error:
        provider.draft(*documents())
    assert error.value.code == 'INVALID_PDF_REPORT'
    assert provider.metadata['llm_actually_called'] and provider.metadata['response_unparsed']
    assert provider.metadata['usage'] is None and provider.metadata['latency_seconds'] >= 0


def test_costs_never_report_unmeasured_tokens_or_latency_as_zero():
    measured = {'error_code': None, 'responded': True, 'wall_seconds': 2.0,
                'usage': {'input_tokens': 900, 'output_tokens': 100, 'total_tokens': 1000}}
    lost = {'error_code': 'PROVIDER_UNAVAILABLE', 'responded': False, 'wall_seconds': 120.0, 'usage': None}
    assert costs([measured])['total_tokens'] == 1000
    both = costs([measured, lost])
    assert both['total_tokens'] is None and both['unmeasured_calls'] == 1 and both['latency_seconds'] == 122.0
    assert costs([{**measured, 'wall_seconds': None}])['latency_seconds'] is None


@pytest.mark.parametrize('steps,calls', [([timeout(), 'valid'], 1), (['invalid_refs', timeout(), 'valid'], 2)])
def test_provider_failure_stops_with_the_original_error(steps, calls):
    sdk, provider = loop(*steps)
    with pytest.raises(CheckFailure) as error:
        revise_until_valid(provider, *documents())
    assert len(sdk.requests) == calls
    assert (error.value.code, error.value.status_code) == ('PROVIDER_UNAVAILABLE', 504)
    assert error.value.workflow['stop_reason'] == 'PROVIDER_ERROR' and error.value.workflow['failed_draft'] == calls


def test_profiles_show_what_a_revision_changed():
    gamed = draft()
    gamed['checks'][0].update(status='uncertain', student_evidence=[])
    a = draft()
    a['checks'][0]['student_evidence'] = []
    _, provider = loop(a, gamed)
    _, trace = revise_until_valid(provider, *documents())
    before, after = (d['profile']['check_status'] for d in trace['drafts'])
    assert before['met'] == 1 and after.get('met', 0) == 0 and after['uncertain'] == before['uncertain'] + 1


def bench(tmp_path, *steps):
    sdk = ScriptedSDK(*steps)
    provider = Recorder(PDFReviewProvider(client=sdk), live=False)
    service = SessionService(tmp_path, pdf_provider=provider)
    client = TestClient(create_app(session_service=service))
    client.post('/assistant/week7/login', json={'profile': 'student-a'})
    return client, service, sdk


def test_http_candidate_hides_stored_drafts_and_scores_until_confirmed(tmp_path):
    client, service, sdk = bench(tmp_path, 'invalid_refs', 'valid')
    body = client.post('/assistant/week7/pdf/precheck', json={'teacher': pdf('teacher'), 'student': pdf('student'),
                                                              'workflow': 'evaluator_optimizer'}).json()
    assert body['workflow']['stop_reason'] == 'PASSED_AFTER_REVISION' and body['live_status'] == 'LIVE_NOT_RUN'
    assert 'content' not in json.dumps(body['workflow']) and 'score_low' not in json.dumps(body)
    stored = service.pdf_prechecks.get({'session_id': body['session_id'], 'owner_id': body['owner_id']}, body['run_id'])
    assert stored['workflow']['drafts'][0]['content'] == DRAFTS['invalid_refs']
    confirmed = client.post(f"/assistant/week7/pdf/prechecks/{body['run_id']}/confirm", json={'confirmed': True}).json()
    assert confirmed['grade']['low'] == 42 and 'content' not in json.dumps(confirmed['workflow'])
    assert len(sdk.requests) == 2


def test_http_default_is_the_original_path_and_unknown_workflow_is_rejected(tmp_path):
    client, _, sdk = bench(tmp_path, 'invalid_refs', 'valid')
    endpoint = '/assistant/week7/pdf/precheck'
    original = client.post(endpoint, json={'teacher': pdf('teacher'), 'student': pdf('student')})
    assert original.status_code == 502 and original.json()['error']['code'] == 'INVALID_SOURCE_REFERENCE'
    assert 'workflow' not in original.json()['error'] and len(sdk.requests) == 1
    unknown = client.post(endpoint, json={'teacher': pdf('teacher'), 'student': pdf('student'), 'workflow': 'retry'})
    assert unknown.status_code == 422 and len(sdk.requests) == 1
