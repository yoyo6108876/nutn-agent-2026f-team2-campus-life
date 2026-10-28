import base64
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
from openai import OpenAI
import httpx
from pypdf import PdfWriter
import pytest

from assignment_checker.api import create_app
from assignment_checker.pdf_review import (PDFInput, PDFPair, ParsedPDF, PDFModelReport,
    PDFReviewProvider, PDFPrechecks, parse_pdf, validate_report)
from assignment_checker.service import CheckFailure
from assignment_checker.week7.memory import SessionMemory
from assignment_checker.week7.routes import SessionService


def documents():
    return (ParsedPDF('teacher.pdf',b'%PDF-fixture',['Report quality 100%\nExplain input and result.']),
            ParsedPDF('student.pdf',b'%PDF-fixture',['Input is empty.']))


def raw_report():
    return {'document_roles_match':True,'rubric_status':'explicit_100_point_rubric',
        'criteria':[{'id':'G1','name':'Report quality','max_points':100,
          'teacher_evidence':{'page':1,'quote':'Report quality 100%'},
          'score_low':40,'score_high':65,'rationale':'Missing result detail.',
          'student_evidence':[{'page':1,'kind':'text','quote_or_observation':'Input is empty.'}],
          'verification':'pdf_evidence_only'}],
        'checks':[{'requirement':'Explain input and result.','authority':'explicit_requirement',
          'teacher_evidence':{'page':1,'quote':'Explain input and result.'},'status':'partial',
          'student_evidence':[{'page':1,'kind':'text','quote_or_observation':'Input is empty.'}],
          'reason':'Only input described.','action':'Add actual result.','priority':'high'}],
        'summary':'Add the result.','limitations':['PDF only; not compiled.']}


def blank_pdf(pages=1,password=None):
    writer=PdfWriter()
    for _ in range(pages):writer.add_blank_page(200,200)
    if password:writer.encrypt(password)
    stream=BytesIO();writer.write(stream)
    return PDFInput(filename='demo.pdf',data_base64=base64.b64encode(stream.getvalue()).decode())


def test_parser_handles_page_images_without_assuming_no_work():
    parsed=parse_pdf(blank_pdf(2))
    assert parsed.pages==['','']
    assert parsed.metadata()['pages']==2


@pytest.mark.parametrize('kind,code',[
    ('wrong_extension','PDF_REQUIRED'),('bad_base64','INVALID_PDF_ENCODING'),
    ('not_pdf','INVALID_PDF'),('malformed','INVALID_PDF'),('encrypted','ENCRYPTED_PDF'),('too_many_pages','PDF_PAGE_LIMIT')])
def test_invalid_pdf_rejected_before_model(kind,code):
    value=blank_pdf()
    if kind=='wrong_extension':value.filename='demo.txt'
    if kind=='bad_base64':value.data_base64='invalid*'
    if kind=='not_pdf':value.data_base64=base64.b64encode(b'not a pdf').decode()
    if kind=='malformed':value.data_base64=base64.b64encode(b'%PDF-broken').decode()
    if kind=='encrypted':value=blank_pdf(password='test-password')
    if kind=='too_many_pages':value=blank_pdf(26)
    with pytest.raises(CheckFailure) as error:parse_pdf(value)
    assert error.value.code==code


def test_grounding_supports_visual_evidence_without_calling_it_verified_text():
    teacher,student=documents();raw=raw_report()
    raw['checks'][0]['student_evidence']=[{'page':1,'kind':'visual','quote_or_observation':'Screenshot shows a chart.'}]
    report=validate_report(raw,teacher,student)
    assert report.checks[0].student_evidence[0].kind=='visual'


@pytest.mark.parametrize('fault',['teacher_quote','student_quote','page','score_range','weight','rubric_sum','inferred_requirement','roles','duplicate_rubric'])
def test_fabrication_and_bad_scores_rejected(fault):
    teacher,student=documents();raw=raw_report()
    if fault=='teacher_quote':raw['checks'][0]['teacher_evidence']['quote']='Invented requirement'
    if fault=='student_quote':raw['checks'][0]['student_evidence'][0]['quote_or_observation']='Invented result'
    if fault=='page':raw['checks'][0]['student_evidence'][0]['page']=2
    if fault=='score_range':raw['criteria'][0]['score_high']=101
    if fault=='weight':teacher.pages[0]='Report quality 20%\nExplain input and result.'
    if fault=='rubric_sum':raw['criteria'][0]['max_points']=90
    if fault=='inferred_requirement':raw['checks'][0]['authority']='example_inference'
    if fault=='roles':raw['document_roles_match']=False
    if fault=='duplicate_rubric':raw['criteria'].append(deepcopy(raw['criteria'][0]));raw['criteria'][1]['id']='G2'
    with pytest.raises(CheckFailure):validate_report(raw,teacher,student)


