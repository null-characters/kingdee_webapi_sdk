"""
金蝶 MCP Agent - 命令行测试客户端

用于快速测试 MCP Server 的工具调用。
运行：
    python3 kingdee_mcp_agent/agent/test_client.py              # 自动跑一遍工具列表与查询
    python3 kingdee_mcp_agent/agent/test_client.py interactive  # 交互式调用

凭证从环境变量读取（KINGDEE_SERVER_URL / KINGDEE_ACCT_ID / KINGDEE_USERNAME / KINGDEE_PASSWORD）。
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp_server"))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _server_params(server_path: Path) -> StdioServerParameters:
    """构造 stdio 连接参数

    - command 用当前解释器，避免环境里没有 `python` 命令
    - env 必须显式传递：MCP SDK 默认只传 PATH/HOME 等白名单变量，
      不传的话 server 子进程读不到 KINGDEE_* 凭证
    """
    return StdioServerParameters(
        command=sys.executable,
        args=[str(server_path)],
        env=dict(os.environ),
    )


async def test_mcp_server():
    """测试 MCP Server 连接和工具调用"""

    # MCP Server 路径
    server_path = Path(__file__).resolve().parent.parent / "mcp_server" / "server.py"

    print(f"连接 MCP Server: {server_path}")

    async with stdio_client(_server_params(server_path)) as (read, write):
        async with ClientSession(read, write) as session:
            # 初始化连接
            await session.initialize()

            # 获取工具列表
            tools = await session.list_tools()
            print(f"\n可用工具 ({len(tools.tools)} 个):")
            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description[:50]}...")

            # 测试调用 search_materials
            print("\n测试调用 search_materials...")
            result = await session.call_tool("search_materials", {"limit": 5})
            print(f"结果: {str(result.content)[:200]}...")

            # 测试调用 query_bill
            print("\n测试调用 query_bill...")
            result = await session.call_tool(
                "query_bill",
                {
                    "form_id": "BD_MATERIAL",
                    "field_keys": "FNumber,FName",
                    "limit": 5
                }
            )
            print(f"结果: {str(result.content)[:200]}...")


async def interactive_test():
    """交互式测试"""

    server_path = Path(__file__).resolve().parent.parent / "mcp_server" / "server.py"

    async with stdio_client(_server_params(server_path)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("可用工具:")
            for i, tool in enumerate(tools.tools, 1):
                print(f"{i}. {tool.name}")

            while True:
                print("\n输入工具名称和参数（格式: tool_name param1=value1 param2=value2）")
                print("或输入 'quit' 退出")

                try:
                    input_str = input("> ").strip()
                    if input_str == "quit":
                        break

                    parts = input_str.split()
                    tool_name = parts[0]

                    # 解析参数
                    params = {}
                    for part in parts[1:]:
                        if "=" in part:
                            key, value = part.split("=", 1)
                            # 尝试解析 JSON
                            try:
                                params[key] = json.loads(value)
                            except Exception:
                                params[key] = value

                    print(f"调用: {tool_name}({params})")
                    result = await session.call_tool(tool_name, params)
                    print(f"结果: {json.dumps(result.content, indent=2, ensure_ascii=False, default=str)[:1000]}")

                except Exception as e:
                    print(f"错误: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("金蝶 MCP Agent 测试客户端")
    print("=" * 60)

    if len(sys.argv) > 1 and sys.argv[1] == "interactive":
        asyncio.run(interactive_test())
    else:
        asyncio.run(test_mcp_server())
