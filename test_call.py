#!/usr/bin/env python3
"""端到端测试：连接 server -> 调用指定工具。用法: test_call.py <tool_name> [json_args]"""
import asyncio, json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TOOL = sys.argv[1] if len(sys.argv) > 1 else "boss_login_status"
ARGS = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}

async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["server.py"],
        cwd="/Users/sunyao/Developer/JianFa/tools/boss-mcp",
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(f">>> calling {TOOL} {json.dumps(ARGS, ensure_ascii=False)}")
            result = await session.call_tool(TOOL, ARGS)
            for item in result.content:
                print(item.text[:2000])
            if result.isError:
                print("!!! TOOL ERROR")

asyncio.run(main())
