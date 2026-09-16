"""
金蝶 MCP Agent / MCP Server 配置示例

复制此文件为 settings.py 后按需修改。
注意：settings.py 不会被 Git 追踪，保护你的敏感信息。

凭证（金蝶账号密码、LLM API Key）一律从环境变量读取，不要写在本文件里：
    export KINGDEE_SERVER_URL=http://<server>/K3Cloud
    export KINGDEE_ACCT_ID=<账套ID>
    export KINGDEE_USERNAME=<用户名>
    export KINGDEE_PASSWORD=<密码>
    export LLM_API_KEY=<你的大模型 API Key>
"""

import os
import sys
from pathlib import Path

# 保证可以从仓库根导入 kingdee_sdk
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kingdee_sdk.config_loader import load_kingdee_config

# ==================== 金蝶服务器配置 ====================
# 统一由 config_loader 读取：
#   环境变量 > kingdee_sdk/config.py > 本文件 > 内置默认值
# 需要写死到本地时，可直接用字典覆盖，例如：
#   KINGDEE_CONFIG = {
#       "server_url": "http://192.168.x.x/K3Cloud",
#       "acct_id": "...", "username": "...", "password": "",
#       "lcid": 2052, "auth_type": "PASSWORD",
#   }

KINGDEE_CONFIG = load_kingdee_config()

# ==================== MCP Server 配置 ====================

MCP_CONFIG = {
    # 服务器名称
    "name": "Kingdee MCP Server",

    # 传输方式: stdio, sse, streamable-http
    "transport": os.getenv("MCP_TRANSPORT", "stdio"),

    # HTTP 端口（仅 sse/streamable-http 模式）
    "port": int(os.getenv("MCP_PORT", "8000")),
}

# ==================== Agent 配置 ====================

AGENT_CONFIG = {
    # LLM 模型 API 配置
    # 支持: deepseek, glm, openai
    "llm_provider": os.getenv("LLM_PROVIDER", "glm"),

    # API Key（从环境变量获取，不要硬编码！）
    "deepseek_api_key": os.getenv("LLM_API_KEY", ""),

    # API 地址
    # DeepSeek: https://api.deepseek.com/v1
    # 腾讯云 GLM: https://api.lkeap.cloud.tencent.com/coding/v3
    "deepseek_base_url": os.getenv("LLM_BASE_URL", "https://api.lkeap.cloud.tencent.com/coding/v3"),

    # 模型名称
    "model_name": os.getenv("LLM_MODEL", "glm-5"),

    # OpenAI（可选，llm_provider=openai 时使用）
    "openai_api_key": os.getenv("OPENAI_API_KEY", ""),

    # 最大工具调用次数（防止无限循环）
    "max_tool_calls": int(os.getenv("LLM_MAX_TOOL_CALLS", "10")),

    # 调试模式
    "debug": os.getenv("AGENT_DEBUG", "true").lower() in ("1", "true", "yes"),
}

# ==================== 安全配置 ====================

SECURITY_CONFIG = {
    # 是否启用用户认证
    "enable_auth": os.getenv("SECURITY_ENABLE_AUTH", "false").lower() in ("1", "true", "yes"),

    # 允许的用户列表（企微/钉钉用户 ID，逗号分隔）
    "allowed_users": [u.strip() for u in os.getenv("SECURITY_ALLOWED_USERS", "").split(",") if u.strip()],

    # 是否记录操作日志
    "enable_logging": os.getenv("SECURITY_ENABLE_LOGGING", "true").lower() in ("1", "true", "yes"),

    # 日志文件路径
    "log_file": os.getenv("SECURITY_LOG_FILE", "logs/agent.log"),
}
