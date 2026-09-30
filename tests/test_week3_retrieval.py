from copy import deepcopy
from datetime import date
import json
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from assignment_checker.api import create_app
from assignment_checker.provider import DEFAULT_MODEL
from assignment_checker.retrieval import (
    GeneratedAnswer, QueryRequest, RetrievalProvider, digest, generator_input,
    literal_baseline, load_json, prepare, run_query, validate_answer,
)
from assignment_checker.service import CheckFailure
from scripts.run_week3_evidence import evaluate, failures


@pytest.fixture(autouse=True)
def fixed_policy_date(monkeypatch):
    # Keep unit fixtures reproducible; the actual service uses the current date.
    class PolicyDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 9, 30)
    monkeypatch.setattr('assignment_checker.retrieval.date', PolicyDate)


@pytest.mark.parametrize('qid,status,calls', [('Q1','answered',0),('Q2','no_answer',0),
                                            ('Q3','coverage_failure',0),('B1','answered',0)])
def test_fixed_queries(qid,status,calls):
    r = run_query(QueryRequest(query_id=qid))
    assert r['status'] == status
    assert r['provider_attempts'] == calls
    assert digest(r['trace']['selected_evidence']) == r['trace']['evidence_hash']
    if status != 'answered':
        assert r['answer'] == []
        assert r['student_notice'] is None


def test_same_question_with_smaller_k_refuses_instead_of_declaring_missing():
    small, tsmall = prepare('Q1', 2)
    full, tfull = prepare('Q1', 6)
    assert tsmall['gate'] == 'coverage_failure'
    assert tfull['gate'] == 'ready'
    assert small.selected_evidence == full.selected_evidence[:2]
    assert tsmall['missing_coverage']


def test_restoring_coverage_on_q3_uses_same_fixture_as_q1():
    result = run_query(QueryRequest(query_id='Q3', top_k=6))
    assert result['status'] == 'answered'
    assert result['answer'] == run_query(QueryRequest(query_id='Q1'))['answer']


def test_ranking_and_hash_are_reproducible():
    assert prepare('B1') == prepare('B1')
    _, trace = prepare('B1')
    assert [r['chunk_id'] for r in trace['ranked_candidates'][:2]] == ['B-hours', 'B-shoes']
    assert {'chunk_id':'B-old','reason':'withdrawn'} in trace['excluded']


@pytest.mark.parametrize('field,value,reason', [('withdrawn',True,'withdrawn'),
    ('permission',False,'permission_denied'),('pii','contains_pii','pii_not_approved'),
    ('valid_until','2026-09-29','outside_validity_window'),
    ('updated_at','2026-10-01','outside_validity_window')])
def test_source_policy_enforced_before_retrieval(field,value,reason):
    dataset=load_json('dataset.json')
    next(s for s in dataset['sources'] if s['id']=='court-hours-demo')[field]=value
    bundle,trace=prepare('B1', dataset=dataset,today=date(2026,9,30))
    assert trace['gate']=='coverage_failure'
    assert 'B-hours' not in [c['id'] for c in bundle.selected_evidence]
    assert {'chunk_id':'B-hours','reason':reason} in trace['excluded']


def test_all_expired_sources_yield_no_answer():
    _,trace=prepare('B1',today=date(2027,1,1))
    assert trace['gate']=='no_answer'


@pytest.mark.parametrize('mutation', ['unselected','quote','fact','duplicate','value','role','wrong_fact'])
def test_citation_and_coverage_gate(mutation):
    bundle,_=prepare('Q1')
    raw=load_json('generator-fixtures.json')['Q1']
    fact=raw['facts'][0]
    if mutation=='unselected': fact['evidence'][0]['chunk_id']='S99'
    elif mutation=='quote': fact['evidence'][0]['quote']='捏造的原文'
    elif mutation=='fact': raw['facts'].pop()
    elif mutation=='duplicate': raw['facts'].append(deepcopy(fact))
    elif mutation=='value': fact['value']='approved'
    elif mutation=='role': fact['evidence']=fact['evidence'][:1]
    elif mutation=='wrong_fact': fact['evidence'][0]=raw['facts'][1]['evidence'][0]
    with pytest.raises(CheckFailure): validate_answer(bundle,raw)


