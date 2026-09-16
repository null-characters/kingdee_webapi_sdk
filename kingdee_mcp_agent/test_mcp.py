#!/usr/bin/env python
"""
简单测试脚本：验证 MCP Server 工具注册是否正确

运行：python3 kingdee_mcp_agent/test_mcp.py
凭证从环境变量读取（KINGDEE_SERVER_URL / KINGDEE_ACCT_ID / KINGDEE_USERNAME / KINGDEE_PASSWORD）。
"""

import sys
import asyncio
import os
from pathlib import Path

# 添加仓库根目录（kingdee_mcp_agent 的上一级），便于 server.py 导入 kingdee_sdk
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_tools():
    """测试 MCP Server 的工具列表"""

    server_path = Path(__file__).resolve().parent / "mcp_server" / "server.py"

    print(f"启动 MCP Server: {server_path}")

    server_params = StdioServerParameters(
        # 用当前解释器，避免环境里没有 `python` 命令导致启动失败
        command=sys.executable,
        args=[str(server_path)],
        # 必须显式传递环境变量：MCP SDK 默认只传 PATH/HOME 等白名单变量，
        # 不传的话 server 子进程读不到 KINGDEE_* 凭证
        env=dict(os.environ),
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # 获取工具列表
                tools = await session.list_tools()

                print(f"\n✅ MCP Server 连接成功！")
                print(f"\n已注册 {len(tools.tools)} 个工具：\n")

                for i, tool in enumerate(tools.tools, 1):
                    print(f"{i:2}. {tool.name}")
                    print(f"    {tool.description[:60]}...")
                    print()

                # 测试调用一个工具（未配置凭证时会失败，属预期）
                print("=" * 50)
                print("测试调用 query_bill 工具...")
                try:
                    result = await session.call_tool(
                        "query_bill",
                        {
                            "form_id": "BD_MATERIAL",
                            "field_keys": "FNumber,FName",
                            "limit": 5
                        }
                    )
                    print(f"结果: {result}")
                except Exception as e:
                    print(f"调用失败（若未设置环境变量凭证则属预期）: {e}")

    except Exception as e:
        print(f"❌ 连接失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_tools())
