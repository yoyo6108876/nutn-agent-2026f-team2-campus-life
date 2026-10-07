import asyncio
import json
import os
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from .contracts import FlowError

ROOT = Path(__file__).resolve().parents[2]


async def read_over_mcp(arguments):
    params = StdioServerParameters(command=sys.executable,
        args=['-m','assignment_checker.week4.mcp_server'], cwd=str(ROOT),
        env={'PYTHONPATH':str(ROOT)})
    try:
        async with asyncio.timeout(10):
            with open(os.devnull, 'w') as errors:
                async with stdio_client(params, errlog=errors) as (read, write):
                    async with ClientSession(read, write) as session:
                        init = await session.initialize()
                        listed = await session.list_tools()
                        if [t.name for t in listed.tools] != ['get_submission_review']:
                            raise FlowError('MCP_TOOLSET_MISMATCH','mcp')
                        called = await session.call_tool('get_submission_review', arguments)
                        if called.isError:
                            raise FlowError('MCP_TOOL_ERROR','mcp')
                        content = json.loads(called.content[0].text)
                        return content, [
                            {'method':'initialize','result':init.model_dump(mode='json',exclude_none=True)},
                            {'method':'tools/list','result':listed.model_dump(mode='json',exclude_none=True)},
                            {'method':'tools/call','params':{'name':'get_submission_review','arguments':arguments},
                             'result':called.model_dump(mode='json',exclude_none=True)}]
    except TimeoutError:
        raise FlowError('READ_TIMEOUT','mcp',True) from None
    except FlowError:
        raise
    except Exception:
        raise FlowError('MCP_UNAVAILABLE','mcp',True) from None
