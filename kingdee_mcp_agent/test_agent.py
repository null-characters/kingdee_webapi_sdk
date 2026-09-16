#!/usr/bin/env python
"""
快速测试 Agent - 单次查询模式
"""

import asyncio
import sys
import json
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "agent"))
sys.path.insert(0, str(PROJECT_ROOT / "config"))

# 直接导入 agent 模块（避免与内置 agent 冲突）
import importlib.util
spec = importlib.util.spec_from_file_location("kingdee_agent", PROJECT_ROOT / "agent" / "agent.py")
kingdee_agent_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kingdee_agent_module)
KingdeeAgent = kingdee_agent_module.KingdeeAgent


async def test_agent():
    """测试 Agent 基本功能"""
    
    print("=" * 60)
    print("金蝶 MCP Agent 快速测试")
    print("=" * 60)
    
    agent = KingdeeAgent()
    
    try:
        # 连接 MCP Server
        print("\n[1] 连接 MCP Server...")
        await agent.connect_mcp()
        print(f"    ✅ 连接成功，加载 {len(agent.tools)} 个工具")
        
        # 测试 1: 查询物料
        print("\n[2] 测试查询物料...")
        print('    问题: "帮我查询前3个物料"')
        response = await agent.chat("帮我查询前3个物料")
        print(f"    回答: {response[:500]}")
        
        # 清空历史
        agent.clear_history()
        
        # 测试 2: 查询客户
        print("\n[3] 测试查询客户...")
        print('    问题: "查询客户列表"')
        response = await agent.chat("查询客户列表，返回3条")
        print(f"    回答: {response[:500]}")
        
        print("\n" + "=" * 60)
        print("✅ Agent 测试完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await agent.disconnect()


if __name__ == "__main__":
    asyncio.run(test_agent())