def test_no_explicit_rubric_does_not_fabricate_grade():
    teacher,student=documents();raw=raw_report();raw.update(rubric_status='not_found_or_ambiguous',criteria=[])
    assert validate_report(raw,teacher,student).criteria==[]
    raw['criteria']=raw_report()['criteria']
    with pytest.raises(CheckFailure):validate_report(raw,teacher,student)


class FixturePDFProvider:
    metadata={'model':'authored fixture','llm_actually_called':False}
    def generate(self,*args):return raw_report()


def setup_http(tmp_path,monkeypatch):
    monkeypatch.setattr('assignment_checker.pdf_review.parse_pdf',lambda value:documents()[0 if value.filename=='teacher.pdf' else 1])
    service=SessionService(tmp_path,pdf_provider=FixturePDFProvider())
    client=TestClient(create_app(session_service=service))
    client.post('/assistant/week7/login',json={'profile':'student-a'})
    payload={'teacher':{'filename':'teacher.pdf','data_base64':'test'},'student':{'filename':'student.pdf','data_base64':'test'}}
    return client,service,payload


def test_http_confirm_is_required_and_replay_preserves_grade(tmp_path,monkeypatch):
    client,service,payload=setup_http(tmp_path,monkeypatch)
    preview=client.post('/assistant/week7/pdf/precheck',json=payload).json()
    assert preview['grade'] is None and 'score_low' not in preview['report']['criteria'][0]
    assert preview['live_status']=='LIVE_NOT_RUN'
    path='/assistant/week7/pdf/prechecks/'+preview['run_id']
    assert client.post(path+'/confirm',json={'confirmed':False}).status_code==409
    assert client.post(path+'/confirm',json={'confirmed':'true'}).status_code==422
    first=client.post(path+'/confirm',json={'confirmed':True}).json()
    second=client.post(path+'/confirm',json={'confirmed':True}).json()
    assert first==second
    assert first['grade']['low']==40 and first['grade']['high']==65
    assert 'data_base64' not in str(first)
    assert service.store.draft_count()==0


def test_pdf_report_is_private_and_clear_revokes_access(tmp_path,monkeypatch):
    client,service,payload=setup_http(tmp_path,monkeypatch)
    preview=client.post('/assistant/week7/pdf/precheck',json=payload).json()
    path='/assistant/week7/pdf/prechecks/'+preview['run_id']
    b=TestClient(create_app(session_service=service));b.post('/assistant/week7/login',json={'profile':'student-b'})
    assert b.get(path).status_code==404
    assert b.post(path+'/confirm',json={'confirmed':True}).status_code==404
    session=client.get('/assistant/week7/session').json()['session']['session_id']
    client.post('/assistant/week7/session/reset',json={'session_id':session,'confirmed':True})
    assert client.get(path).status_code==404
    assert client.post(path+'/confirm',json={'confirmed':True}).status_code==404


def test_http_requires_login_origin_and_bounded_upload(tmp_path,monkeypatch):
    client,service,payload=setup_http(tmp_path,monkeypatch)
    endpoint='/assistant/week7/pdf/precheck'
    assert TestClient(create_app(session_service=service)).post(endpoint,json=payload).status_code==401
    assert client.post(endpoint,json=payload,headers={'Origin':'https://other.example'}).status_code==403
    assert client.post(endpoint,content='not-json').status_code==422
    monkeypatch.setattr('assignment_checker.week7.routes.MAX_BODY_BYTES',10)
    assert client.post(endpoint,json=payload).status_code==413


def test_pdf_provider_uses_both_pdf_images_one_call_and_sanitizes_metadata():
    model=PDFModelReport.model_validate(raw_report())
    parse=Mock(return_value=SimpleNamespace(model='gpt-test',id='resp-test',usage=None,status='completed',output_parsed=model))
    provider=PDFReviewProvider(client=SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    provider.generate(*documents())
    options=parse.call_args.kwargs
    files=[p for p in options['input'][1]['content'] if p['type']=='input_file']
    assert [p['filename'] for p in files]==['teacher.pdf','student.pdf']
    assert all(p['detail']=='high' and p['file_data'].startswith('data:application/pdf;base64,') for p in files)
    assert options['store'] is False and parse.call_count==1
    assert 'file_data' not in str(provider.metadata)


def test_pdf_provider_failure_never_exposes_upstream_body():
    def handler(req):return httpx.Response(401,json={'error':{'message':'sensitive-upstream-value','type':'invalid_api_key','code':'invalid_api_key'}})
    with OpenAI(api_key='test-only',max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(CheckFailure) as error:PDFReviewProvider(client=client).generate(*documents())
    assert error.value.code=='PROVIDER_AUTH_FAILED'
    assert 'sensitive-upstream-value' not in str(error.value)
