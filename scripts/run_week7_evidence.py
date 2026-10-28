"""Week 7 same-project memory evidence. --live spends OpenAI quota; never claims Gemini."""
import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter
from unittest.mock import patch

from assignment_checker.models import ModelReport
from assignment_checker.provider import OpenAIProvider
from assignment_checker.retrieval import load_json, prepare
from assignment_checker.service import ground_report, CheckFailure
from assignment_checker.week4.contracts import IDENTITY, FlowError, StartRequest
from assignment_checker.week4.provider import FixtureProvider
from assignment_checker.week4.store import Store
from assignment_checker.week4.tools import get_review
from assignment_checker.week4.workflow import Workflow
from assignment_checker.week7.memory import SessionMemory
from assignment_checker.week7.routes import ReviewInput
from assignment_checker.week7.workflow import SessionWorkflow


def provenance():
    return {'tested_commit_sha': subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'tracked_files_dirty': bool(subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],text=True).strip()),
            'captured_at': datetime.now(timezone.utc).isoformat(),
            'provider': 'openai', 'gemini_status': 'LIVE_NOT_RUN',
            'gemini_reason': 'User explicitly selected the existing GPT API; course ADC/Gemini requirement remains unmet',
            'data_source': 'synthetic_only', 'approval_source':'automated sandbox confirmation, not teacher approval'}


def req(live=False,intent='read'):
    return StartRequest(**IDENTITY,message='請查看這份作業的缺漏，整理需補件與待確認項目；建立草稿前先等我確認。',
                        intent=intent,mode='live' if live else 'fixture')


def facts(run):
    return {key:(run.get('summary') or {}).get(key) for key in
            ('submission_id','submission_version','needs_revision','needs_confirmation','status')}


def metrics(runs):
    metadata=[m for run in runs for m in run.get('provider_metadata',[])]
    actual=[m for m in metadata if m.get('llm_actually_called')]
    return {'actual_llm_responses':len(actual),
            'tokens':{key:sum(m.get('usage',{}).get(key,0) for m in actual) for key in
                      ('input_tokens','output_tokens','total_tokens')}}