def test_changed_frozen_evidence_rejected():
    bundle,_=prepare('B1')
    bundle.selected_evidence[0]['text']+='changed'
    with pytest.raises(CheckFailure,match='evidence_changed'):
        validate_answer(bundle,load_json('generator-fixtures.json')['B1'])


def test_semantically_wrong_claim_passes_citation_gate_but_fails_oracle():
    observed=failures()['observations'][-1]['evaluation']
    assert observed['citation_gate']=='passed'
    assert observed['unsupported_claims']==1
    assert observed['fact_coverage']=='2/3'
    assert observed['benchmark_pass'] is False


def test_literal_rule_failure_on_paraphrase_negation_and_missing_appendix():
    bundle,_=prepare('Q1')
    baseline=literal_baseline(bundle)
    assert [f.value for f in baseline.facts]==['uncertain','met','met']
    score=evaluate(bundle,baseline,load_json('oracle.json')['Q1']['facts'])
    assert score['fact_coverage']=='0/3'
    assert score['unsupported_claims']==2
    assert score['unnecessary_abstentions']==1


def test_teacher_and_student_notices_agree():
    result=run_query(QueryRequest(query_id='Q1'))
    assert result['student_notice']==result['teacher_notice']=={
        'needs_revision':['failure_case'],'needs_confirmation':['appendix']}


@pytest.mark.parametrize('qid', ['Q2','Q3'])
def test_no_provider_call_for_refused_live_requests(qid):
    provider=Mock()
    with TestClient(create_app(retrieval_provider=provider)) as client:
        r=client.post('/assistant/week3/query',json={'query_id':qid,'mode':'live'})
    assert r.status_code==200
    assert r.json()['provider_attempts']==0
    provider.generate.assert_not_called()


def test_live_adapter_only_sees_frozen_evidence_and_no_gold_labels():
    bundle,_=prepare('Q1')
    answer=GeneratedAnswer.model_validate(load_json('generator-fixtures.json')['Q1'])
    parse=Mock(return_value=SimpleNamespace(model=DEFAULT_MODEL,usage=None,status='completed',output_parsed=answer))
    provider=RetrievalProvider(client=SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    with TestClient(create_app(retrieval_provider=provider)) as client:
        r=client.post('/assistant/week3/query',json={'query_id':'Q1','mode':'live'})
    assert r.status_code==200
    assert r.json()['provider_attempts']==1
    options=parse.call_args.kwargs
    payload=json.loads(options['input'][1]['content'])
    assert payload['selected_evidence']==bundle.selected_evidence
    assert payload['evidence_hash']==bundle.evidence_hash
    assert all('literal_rules' not in f for f in payload['facts'])
    assert 'oracle' not in json.dumps(payload)
    assert options['text_format'] is GeneratedAnswer
    assert options['store'] is False
    assert provider.metadata['prompt_version']=='retrieval-generator-v1'
    parse.assert_called_once()


@pytest.mark.parametrize('body',[{'query_id':'bad'}, {'query_id':'Q1','top_k':0},
    {'query_id':'Q1','top_k':True},{'query_id':'Q1','mode':'other'},{'query_id':'Q1','api_key':'secret'}])
def test_api_rejects_invalid_request_before_provider(body):
    provider=Mock()
    with TestClient(create_app(retrieval_provider=provider)) as client:
        r=client.post('/assistant/week3/query',json=body)
    assert r.status_code==422
    assert 'secret' not in r.text
    provider.generate.assert_not_called()


def test_unselected_citation_returns_safe_http_error():
    raw=load_json('generator-fixtures.json')['B1']
    raw['facts'][0]['evidence'][0]['chunk_id']='B-old'
    provider=SimpleNamespace(generate=lambda _:raw, metadata={})
    with TestClient(create_app(retrieval_provider=provider)) as client:
        r=client.post('/assistant/week3/query',json={'query_id':'B1','mode':'live'})
    assert r.status_code==502
    assert r.json()['error']['code']=='UNGROUNDED_RESPONSE'
