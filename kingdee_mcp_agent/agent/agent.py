"""
金蝶 MCP Agent - 主 Agent 实现

使用 DeepSeek/OpenAI API，通过 MCP 协议调用金蝶工具。
"""

import asyncio
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
import sys

# 添加配置路径
sys.path.insert(0, str(Path(__file__).parent.parent / "config"))

from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from settings import AGENT_CONFIG, MCP_CONFIG

# 配置日志
logging.basicConfig(level=logging.INFO if not AGENT_CONFIG["debug"] else logging.DEBUG)
logger = logging.getLogger(__name__)


class KingdeeAgent:
    """金蝶 MCP Agent"""
    
    def __init__(self):
        self.llm_provider = AGENT_CONFIG["llm_provider"]
        self.model_name = AGENT_CONFIG["model_name"]
        self.max_tool_calls = AGENT_CONFIG["max_tool_calls"]
        
        # 初始化 LLM 客户端
        if self.llm_provider == "deepseek":
            self.client = OpenAI(
                api_key=AGENT_CONFIG["deepseek_api_key"],
                base_url=AGENT_CONFIG["deepseek_base_url"]
            )
        elif self.llm_provider == "openai":
            self.client = OpenAI(
                api_key=AGENT_CONFIG["openai_api_key"]
            )
        elif self.llm_provider == "glm":
            # 腾讯云 GLM 模型（OpenAI 兼容 API）
            self.client = OpenAI(
                api_key=AGENT_CONFIG["deepseek_api_key"],
                base_url=AGENT_CONFIG["deepseek_base_url"]
            )
        else:
            raise ValueError(f"不支持的 LLM 提供商: {self.llm_provider}")
        
        self.mcp_session: Optional[ClientSession] = None
        self.tools: List[Dict] = []
        self.conversation_history: List[Dict] = []
    
    async def connect_mcp(self):
        """连接 MCP Server"""
        server_path = Path(__file__).parent.parent / "mcp_server" / "server.py"
        
        server_params = StdioServerParameters(
            command="python",
            args=[str(server_path)],
            env=None
        )
        
        self._stdio_context = stdio_client(server_params)
        read, write = await self._stdio_context.__aenter__()
        
        self._session_context = ClientSession(read, write)
        self.mcp_session = await self._session_context.__aenter__()
        
        await self.mcp_session.initialize()
        
        # 获取工具列表并转换为 OpenAI 格式
        tools_result = await self.mcp_session.list_tools()
        self.tools = self._convert_tools(tools_result.tools)
        
        logger.info(f"连接 MCP Server 成功，加载 {len(self.tools)} 个工具")
    
    async def disconnect(self):
        """断开连接"""
        if self._session_context:
            await self._session_context.__aexit__(None, None, None)
        if self._stdio_context:
            await self._stdio_context.__aexit__(None, None, None)
    
    def _convert_tools(self, mcp_tools) -> List[Dict]:
        """将 MCP 工具转换为 OpenAI 格式"""
        openai_tools = []
        for tool in mcp_tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                }
            })
        return openai_tools
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return """你是金蝶云星空 ERP 系统的智能助手。

你的职责是帮助用户查询和操作金蝶系统中的数据，包括：
- 物料管理：查询、创建物料
- BOM 管理：查询和创建 BOM 结构
- 单据操作：查询、提交、审核、删除单据
- 变更管理：查看和审批工程变更单

工作流程：
1. 理解用户的自然语言需求
2. 调用相应的工具获取数据或执行操作
3. 将结果以清晰、友好的方式呈现给用户

注意事项：
- 涉及修改、删除、审核操作时，先确认用户意图
- 返回的数据要整理成易读的格式
- 如果工具调用失败，向用户解释原因并建议解决方案

常用表单 ID：
- BD_MATERIAL: 物料
- BD_CUSTOMER: 客户
- BD_SUPPLIER: 供应商
- SAL_SaleOrder: 销售订单
- PUR_PurchaseOrder: 采购订单
- ENG_BOM: BOM
- ENG_ECO: 工程变更单"""
    
    async def chat(self, user_message: str) -> str:
        """处理用户消息"""
        # 添加用户消息到历史
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # 调用 LLM
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": self._build_system_prompt()},
                *self.conversation_history
            ],
            tools=self.tools,
            tool_choice="auto"
        )
        
        assistant_message = response.choices[0].message
        
        # 处理工具调用
        tool_calls_count = 0
        while assistant_message.tool_calls and tool_calls_count < self.max_tool_calls:
            # 添加助手消息到历史
            self.conversation_history.append(assistant_message.to_dict())
            
            # 执行工具调用
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                
                logger.info(f"调用工具: {tool_name}({tool_args})")
                
                try:
                    # 调用 MCP 工具
                    result = await self.mcp_session.call_tool(tool_name, tool_args)
                    
                    # 提取结果内容
                    if hasattr(result, 'content'):
                        if isinstance(result.content, list):
                            tool_result = "\n".join([
                                c.text if hasattr(c, 'text') else str(c) 
                                for c in result.content
                            ])
                        else:
                            tool_result = str(result.content)
                    else:
                        tool_result = str(result)
                    
                    logger.info(f"工具结果: {tool_result[:200]}...")
                    
                except Exception as e:
                    tool_result = f"工具调用失败: {str(e)}"
                    logger.error(f"工具调用失败: {e}")
                
                # 添加工具结果到历史
                self.conversation_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result
                })
            
            # 再次调用 LLM 获取最终回复
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self._build_system_prompt()},
                    *self.conversation_history
                ],
                tools=self.tools,
                tool_choice="auto"
            )
            
            assistant_message = response.choices[0].message
            tool_calls_count += 1
        
        # 添加最终回复到历史
        self.conversation_history.append({
            "role": "assistant",
            "content": assistant_message.content or ""
        })
        
        return assistant_message.content or "抱歉，我无法处理这个请求。"
    
    def clear_history(self):
        """清空对话历史"""
        self.conversation_history = []


async def run_interactive():
    """交互式对话模式"""
    agent = KingdeeAgent()
    
    try:
        await agent.connect_mcp()
        
        print("\n" + "=" * 60)
        print("金蝶云星空智能助手")
        print("=" * 60)
        print("输入 'quit' 退出，'clear' 清空对话历史")
        print("=" * 60 + "\n")
        
        while True:
            try:
                user_input = input("你: ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() == "quit":
                    print("再见！")
                    break
                
                if user_input.lower() == "clear":
                    agent.clear_history()
                    print("对话历史已清空。\n")
                    continue
                
                print("\n助手: ", end="", flush=True)
                response = await agent.chat(user_input)
                print(response + "\n")
                
            except KeyboardInterrupt:
                print("\n再见！")
                break
            except Exception as e:
                logger.error(f"处理消息失败: {e}")
                print(f"抱歉，处理您的请求时出错: {e}\n")
    
    finally:
        await agent.disconnect()


async def run_once(query: str):
    """单次查询模式"""
    agent = KingdeeAgent()
    
    try:
        await agent.connect_mcp()
        response = await agent.chat(query)
        print(response)
    finally:
        await agent.disconnect()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="金蝶 MCP Agent")
    parser.add_argument("--query", "-q", type=str, help="单次查询")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    
    args = parser.parse_args()
    
    if args.query:
        asyncio.run(run_once(args.query))
    else:
        asyncio.run(run_interactive())