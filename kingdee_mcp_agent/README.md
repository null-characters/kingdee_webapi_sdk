# 金蝶云星空 MCP Agent

将金蝶云星空 SDK 封装为 MCP 工具，让 AI Agent 可以通过自然语言操作 ERP 系统。

## 功能特性

- ✅ 14 个 MCP 工具覆盖常用业务场景
- ✅ 自然语言交互，无需编写代码
- ✅ 支持腾讯云 GLM-5 / DeepSeek / OpenAI
- ✅ 可接入企业微信/钉钉
- ✅ 配置文件保护敏感信息

## 项目结构

```
kingdee_mcp_agent/
├── mcp_server/               # MCP Server
│   ├── server.py             # 14 个金蝶工具
│   ├── requirements.txt      # MCP 依赖
│   └── __init__.py
│
├── agent/                    # Agent 服务
│   ├── agent.py              # Agent 主逻辑
│   ├── requirements.txt      # Agent 依赖
│   └── __init__.py
│
├── config/
│   ├── settings.py           # 配置文件（需自行创建）
│   ├── settings.example.py   # 配置示例
│   └── __init__.py
│
└── README.md                 # 本文档
```

## 快速开始

### 1. 安装依赖

```bash
# MCP Server 依赖
cd kingdee_mcp_agent/mcp_server
pip install -r requirements.txt

# Agent 依赖
cd kingdee_mcp_agent/agent
pip install -r requirements.txt
```

### 2. 配置

复制配置示例文件：

```bash
cp config/settings.example.py config/settings.py
```

编辑 `config/settings.py`，填入：

```python
# 金蝶服务器配置
KINGDEE_CONFIG = {
    "server_url": "http://your-server/K3Cloud",
    "acct_id": "your_acct_id",
    "username": "your_username",
    "password": "your_password",
    "lcid": 2052,
    "auth_type": "PASSWORD",
}

# LLM 配置
AGENT_CONFIG = {
    "llm_provider": "glm",  # glm / deepseek / openai
    "deepseek_api_key": "your_api_key",
    "deepseek_base_url": "https://api.lkeap.cloud.tencent.com/coding/v3",
    "model_name": "glm-5",
}
```

**支持的 LLM**：

| Provider | API 地址 | 模型 |
|----------|---------|------|
| 腾讯云 GLM | api.lkeap.cloud.tencent.com/coding/v3 | glm-5, glm-5-plus |
| DeepSeek | api.deepseek.com/v1 | deepseek-chat |
| OpenAI | api.openai.com/v1 | gpt-4o |

### 3. 运行 Agent

```bash
cd agent

# 交互模式
python agent.py -i

# 单次查询
python agent.py -q "查询前5个物料"
```

### 4. 测试 MCP Server

```bash
cd mcp_server

# 直接运行（stdio 模式）
python server.py

# 使用 MCP Inspector 测试
uv run mcp dev server.py
```

## 可用工具

### 通用单据操作

| 工具名 | 功能 | 参数 |
|-------|------|------|
| `query_bill` | 通用单据查询 | form_id, field_keys, filter_string, limit |
| `view_bill` | 查看单据详情 | form_id, number/bill_id |
| `save_bill` | 创建/修改单据 | form_id, model_json |
| `submit_bill` | 提交审批 | form_id, numbers |
| `audit_bill` | 审核单据 | form_id, numbers |
| `delete_bill` | 删除单据 | form_id, numbers |

### 物料管理

| 工具名 | 功能 | 参数 |
|-------|------|------|
| `search_materials` | 搜索物料 | keyword, material_group, limit |
| `get_material_detail` | 物料详情 | material_code |
| `create_material` | 创建物料 | material_code, material_name, specification |

### BOM 管理

| 工具名 | 功能 | 参数 |
|-------|------|------|
| `get_bom` | 获取 BOM | material_code, version |
| `create_bom` | 创建 BOM | bom_no, parent_material_code, items_json |

### 变更管理

| 工具名 | 功能 | 参数 |
|-------|------|------|
| `get_pending_ecos` | 待审批变更单 | limit |
| `approve_eco` | 审批变更单 | bill_no |
| `reject_eco` | 驳回变更单 | bill_no |

## 对话示例

```
你: 查询前5个物料的信息

助手: 我为您查询了前5个物料：
| 序号 | 物料编码 | 物料名称 | 规格型号 | 状态 |
|------|---------|---------|---------|------|
| 1 | MAT001 | 螺丝M6x20 | M6x20mm | 已审核 |
| 2 | MAT002 | 螺母M6 | M6 | 已审核 |
| 3 | MAT003 | 弹簧垫圈 | M6 | 已审核 |
...

你: 帮我创建一个新物料，编号 NEW001，名称 测试物料

助手: 好的，我来为您创建物料 NEW001。
物料创建成功！
- 编号: NEW001
- 名称: 测试物料
- 状态: 已保存

你: 有哪些待审批的变更单？

助手: 当前有 3 个待审批的变更单：
1. ECO2026001 - 物料变更（张三创建）
2. ECO2026002 - BOM变更（李四创建）
3. ECO2026003 - 工艺变更（王五创建）

需要我帮您审批吗？
```

## 技术架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   用户      │────▶│   Agent     │────▶│ MCP Server  │────▶│  金蝶 SDK   │
│ (自然语言)  │     │ (LLM+MCP)   │     │ (14个工具)   │     │  (WebAPI)   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                     │
                                                                     ▼
                                                              ┌─────────────┐
                                                              │  金蝶云星空  │
                                                              │  (ERP 系统) │
                                                              └─────────────┘
```

## 配置优先级

MCP Server 读取配置的优先级：

1. **环境变量**（优先）
   - `KINGDEE_SERVER_URL`
   - `KINGDEE_ACCT_ID`
   - `KINGDEE_USERNAME`
   - `KINGDEE_PASSWORD`

2. **settings.py**
   - `KINGDEE_CONFIG` 字典

如果两者都未配置，会报错提示。

## 下一步

1. **接入企业微信/钉钉**: 使用 FastAPI + Webhook 接收消息
2. **添加安全层**: 用户认证、权限控制、操作日志
3. **部署到服务器**: Docker 容器化部署
4. **添加更多工具**: 根据业务需求扩展

## 注意事项

- `settings.py` 包含敏感信息，已被 `.gitignore` 忽略
- 确保 `kingdee_sdk/` 目录在项目根目录
- 生产环境建议使用 API 签名认证而非密码认证
- 建议使用环境变量管理敏感配置