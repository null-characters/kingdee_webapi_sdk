# 金蝶云星空 MCP Agent

将金蝶云星空 SDK 封装为 MCP 工具，让 AI Agent 可以通过自然语言操作 ERP 系统。

## 项目结构

```
kingdee_mcp_agent/
├── mcp_server/           # MCP Server（封装 SDK）
│   ├── server.py         # MCP 服务入口
│   └── requirements.txt  # MCP 依赖
├── agent/                # Agent 服务
│   ├── agent.py          # Agent 主逻辑
│   ├── test_client.py    # 测试客户端
│   └── requirements.txt  # Agent 依赖
├── config/
│   └ settings.py         # 配置文件
└── README.md             # 本文档
```

## 快速开始

### 1. 安装依赖

```bash
# MCP Server 依赖
cd mcp_server
pip install -r requirements.txt

# Agent 依赖
cd agent
pip install -r requirements.txt
```

### 2. 配置

编辑 `config/settings.py`，填入：
- 金蝶服务器地址、账号密码
- DeepSeek/OpenAI API Key

### 3. 测试 MCP Server

```bash
# 使用 MCP Inspector 测试
cd mcp_server
uv run mcp dev server.py

# 或直接运行
python server.py --transport stdio
```

### 4. 运行 Agent

```bash
cd agent

# 交互模式
python agent.py -i

# 单次查询
python agent.py -q "查询前5个物料"
```

## 可用工具

| 工具名 | 功能 |
|-------|------|
| `query_bill` | 通用单据查询 |
| `view_bill` | 查看单据详情 |
| `save_bill` | 创建/修改单据 |
| `submit_bill` | 提交审批 |
| `audit_bill` | 审核单据 |
| `delete_bill` | 删除单据 |
| `search_materials` | 搜索物料 |
| `get_material_detail` | 物料详情 |
| `create_material` | 创建物料 |
| `get_bom` | 获取 BOM |
| `create_bom` | 创建 BOM |
| `get_pending_ecos` | 待审批变更单 |
| `approve_eco` | 审批变更单 |
| `reject_eco` | 驳回变更单 |

## 对话示例

```
你: 查询前5个物料的信息

助手: 我为您查询了前5个物料：
1. MAT001 - 螺丝M6x20
2. MAT002 - 螺母M6
3. MAT003 - 弹簧垫圈
4. MAT004 - 平垫圈
5. MAT005 - 螺栓M8x30

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

## 下一步

1. **接入企业微信/钉钉**: 使用 FastAPI + Webhook 接收消息
2. **添加安全层**: 用户认证、权限控制、操作日志
3. **部署到服务器**: Docker 容器化部署

## 技术架构

```
用户 → 企业微信/钉钉 → Agent 服务 → MCP Server → 金蝶 SDK → 金蝶云星空
```

## 注意事项

- 确保 `kingdee_sdk/` 目录在项目根目录
- 金蝶账号密码不要硬编码，使用环境变量
- 生产环境建议使用 API 签名认证而非密码认证