import asyncio
from datetime import datetime, timezone
import json
import re
import uuid
from pydantic import ValidationError
from .contracts import ReadArgs, DraftArgs, StartRequest, Summary, FlowError, identity
from .tools import get_review
from .mcp_client import read_over_mcp
from .provider import ToolProvider, FixtureProvider
from .store import event, now


class Workflow:
    def __init__(self, store, provider=None, reader=read_over_mcp, fault=None):
        self.store,self.provider,self.reader,self.fault=store,provider,reader,fault

    def fail(self,run,error):
        run['error']=error.body()
        if run['state']!='written':run['state']='stopped'
        run['live_status']='LIVE_NOT_RUN' if run['request']['mode']!='live' or not run['model_rounds'] or error.code=='MISSING_API_KEY' else 'LIVE_FAIL'
        event(run,'stopped',**error.body(),executed=bool(run.get('receipt')))
        self.store.save(run)
        return run

    async def model(self,run,phase):
        if run['model_rounds']>=3:
            raise FlowError('MODEL_ROUND_LIMIT','budget')
        run['model_rounds']+=1
        if run['request']['mode']=='live':run['live_status']='LIVE_IN_PROGRESS'
        provider=self.provider or (ToolProvider() if run['request']['mode']=='live' else FixtureProvider())
        for attempt in range(1,3):
            event(run,'model_attempt',phase=phase,attempt=attempt)
            try:
                async with asyncio.timeout(32):
                    response=await provider.next(run['history'],phase)
                run['provider_metadata'].append(response['metadata'])
                event(run,'model_output',phase=phase,output=response['output'],text=response['text'])
                run['history'].extend(response['output'])
                return response
            except TimeoutError:
                error=FlowError('PROVIDER_TIMEOUT','provider',True)
            except FlowError as caught:
                error=caught
            event(run,'model_error',phase=phase,attempt=attempt,**error.body())
            if not error.retryable or attempt==2:raise error
            await asyncio.sleep(0.2)

    def call(self,run,response,expected):
        calls=[item for item in response['output'] if item.get('type')=='function_call']
        if len(calls)!=1 or calls[0]['name']!=expected:
            raise FlowError('UNEXPECTED_TOOL_SEQUENCE','validation')
        call=calls[0]
        try:
            args=(ReadArgs if expected=='get_submission_review' else DraftArgs).model_validate_json(call['arguments'])
        except (ValidationError,ValueError):
            raise FlowError('INVALID_TOOL_ARGUMENTS','validation') from None
        if identity(args.model_dump())!=identity(run['request']):
            raise FlowError('REQUEST_MISMATCH','validation')
        if expected=='create_revision_draft':
            expected_ids=run['report']['needs_revision']+run['report']['needs_confirmation']
            if sorted(args.requirement_ids)!=sorted(expected_ids):
                raise FlowError('REPORT_MISMATCH','validation')
        event(run,'tool_validated',name=expected,arguments=args.model_dump(),executed=False)
        return call,args.model_dump()

    def send_result(self,run,call,result):
        output={'type':'function_call_output','call_id':call['call_id'],'output':json.dumps(result,ensure_ascii=False)}
        run['history'].append(output)
        event(run,'tool_result_returned',call_id=call['call_id'],tool=call['name'],result=result)

    async def summary(self,run):
        response=await self.model(run,'summary')
        try:
            summary=Summary.model_validate_json(response['text'])
        except (ValidationError,ValueError):
            raise FlowError('INVALID_SUMMARY','summary') from None
        expected={k:run['report'][k] for k in ('submission_id','submission_version','needs_revision','needs_confirmation')}
        expected.update(draft_id=run.get('receipt',{}).get('draft_id'),
                        status='draft_created' if run.get('receipt') else 'reviewed')
        actual=summary.model_dump()
        for key in ('needs_revision','needs_confirmation'):
            actual[key]=sorted(actual[key]);expected[key]=sorted(expected[key])
        if actual!=expected:raise FlowError('SUMMARY_MISMATCH','summary')
        run['summary']=summary.model_dump()
        event(run,'summary_verified',summary=run['summary'])
        run['state']='completed'
        run['live_status']='LIVE_PASS' if run['request']['mode']=='live' else 'LIVE_NOT_RUN'
        self.store.save(run)
        return run

    async def start(self,request:StartRequest):
        run={'run_id':'run-'+uuid.uuid4().hex,'created_at':now(),'state':'starting',
             'request':request.model_dump(),'audit':[],'history':[], 'model_rounds':0,
             'provider_metadata':[], 'live_status':'LIVE_NOT_RUN','summary':None}
        self.store.save(run)
        try:
            # The UI target is verified independently of the model proposal.
            for name,prefix in [('submission_id','SUB'),('assignment_id','HW')]:
                explicit=re.findall(r'\b'+prefix+r'-[A-Z0-9-]+\b',request.message)
                if any(value!=getattr(request,name) for value in explicit):
                    raise FlowError('MESSAGE_TARGET_MISMATCH','request')
            preflight,trace=get_review(identity(run['request']))
            run['rag_trace']=trace
            event(run,'readiness_passed',evidence_hash=preflight['evidence_hash'],gate=trace['gate'])
            run['history']=[{'role':'user','content':json.dumps({'request':run['request']},ensure_ascii=False)}]
            response=await self.model(run,'proposal')
            read_call,args=self.call(run,response,'get_submission_review')
            for attempt in range(1,3):
                try:
                    content,protocol=await self.reader(args)
                    if content['report']!=preflight:
                        raise FlowError('READ_RESULT_MISMATCH','read_tool')
                    run['mcp_trace']=protocol
                    run['report']=content['report']
                    event(run,'read_executed',attempt=attempt,executed=True,source=run['report']['source'])
                    break
                except FlowError as error:
                    event(run,'read_error',attempt=attempt,**error.body())
                    if not error.retryable or attempt==2:raise
                    await asyncio.sleep(0.2)
            self.send_result(run,read_call,run['report'])
            if request.intent=='read':return await self.summary(run)
            response=await self.model(run,'proposal')
            write_call,args=self.call(run,response,'create_revision_draft')
            run.update(state='awaiting_confirmation',proposal=args,pending_call=write_call)
            run['proposal_created_at']=now()
            event(run,'awaiting_confirmation',executed=False,report_hash=run['report']['report_hash'])
            self.store.save(run)
            return run
        except FlowError as error:
            return self.fail(run,error)

    async def decide(self,run_id,accepted):
        run=self.store.get(run_id)
        if run['state']!='awaiting_confirmation':
            return {**run,'replayed':True}
        try:
            if accepted:
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(run['proposal_created_at'])).total_seconds()
                if age>600:raise FlowError('PROPOSAL_EXPIRED','readiness')
                current,_=get_review(identity(run['request']))
                current_hash=current['report_hash']
            else:current_hash=None
            run,created=self.store.decide(run_id,accepted,current_hash)
            if not created:return run
            # The SQLite commit above already contains receipt + audit. Never repeat a write after this point.
            if self.fault=='after_write':
                recovered=self.store.get(run_id)
                event(recovered,'write_result_reconciled',request_id=run_id,draft_id=recovered['receipt']['draft_id'])
                return self.fail(recovered,FlowError('INJECTED_WRITE_RESPONSE_LOST','write_transport'))
            self.send_result(run,run['pending_call'],run['receipt'])
            self.store.save(run)
            return await self.summary(run)
        except FlowError as error:
            return self.fail(run,error)
