import json
from pathlib import Path
from time import perf_counter
from openai import AsyncOpenAI, AuthenticationError, RateLimitError, APITimeoutError, APIConnectionError, APIStatusError
from ..provider import local_settings
from ..service import CheckFailure
from .contracts import FlowError, TOOLS, Summary

PROMPT = Path(__file__).with_name('prompt.txt').read_text(encoding='utf-8')
PROMPT_VERSION = 'assignment-tools-v1'


class ToolProvider:
    async def next(self, history, phase):
        try:
            key, model = local_settings()
        except CheckFailure:
            raise FlowError('MISSING_API_KEY','provider') from None
        start=perf_counter()
        options={'model':model, 'input':history, 'instructions':PROMPT, 'store':False,
                 'temperature':0, 'max_output_tokens':1800}
        if phase=='summary':
            options['text']={'format':{'type':'json_schema','name':'review_summary',
                'schema':Summary.model_json_schema(),'strict':True}}
        else:
            options.update(tools=TOOLS,tool_choice='auto',parallel_tool_calls=False)
        try:
            async with AsyncOpenAI(api_key=key,base_url='https://api.openai.com/v1',max_retries=0,timeout=30) as client:
                response=await client.responses.create(**options)
        except AuthenticationError:
            raise FlowError('PROVIDER_AUTH_FAILED','provider') from None
        except RateLimitError as error:
            raise FlowError('PROVIDER_QUOTA' if error.code=='insufficient_quota' else 'PROVIDER_429',
                            'provider',error.code!='insufficient_quota') from None
        except (APITimeoutError,APIConnectionError):
            raise FlowError('PROVIDER_TIMEOUT_OR_CONNECTION','provider',True) from None
        except APIStatusError as error:
            raise FlowError('PROVIDER_HTTP_ERROR','provider',error.status_code>=500) from None
        if response.status!='completed':
            raise FlowError('PROVIDER_INCOMPLETE','provider')
        return {'output':[item.model_dump(mode='json',exclude_none=True) for item in response.output],
                'text':response.output_text,
                'metadata':{'provider':'openai','model':response.model,'response_id':response.id,
                    'prompt_version':PROMPT_VERSION,'latency_seconds':round(perf_counter()-start,3),
                    'usage':response.usage.model_dump() if response.usage else '未取得',
                    'api_version':'未取得','llm_actually_called':True}}


class FixtureProvider:
    """Authored deterministic tool turns, never reported as live or Gemini."""
    def __init__(self,fault=None):
        self.fault=fault

    async def next(self, history, phase):
        if self.fault=='provider429':
            raise FlowError('PROVIDER_429','provider',True)
        context=json.loads(history[0]['content'])
        request=context['request']
        identity={k:request[k] for k in ('assignment_id','submission_id','submission_version')}
        outputs=[json.loads(item['output']) for item in history if item.get('type')=='function_call_output']
        metadata={'provider':'authored_fixture','model':'未取得','response_id':'未取得',
                  'prompt_version':PROMPT_VERSION,'usage':'未取得','llm_actually_called':False}
        if phase=='summary':
            if self.fault=='summary_timeout':
                raise FlowError('PROVIDER_TIMEOUT_OR_CONNECTION','provider',True)
            report=outputs[0]
            receipt=outputs[-1] if outputs[-1].get('draft_id') else None
            summary={k:report[k] for k in ('submission_id','submission_version','needs_revision','needs_confirmation')}
            summary.update(draft_id=receipt['draft_id'] if receipt else None,
                           status='draft_created' if receipt else 'reviewed')
            if self.fault=='wrong_summary':summary['needs_revision']=[]
            return {'output':[], 'text':json.dumps(summary), 'metadata':metadata}
        name='get_submission_review' if not outputs else 'create_revision_draft'
        args=dict(identity)
        if outputs:
            args['requirement_ids']=outputs[0]['needs_revision']+outputs[0]['needs_confirmation']
        if self.fault=='missing_field':args.pop('submission_version')
        if self.fault=='wrong_version':args['submission_version']=2
        if self.fault=='model_confirmation' and outputs:args['confirmed']=True
        if self.fault=='wrong_items' and outputs:args['requirement_ids']=['target_user']
        call={'type':'function_call','name':name,'arguments':json.dumps(args),'call_id':f'fixture-call-{len(outputs)+1}'}
        return {'output':[call], 'text':'', 'metadata':metadata}