async def collect(directory,live=False):
    directory.mkdir(parents=True,exist_ok=True)
    meta=provenance(); results=[]

    def save(case,expected,actual,runs,**extra):
        passed=actual==expected
        record={**meta,'case':case,'mode':'live' if live else 'fixture','expected':expected,'actual':actual,
                'matches_expected':passed,'runs':runs,'metrics':metrics(runs),**extra}
        (directory/(case+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
        results.append({'case':case,'matches_expected':passed,'run_ids':[r['run_id'] for r in runs]})
        print(case,'PASS' if passed else 'FAIL',flush=True)

    with tempfile.TemporaryDirectory(prefix='week7-evidence-') as temporary:
        root=Path(temporary); memory=SessionMemory(root/'memory.sqlite3'); store=Store(root/'domain.sqlite3')
        session=memory.new_session('student-a')
        candidate=SessionWorkflow(store,memory,'student-a',session['session_id'])
        baseline=Workflow(Store(root/'baseline.sqlite3'))
        begin=perf_counter(); before=await baseline.start(req(live,'draft')); base_pending=deepcopy(before)
        if before['state']=='awaiting_confirmation': before=await baseline.decide(before['run_id'],True)
        base_seconds=perf_counter()-begin
        begin=perf_counter(); pending=await candidate.start(req(live,'draft')); pending_copy=deepcopy(pending)
        before_count=store.draft_count()
        normal=await candidate.decide(pending['run_id'],True) if pending['state']=='awaiting_confirmation' else pending
        candidate_seconds=perf_counter()-begin
        replay=await candidate.decide(normal['run_id'],True)
        good='LIVE_PASS' if live else 'LIVE_NOT_RUN'
        save('C01-normal-comparison',{'baseline_state':'completed','candidate_state':'completed','facts_equal':True,
             'baseline_live':good,'candidate_live':good},
             {'baseline_state':before['state'],'candidate_state':normal['state'],'facts_equal':facts(before)==facts(normal),
              'baseline_live':before['live_status'],'candidate_live':normal['live_status']},[before,normal],
             baseline_seconds=base_seconds,candidate_seconds=candidate_seconds,
             baseline_pending=base_pending,candidate_pending=pending_copy)
        save('W01-W02-confirmation-replay',{'before_confirmation':0,'after_confirmation':1,'after_replay':1,'same_receipt':True},
             {'before_confirmation':before_count,'after_confirmation':store.draft_count(),'after_replay':store.draft_count(),
              'same_receipt':bool(normal.get('receipt')) and normal.get('receipt')==replay.get('receipt')},[replay])
        # Follow-up actually consumes the bounded prior summary in this same session.
        follow=await candidate.start(req(live))
        save('C03-same-session',{'included':True,'prior_run':normal['run_id'],'state':'completed','live_status':good},
             {'included':follow.get('memory_trace',{}).get('included'),
              'prior_run':(json.loads(follow['history'][0]['content']).get('session_context',{}).get('memory') or {}).get('run_id') if follow.get('history') else None,
              'state':follow['state'],'live_status':follow['live_status']},[follow])
        other=memory.new_session('student-b'); other_code=None
        try: memory.authorize_run(normal['run_id'],other['session_id'],'student-b')
        except FlowError as error: other_code=error.code
        save('C02-cross-user',{'read_code':'RUN_NOT_FOUND','other_context':None},
             {'read_code':other_code,'other_context':memory.context(other['session_id'],'student-b','v1')['memory']},[])
        replacement=memory.clear_session(session['session_id'],'student-a')
        active=SessionWorkflow(store,memory,'student-a',replacement['session_id'])
        cleared=await active.start(req(live))
        current_history=json.loads(cleared['history'][0]['content']) if cleared.get('history') else {}
        save('C04-clear-context',{'old_inactive':True,'included':False,'memory':None,'old_id_in_model_input':False,'state':'completed','live_status':good},
             {'old_inactive':not memory.get_session(session['session_id'],'student-a')['active'],
              'included':cleared.get('memory_trace',{}).get('included'),
              'memory':current_history.get('session_context',{}).get('memory'),
              'old_id_in_model_input':normal['run_id'] in json.dumps(current_history) or follow['run_id'] in json.dumps(current_history),
              'state':cleared['state'],'live_status':cleared['live_status']},[cleared])
        if not live:
            # Same real retrieval/quote gate over a versioned synthetic copy, with a marked in-process reader.
            dataset=load_json('dataset.json'); dataset['version']+='-week7-v2'
            for source in dataset['sources']:
                source['version']=str(source['version'])+'-v2'
            teacher=next(chunk for chunk in dataset['chunks'] if chunk['id']=='T2')
            teacher['text']+=' 新版補充：失敗原因必須說明造成錯誤的成因。'
            async def updated_reader(args):
                report,trace=get_review(args)
                return {'report':report,'rag_trace':trace},[{'transport':'in-process versioned source fixture, not MCP'}]
            updated=SessionWorkflow(store,memory,'student-a',replacement['session_id'],reader=updated_reader)
            with patch('assignment_checker.week4.tools.prepare',lambda query:prepare(query,dataset=dataset)):
                newer=await updated.start(req())
            save('C06-source-update',{'excluded_old':True,'reason':'source_version_changed','new_hash':True,'state':'completed'},
                 {'excluded_old':newer.get('memory_trace',{}).get('included') is False,
                  'reason':newer.get('memory_trace',{}).get('reason'),
                  'new_hash':newer.get('report',{}).get('evidence_hash')!=cleared.get('report',{}).get('evidence_hash'),
                  'state':newer['state']},[newer],failure_injection='versioned synthetic dataset copy; production files unchanged')
            for name,fault,code in [('C07-invalid-arguments','missing_field','INVALID_TOOL_ARGUMENTS'),
                                    ('C08-provider-failure','provider429','PROVIDER_429')]:
                bad=SessionWorkflow(store,memory,'student-a',replacement['session_id'],provider=FixtureProvider(fault))
                failed=await bad.start(req())
                save(name,{'state':'stopped','code':code,'new_write':False},
                     {'state':failed['state'],'code':failed.get('error',{}).get('code'),'new_write':bool(failed.get('receipt'))},
                     [failed],failure_injection=fault)

    if live:
        payload=ReviewInput(teacher_text='作業應說明目標使用者與使用情境，並提供一個失敗案例，包含輸入、實際結果與失敗原因。',
                           student_text='誰會用：剛交完報告、擔心漏寫內容的南大同學，希望先取得補件提醒。失敗案例：輸入只有封面的報告，系統卻顯示全部完成。',
                           requirements=['描述目標使用者及使用情境。','提供失敗案例，包含輸入、實際結果與失敗原因。'],requirements_confirmed=True)
        provider=OpenAIProvider(); request=payload.request()
        try:
            report=ground_report(request,provider.generate(request)); labels={c.requirement_id:c.status for c in report.checks}
            record={**meta,'case':'semantic-review','request':request.model_dump(),'report':report.model_dump(),
                    'provider_metadata':provider.metadata,'live_status':'LIVE_PASS',
                    'expected':{'R1':'met','R2':'partial'},'actual':labels,'matches_expected':labels=={'R1':'met','R2':'partial'}}
        except CheckFailure as error:
            record={**meta,'case':'semantic-review','request':request.model_dump(),'live_status':'LIVE_NOT_RUN' if error.code=='MISSING_API_KEY' else 'LIVE_FAIL',
                    'error':error.body(),'matches_expected':False}
        (directory/'semantic-review.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
        results.append({'case':'semantic-review','matches_expected':record['matches_expected']})
        print('semantic-review',record['live_status'],flush=True)
    index={**meta,'mode':'live' if live else 'fixture','cases':results,'all_passed':all(r['matches_expected'] for r in results)}
    (directory/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
    return 0 if index['all_passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--output-dir',type=Path,default=Path('tmp/week7-evidence'))
    args=parser.parse_args()
    raise SystemExit(asyncio.run(collect(args.output_dir,args.live)))
