"""Week 6 evidence: the same synthetic PDF pair through the original and evaluator–optimizer paths.

Fixture cases replace only the OpenAI SDK call with authored drafts or injected errors, so request
building, error mapping, the Host gate and the HTTP API all run for real. --live spends OpenAI quota.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx
from openai import APITimeoutError

from assignment_checker.api import create_app
from assignment_checker.pdf_review import (DEFAULT_PDF_MODEL, PDFDraftReport, PDFInput, PDFReviewProvider,
    evaluate_draft, parse_pdf, resolve_draft)
from assignment_checker.provider import local_settings
from assignment_checker.service import CheckFailure
from assignment_checker.week7.routes import SessionService

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples/week6'
DRAFTS = json.loads((EXAMPLES / 'fixture-drafts.json').read_text(encoding='utf-8'))
WORKFLOWS = ('single', 'evaluator_optimizer')
LIGHT_MODEL = 'gpt-4.1-mini-2025-04-14'
MISSING_MODEL = 'gpt-week6-model-does-not-exist'
# Everything a run's outcome depends on; hashed and dirty-checked so evidence names the code that produced it.
INPUTS = ['assignment_checker/pdf_review.py', 'assignment_checker/pdf_review_prompt.txt',
          'assignment_checker/week6/workflow.py', 'assignment_checker/week6/revision_prompt.txt',
          'assignment_checker/week7/routes.py', 'assignment_checker/service.py',
          'examples/week6/teacher.pdf', 'examples/week6/student.pdf', 'examples/week6/fixture-drafts.json',
          'scripts/run_week6_comparison.py']
# Ground truth of the synthetic pair, written before any live run (see examples/week6/README.md).
EXPECTED_LIVE = {'http_status': 200, 'rubric_status': 'explicit_100_point_rubric', 'max_points': [20, 20, 20, 40],
                 'gap_std_dev_flagged': True, 'gap_improvement_section_flagged': True,
                 'gap_terminal_screenshot_flagged': True, 'grade_after_confirm': True}


def provenance():
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    return {'tested_commit_sha': git('rev-parse', 'HEAD'),
            'inputs_uncommitted': git('status', '--porcelain', '--', *INPUTS).splitlines(),
            'input_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in INPUTS},
            'captured_at': datetime.now(timezone.utc).isoformat(),
            'provider': 'openai', 'gemini_status': 'LIVE_NOT_RUN',
            'gemini_reason': 'Team chose the existing GPT API; the course Gemini/ADC requirement remains unmet',
            'data_source': 'synthetic_only'}


def pdf(name, data=None):
    raw = data if data is not None else (EXAMPLES / f'{name}.pdf').read_bytes()
    return {'filename': f'{name}.pdf', 'data_base64': base64.b64encode(raw).decode()}


def parsed():
    return tuple(parse_pdf(PDFInput(**pdf(name))) for name in ('teacher', 'student'))


def timeout():
    return APITimeoutError(request=httpx.Request('POST', 'https://api.openai.com/v1/responses'))


class ScriptedSDK:
    """Stands in for the OpenAI SDK: plays authored drafts (by name or value) or injected errors."""

    def __init__(self, *steps):
        self.steps, self.requests = list(steps), []
        self.responses = SimpleNamespace(parse=self.parse)

    def parse(self, **request):
        self.requests.append(request)
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        draft = DRAFTS[step] if isinstance(step, str) else step
        return SimpleNamespace(model='scripted-sdk-fixture', id=f'fixture-{len(self.requests)}', usage=None,
                               status='completed', output_parsed=PDFDraftReport.model_validate(draft))


class Recorder:
    """The provider the API sees: times and counts calls, keeps drafts, and never labels a fixture live."""

    def __init__(self, inner, live):
        self.inner, self.live, self.calls, self.drafts, self.metadata = inner, live, [], [], {}

    def draft(self, teacher, student, followup=()):
        self.inner.metadata = {}
        started, draft, error = perf_counter(), None, None
        try:
            draft = self.inner.draft(teacher, student, followup)
            self.drafts.append(draft.model_dump())
            return draft
        except CheckFailure as failure:
            error = failure.code
            raise
        finally:
            metadata = dict(self.inner.metadata)
            if metadata and not self.live:
                metadata.update(model='scripted-sdk-fixture', llm_actually_called=False)
            self.metadata = metadata
            self.calls.append({'call': len(self.calls) + 1, 'revision_turns': len(followup),
                               'responded': bool(metadata), 'error_code': error,
                               'wall_seconds': round(perf_counter() - started, 3) if self.live else None,
                               **{key: metadata.get(key) for key in ('model', 'response_id', 'usage')}})

    def generate(self, teacher, student):
        return resolve_draft(self.draft(teacher, student), teacher, student)


def costs(calls):
    """Sums only what was measured; a call without usage makes the token totals null, never 0."""
    sent = [call for call in calls if call['error_code'] != 'MISSING_API_KEY']
    unmeasured = sum(call['usage'] is None for call in sent)
    total = lambda pick: None if unmeasured or not sent else sum(pick(call['usage']) for call in sent)
    wall = [call['wall_seconds'] for call in sent]
    return {'provider_calls': len(sent), 'responded_calls': sum(call['responded'] for call in sent),
            'unmeasured_calls': unmeasured,
            'latency_seconds': None if not sent or None in wall else round(sum(wall), 3),
            'input_tokens': total(lambda u: u.get('input_tokens', 0)),
            'output_tokens': total(lambda u: u.get('output_tokens', 0)),
            'reasoning_tokens': total(lambda u: (u.get('output_tokens_details') or {}).get('reasoning_tokens', 0)),
            'total_tokens': total(lambda u: u.get('total_tokens', 0))}


class Bench:
    """One fresh Session and SQLite directory per run, driven through the real HTTP API."""

    def __init__(self, directory, provider):
        self.provider = provider
        self.service = SessionService(directory, pdf_provider=provider)
        self.client = TestClient(create_app(session_service=self.service))
        self.client.post('/assistant/week7/login', json={'profile': 'student-a'})

    def stored(self):
        with self.service.memory.db() as db:
            return db.execute('SELECT COUNT(*) FROM pdf_prechecks').fetchone()[0]

    def precheck(self, workflow, teacher=None, student=None):
        before = self.stored()
        response = self.client.post('/assistant/week7/pdf/precheck', json={
            'teacher': teacher or pdf('teacher'), 'student': student or pdf('student'), 'workflow': workflow})
        body = response.json()
        error = body.get('error') or {}
        flow = body.get('workflow') or error.get('workflow') or {}
        report = body.get('report') or {}
        return body, {
            'http_status': response.status_code, 'run_id': body.get('run_id'),
            'live_status': body.get('live_status'), 'error_code': error.get('code'),
            'error_stage': error.get('stage'), 'stop_reason': flow.get('stop_reason'),
            'draft_results': [{'draft': d['draft'], 'passed': d['passed'], 'issues': len(d['issues']),
                               'rules': sorted({i.get('rule') for i in d['issues']}), 'profile': d['profile'],
                               'same_as_previous': d.get('same_as_previous')}
                              for d in flow.get('drafts', [])],
            'records_added': self.stored() - before, 'grade_before_confirm': body.get('grade'),
            'check_status': {s: sum(c['status'] == s for c in report.get('checks', []))
                             for s in ('met', 'partial', 'missing', 'uncertain')} if report else None,
            'criteria': len(report.get('criteria', [])) if report else None,
            **costs(self.provider.calls)}

    def confirm(self, run_id):
        before = len(self.provider.calls)
        response = self.client.post(f'/assistant/week7/pdf/prechecks/{run_id}/confirm', json={'confirmed': True})
        return response.json(), {'http_status': response.status_code, 'grade': response.json().get('grade'),
                                 'confirmed_at': response.json().get('confirmed_at'),
                                 'provider_calls_added': len(self.provider.calls) - before}


def run_case(root, steps, workflow, **kwargs):
    sdk = ScriptedSDK(*steps)
    bench = Bench(root / f'{workflow}-{len(list(root.iterdir()))}', Recorder(PDFReviewProvider(client=sdk), live=False))
    body, actual = bench.precheck(workflow, **kwargs)
    return bench, sdk, body, actual


def subset(actual, expected):
    return {key: actual.get(key) for key in expected}


def relabelled():
    """Draft A breaks inference_not_uncertain; B 'fixes' it by calling the inference an explicit requirement."""
    a, b = json.loads(json.dumps(DRAFTS['valid'])), json.loads(json.dumps(DRAFTS['valid']))
    a['checks'][5].update(authority='example_inference', status='missing')
    b['checks'][5].update(authority='explicit_requirement', status='missing')
    return a, b


def fixture_cases(root):
    cases = []

    def record(case, workflow, expected, actual, note, **extra):
        observed = subset(actual, expected)
        cases.append({'case': case, 'workflow': workflow, 'mode': 'fixture', 'live_status': 'LIVE_NOT_RUN',
                      'note': note, 'expected': expected, 'actual': observed, 'passed': observed == expected,
                      'details': actual, **extra})

    for workflow in WORKFLOWS:
        bench, sdk, body, actual = run_case(root, ['valid'], workflow)
        record('1_normal', workflow, {'http_status': 200, 'provider_calls': 1, 'records_added': 1,
                                      'grade_before_confirm': None,
                                      'stop_reason': 'PASSED' if workflow == 'single' else 'PASSED_FIRST_DRAFT'},
               actual, 'Authored passing draft; normal-path behaviour without a model. Live run is separate.')

        _, confirm = bench.confirm(body['run_id'])
        replay, again = bench.confirm(body['run_id'])
        resend = {'http_status': again['http_status'], 'first_grade': confirm['grade'], 'second_grade': again['grade'],
                  'same_confirmed_at': confirm['confirmed_at'] == again['confirmed_at'],
                  'provider_calls': confirm['provider_calls_added'] + again['provider_calls_added'],
                  'records_total': bench.stored(), 'same_run_id': replay['run_id'] == body['run_id']}
        record('5_confirm_resend', workflow, {'http_status': 200, 'first_grade': {
                    'low': 42, 'high': 70, 'out_of': 100, 'label': '依目前 PDF 證據的預估區間，非教師正式成績或統計信賴區間'},
                'second_grade': confirm['grade'], 'same_confirmed_at': True, 'provider_calls': 0,
                'records_total': 1, 'same_run_id': True},
               resend, 'Same confirmed rubric sent twice for one run_id: the run_id is the request id.')

        before, calls = bench.stored(), len(bench.provider.calls)
        _, invalid = bench.precheck(workflow, teacher=pdf('teacher', b'not a pdf'))
        invalid.update(provider_calls=len(bench.provider.calls) - calls, records_added=bench.stored() - before,
                       returned_previous_run=invalid['run_id'] == body['run_id'])
        record('2_invalid_input', workflow, {'http_status': 422, 'error_code': 'INVALID_PDF', 'error_stage': 'pdf_input',
                                             'provider_calls': 0, 'records_added': 0,
                                             'returned_previous_run': False},
               invalid, 'Non-PDF bytes named teacher.pdf, sent after a successful run in the same Session.')

        _, _, _, actual = run_case(root, [timeout(), 'valid'], workflow)
        record('3_provider_timeout', workflow, {'http_status': 504, 'error_code': 'PROVIDER_UNAVAILABLE',
                                                'provider_calls': 1, 'records_added': 0,
                                                'stop_reason': None if workflow == 'single' else 'PROVIDER_ERROR'},
               actual, 'Injected SDK timeout on the first call; a passing draft is queued but must not be used.')

        bench, sdk, _, actual = run_case(root, ['invalid_refs', 'valid'], workflow)
        expected = ({'http_status': 502, 'error_code': 'INVALID_SOURCE_REFERENCE', 'provider_calls': 1,
                     'records_added': 0} if workflow == 'single' else
                    {'http_status': 200, 'provider_calls': 2, 'records_added': 1,
                     'stop_reason': 'PASSED_AFTER_REVISION'})
        revision = None
        if len(sdk.requests) > 1:
            second = sdk.requests[1]['input']
            revision = {'turns': [m['role'] for m in second],
                        'same_pdfs_resent': [p.get('filename') for p in second[1]['content'] if p['type'] == 'input_file'],
                        'previous_draft_is_A': second[2]['content'] == PDFDraftReport.model_validate(DRAFTS['invalid_refs']).model_dump_json(),
                        'findings_sent': json.loads(second[3]['content'].split('\n')[-1])['host_findings']}
        record('4a_revision_recovers', workflow, expected, actual,
               'Draft A has the two real LIVE_FAIL shapes (cross-page range, range past page end) and a wrong prefix.',
               revision_request=revision)

        if workflow == 'evaluator_optimizer':
            bench, sdk, _, actual = run_case(root, ['invalid_refs', 'invalid_refs', 'valid'], workflow)
            record('4b_limit_stops', workflow, {'http_status': 502, 'error_code': 'INVALID_SOURCE_REFERENCE',
                                                'provider_calls': 2, 'records_added': 0,
                                                'stop_reason': 'MAX_DRAFTS_UNRESOLVED',
                                                'grade_before_confirm': None},
                   actual, 'Both drafts fail; a passing third draft stays queued to prove the loop stops at 2.',
                   unused_steps=len(sdk.steps))
            roles_with_bad_ref = json.loads(json.dumps(DRAFTS['roles_mismatch']))
            roles_with_bad_ref['checks'][2]['teacher_evidence'] = {'start': 'S1L1', 'end': 'S1L1'}
            for name, first in (('4c_roles_not_revised', 'roles_mismatch'),
                                ('4c_roles_with_bad_ref_not_revised', roles_with_bad_ref)):
                bench, sdk, _, actual = run_case(root, [first, 'valid'], workflow)
                record(name, workflow, {'http_status': 502, 'provider_calls': 1, 'records_added': 0,
                                        'stop_reason': 'NOT_REVISABLE'},
                       actual, 'A wrong-files verdict is a judgement; the loop must not ask the model to flip it, '
                               'even when the same draft also has a bad line reference.')
            bench, sdk, _, actual = run_case(root, list(relabelled()), workflow)
            record('4d_relabel_rejected', workflow, {'http_status': 502, 'provider_calls': 2, 'records_added': 0,
                                                     'stop_reason': 'MAX_DRAFTS_UNRESOLVED'},
                   actual, 'B passes the gate only by relabelling an example inference as explicit; the revision '
                           'contract rejects it.')
            bench, sdk, _, actual = run_case(root, ['invalid_refs', timeout()], workflow)
            record('3b_timeout_on_revision', workflow, {'http_status': 504, 'error_code': 'PROVIDER_UNAVAILABLE',
                                                        'provider_calls': 2, 'records_added': 0,
                                                        'stop_reason': 'PROVIDER_ERROR'},
                   actual, 'Injected SDK timeout on the revision call: stop with the provider error, no third call.')
    return cases


def business(body, grade):
    report = body.get('report') or {}
    def flagged(word):
        # Any check citing that teacher line reports a gap; the model may split one requirement in two.
        return any(word in c['teacher_evidence']['quote'] and c['status'] != 'met' for c in report.get('checks', []))
    return {'rubric_status': report.get('rubric_status'),
            'max_points': sorted(c['max_points'] for c in report.get('criteria', [])),
            'gap_std_dev_flagged': flagged('標準差'), 'gap_improvement_section_flagged': flagged('改進方向'),
            'gap_terminal_screenshot_flagged': flagged('終端機'), 'grade_after_confirm': grade is not None}


def diagnose(drafts):
    """For a failed run, list what the Host found in each draft (the original path returns only the first)."""
    teacher, student = parsed()
    return [evaluate_draft(PDFDraftReport.model_validate(d), teacher, student)[1] for d in drafts]


def live_cases(root, emit, models):
    try:
        local_settings()
    except CheckFailure as error:
        for workflow in WORKFLOWS:
            emit({'case': '1_normal_live', 'workflow': workflow, 'mode': 'live', 'live_status': 'LIVE_NOT_RUN',
                  'note': f'{error.code}: no request sent', 'expected': EXPECTED_LIVE, 'actual': None,
                  'passed': False, 'details': {}})
        return
    for model in models:
        for workflow in WORKFLOWS:
            bench = Bench(root / f'{workflow}-{model}', Recorder(PDFReviewProvider(model=model), live=True))
            body, actual = bench.precheck(workflow)
            grade = None
            if actual['http_status'] == 200:
                _, confirmed = bench.confirm(body['run_id'])
                grade = confirmed['grade']
                actual.update(grade_after_confirm=grade, confirm_provider_calls_added=confirmed['provider_calls_added'])
            observed = {'http_status': actual['http_status'], **business(body, grade)}
            emit({'case': '1_normal_live', 'workflow': workflow, 'model': model, 'mode': 'live',
                  'live_status': 'LIVE_PASS' if actual['http_status'] == 200 else 'LIVE_FAIL',
                  'expected': EXPECTED_LIVE, 'actual': observed, 'passed': observed == EXPECTED_LIVE,
                  'details': actual, 'calls': bench.provider.calls, 'drafts': bench.provider.drafts,
                  'host_findings_per_draft': diagnose(bench.provider.drafts) if actual['http_status'] != 200 else None,
                  'body': body})
    for workflow in WORKFLOWS:
        bench = Bench(root / f'{workflow}-missing-model', Recorder(PDFReviewProvider(model=MISSING_MODEL), live=True))
        body, actual = bench.precheck(workflow)
        expected = {'http_status': 502, 'error_code': 'PROVIDER_ERROR', 'error_stage': 'provider',
                    'provider_calls': 1, 'records_added': 0}
        emit({'case': '3_provider_rejects_live', 'workflow': workflow, 'model': MISSING_MODEL, 'mode': 'live',
              'live_status': 'LIVE_FAIL' if actual['http_status'] != 200 else 'LIVE_PASS',
              'note': 'Real request with a model name that does not exist: a configuration fault, not an outage.',
              'expected': expected, 'actual': subset(actual, expected), 'passed': subset(actual, expected) == expected,
              'details': actual, 'calls': bench.provider.calls, 'body': body})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='call OpenAI (spends quota)')
    parser.add_argument('--allow-uncommitted', action='store_true', help='live run on uncommitted inputs')
    parser.add_argument('--model', action='append', dest='models', help='live models (default: both)')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'tmp/week6')
    args = parser.parse_args()
    meta = provenance()
    if args.live and meta['inputs_uncommitted'] and not args.allow_uncommitted:
        parser.error('commit the inputs first so the evidence names their SHA: ' + ', '.join(meta['inputs_uncommitted']))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cases = []

    def emit(case):
        # Written as soon as each case finishes, so a crash later never loses paid evidence.
        cases.append(case)
        name = f"{case['case']}-{case['workflow']}" + (f"-{case['model']}" if case.get('model') else '')
        (args.output_dir / f'{name}.json').write_text(
            json.dumps({**meta, **case}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    with tempfile.TemporaryDirectory() as directory:
        if args.live:
            live_cases(Path(directory), emit, args.models or [DEFAULT_PDF_MODEL, LIGHT_MODEL])
        else:
            for case in fixture_cases(Path(directory)):
                emit(case)
    keys = ('http_status', 'error_code', 'stop_reason', 'provider_calls', 'responded_calls', 'unmeasured_calls',
            'total_tokens', 'latency_seconds')
    summary = [{key: case.get(key) for key in ('case', 'workflow', 'model', 'mode', 'passed', 'live_status')}
               | {key: case['details'].get(key) for key in keys} for case in cases]
    (args.output_dir / 'summary.json').write_text(
        json.dumps({**meta, 'cases': summary}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for row in summary:
        print(json.dumps(row, ensure_ascii=False))
    return 0 if all(case['passed'] for case in cases) else 1


if __name__ == '__main__':
    raise SystemExit(main())
