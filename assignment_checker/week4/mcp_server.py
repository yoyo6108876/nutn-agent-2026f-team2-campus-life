"""stdio MCP server; exposes only a read tool, never the draft writer."""
import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ToolAnnotations
from .contracts import ReadArgs, FlowError
from .tools import get_review

server = Server('assignment-review-readonly', version='1.0.0')


@server.list_tools()
async def tools():
    return [Tool(name='get_submission_review', description='讀取合成作業的既有報告；不寫入。',
                 inputSchema=ReadArgs.model_json_schema(),
                 annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                             idempotentHint=True, openWorldHint=False))]


@server.call_tool()
async def call(name, arguments):
    if name != 'get_submission_review':
        raise ValueError('TOOL_NOT_ALLOWED')
    try:
        result, trace = get_review(arguments)
        return [TextContent(type='text', text=json.dumps({'report':result,'rag_trace':trace},ensure_ascii=False))]
    except FlowError as error:
        raise ValueError(error.code) from None


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == '__main__':
    asyncio.run(main())
