#!/usr/bin/env python3
"""快速验证 MCP server: 连接 -> list_tools -> 逐个列出工具签名。"""
import asyncio, json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["server.py"],
        cwd="/Users/sunyao/Developer/JianFa/tools/boss-mcp",
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"发现 {len(tools.tools)} 个工具:\n")
            for t in tools.tools:
                desc = (t.description or "").split("\n")[0][:80]
                print(f"  - {t.name}: {desc}")
                schema = t.inputSchema
                props = list((schema or {}).get("properties", {}).keys())
                if props:
                    print(f"    参数: {props}")

asyncio.run(main())
