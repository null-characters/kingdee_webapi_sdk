"""
金蝶 MCP Agent 配置文件示例

复制此文件为 settings.py 并填入实际配置。
注意：settings.py 不会被 Git 追踪，保护你的敏感信息。
"""

import os

# ==================== 金蝶服务器配置 ====================

KINGDEE_CONFIG = {
    # 金蝶服务器地址
    "server_url": os.getenv("KINGDEE_SERVER_URL", "http://your-server/K3Cloud"),
    
    # 数据中心 ID（账套 ID）
    "acct_id": os.getenv("KINGDEE_ACCT_ID", "your_acct_id"),
    
    # 用户名
    "username": os.getenv("KINGDEE_USERNAME", "your_username"),
    
    # 密码
    "password": os.getenv("KINGDEE_PASSWORD", "your_password"),
    
    # 语言代码（2052 = 中文简体）
    "lcid": 2052,
    
    # 认证方式: PASSWORD, SIGN_SHA256, SIGN_SHA1, APP_SECRET
    "auth_type": "PASSWORD",
}

# ==================== MCP Server 配置 ====================

MCP_CONFIG = {
    # 服务器名称
    "name": "Kingdee MCP Server",
    
    # 传输方式: stdio, sse, streamable-http
    "transport": "stdio",
    
    # HTTP 端口（仅 sse/streamable-http 模式）
    "port": 8000,
}

# ==================== Agent 配置 ====================

AGENT_CONFIG = {
    # LLM 模型 API 配置
    # 支持: deepseek, glm, openai
    "llm_provider": "glm",
    
    # API Key（从环境变量获取，不要硬编码！）
    "deepseek_api_key": os.getenv("LLM_API_KEY", ""),
    
    # API 地址
    # DeepSeek: https://api.deepseek.com/v1
    # 腾讯云 GLM: https://api.lkeap.cloud.tencent.com/coding/v3
    "deepseek_base_url": os.getenv("LLM_BASE_URL", "https://api.lkeap.cloud.tencent.com/coding/v3"),
    
    # 模型名称
    "model_name": "glm-5",
    
    # 最大工具调用次数（防止无限循环）
    "max_tool_calls": 10,
    
    # 调试模式
    "debug": True,
}

# ==================== 安全配置 ====================

SECURITY_CONFIG = {
    # 是否启用用户认证
    "enable_auth": False,
    
    # 允许的用户列表（企微/钉钉用户 ID）
    "allowed_users": [],
    
    # 是否记录操作日志
    "enable_logging": True,
    
    # 日志文件路径
    "log_file": "logs/agent.log",
}