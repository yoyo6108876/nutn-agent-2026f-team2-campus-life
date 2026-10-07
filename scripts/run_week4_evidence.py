"""Week 4 evidence. --live makes a real OpenAI tool loop with a synthetic confirmed local draft."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile

from assignment_checker.week4.contracts import StartRequest, IDENTITY, FlowError
from assignment_checker.week4.provider import FixtureProvider
from assignment_checker.week4.store import Store
from assignment_checker.week4.workflow import Workflow


def git_revision():
    return subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()


def source_dirty():
    return bool(subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],text=True).strip())


async def collect(output_dir, live=False):
    output_dir.mkdir(parents=True,exist_ok=True)
    cases=[('live-success',None,'draft',True,'completed')] if live else [
        ('read-only',None,'read',None,'completed'),
        ('confirm-and-replay',None,'draft',True,'completed'),
        ('declined',None,'draft',False,'declined'),
        ('invalid-arguments','missing_field','draft',None,'stopped'),
        ('model-forged-confirmation','model_confirmation','draft',None,'stopped'),
        ('report-mismatch','wrong_items','draft',None,'stopped'),
        ('provider-429','provider429','draft',None,'stopped'),
        ('summary-failed-after-write','summary_timeout','draft',True,'written'),
        ('write-response-lost','after_write','draft',True,'written'),
    ]
    summary=[]
    for name,fault,intent,accepted,expected in cases:
        with tempfile.TemporaryDirectory(prefix='week4-validation-') as d:
            provider=None if live else FixtureProvider(None if fault=='after_write' else fault)
            host=Workflow(Store(Path(d)/'state.sqlite3'),provider=provider,fault=fault)
            run=await host.start(StartRequest(**IDENTITY,message='請讀取這份作業的缺漏報告，整理補件與待確認項目；若需寫入，先讓我確認草稿。',intent=intent,mode='live' if live else 'fixture'))
            before={'state':run['state'],'draft_count':host.store.draft_count()}
            if run['state']=='awaiting_confirmation' and accepted is not None:
                run=await host.decide(run['run_id'],accepted)
            count=host.store.draft_count()
            replay=None
            if run['state'] in ('completed','written','declined') and intent=='draft':
                repeated=await host.decide(run['run_id'],True)
                replay={'state':repeated['state'],'replayed':repeated.get('replayed',False),
                        'draft_count':host.store.draft_count(),
                        'same_receipt':repeated.get('receipt')==run.get('receipt')}
            expected_count=1 if expected in ('completed','written') and intent=='draft' else 0
            passed=run['state']==expected and count==expected_count
            if live:passed=passed and run['live_status']=='LIVE_PASS'
            if replay:passed=passed and replay['same_receipt'] and replay['draft_count']==count
            record={'case':name,'captured_at':datetime.now(timezone.utc).isoformat(),
                    'tested_commit_sha':git_revision(),'tracked_files_dirty':source_dirty(),
                    'data_source':'synthetic only; no real student records',
                    'provider':'openai' if live else 'authored_fixture',
                    'failure_injection':fault,'approval_source':'automated sandbox test decision, not an external user approval',
                    'before_decision':before,'draft_count':count,'replay':replay,
                    'run':run,'matches_expected':passed,
                    'gemini_requirement':'NOT_RUN: user explicitly selected project OpenAI provider'}
            (output_dir/(name+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            summary.append({'case':name,'matches_expected':passed,'run_id':run['run_id'],
                            'state':run['state'],'live_status':run['live_status'],'draft_count':count})
            print(name,run['state'],run['live_status'],'expected='+str(passed),flush=True)
    (output_dir/'index.json').write_text(json.dumps({'tested_commit_sha':git_revision(),
        'tracked_files_dirty':source_dirty(),'cases':summary,'all_passed':all(r['matches_expected'] for r in summary)},ensure_ascii=False,indent=2)+'\n')
    return 0 if all(r['matches_expected'] for r in summary) else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--output-dir',type=Path,default=Path('tmp/week4-evidence'))
    args=parser.parse_args()
    return asyncio.run(collect(args.output_dir,args.live))


if __name__=='__main__':raise SystemExit(main())
