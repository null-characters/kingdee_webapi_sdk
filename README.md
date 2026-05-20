# 金蝶云星空 WebAPI SDK

一个简洁易用的金蝶云星空（K3Cloud）WebAPI Python SDK，支持用户名密码认证和API签名认证。

**新增 MCP Agent 支持**：现已封装为 MCP Server，可通过自然语言操作金蝶系统。

## 功能特性

### SDK 核心功能
- ✅ 用户名密码认证
- ✅ API签名认证（SHA256/SHA1）
- ✅ 第三方应用授权认证
- ✅ 单据查询、保存、提交、审核等操作
- ✅ 附件上传（支持大文件分块上传）
- ✅ 自动会话管理
- ✅ 完善的错误处理

### MCP Agent 功能（新增）
- ✅ 14 个 MCP 工具覆盖常用业务场景
- ✅ 自然语言交互，无需编写代码
- ✅ 支持腾讯云 GLM-5 / DeepSeek / OpenAI
- ✅ 可接入企业微信/钉钉

## 项目结构

```
kingdee_webapi_sdk/
├── kingdee_sdk/              # SDK 核心
│   ├── __init__.py           # 模块入口
│   ├── client.py             # 客户端实现
│   ├── auth.py               # 认证模块
│   ├── exceptions.py         # 异常定义
│   ├── plm_tools.py          # PLM 工具集
│   ├── config.py             # 配置文件（需自行创建）
│   └── config.example.py     # 配置示例
│
├── kingdee_mcp_agent/        # MCP Agent
│   ├── mcp_server/           # MCP Server
│   │   ├── server.py         # 14 个金蝶工具
│   │   └── requirements.txt
│   ├── agent/                # Agent 服务
│   │   ├── agent.py          # Agent 主逻辑
│   │   └── requirements.txt
│   ├── config/
│   │   ├── settings.py       # 配置文件（需自行创建）
│   │   └── settings.example.py
│   └── README.md
│
├── docs/                     # 文档目录
│   ├── guides/               # 使用指南
│   │   ├── 快速开始.md
│   │   ├── 使用指南.md
│   │   └── AGENT_GUIDE.md
│   └── reference/            # 参考资料
│       ├── 金蝶云API探索记录.md
│       ├── all_bill_types.json
│       └── bill_types_list.txt
│
├── examples/                 # 示例脚本
│   ├── demo.py               # SDK 功能演示
│   ├── example.py            # PLM 完整示例
│   ├── material_query.py     # 物料查询工具
│   └── view_material_full.py # 物料详情查看
│
├── scripts/                  # 业务脚本
│   ├── detect_acct_id.py     # ID检测工具
│   ├── extract_submitted_items.py
│   └── verify_material_codes.py
│
├── tests/                    # 测试脚本
│   ├── test_sdk_full.py
│   └── test_sdk_functions.py
│
├── requirements.txt          # SDK 依赖
└── README.md                 # 本文档
```

## 快速开始

### 方式一：直接使用 SDK

#### 1. 安装依赖

```bash
pip install requests
```

#### 2. 配置

复制配置示例文件：

```bash
cp kingdee_sdk/config.example.py kingdee_sdk/config.py
```

编辑 `config.py` 填入实际配置：

```python
KINGDEE_CONFIG = {
    "server_url": "http://your-server/K3Cloud",
    "acct_id": "your_acct_id",
    "username": "your_username",
    "password": "your_password",
    "lcid": 2052
}
```

#### 3. 基础用法

```python
from kingdee_sdk import KingdeeClient, AuthType

# 创建客户端
client = KingdeeClient(
    server_url="http://your-server/K3Cloud",
    acct_id="your_acct_id",
    username="your_username",
    password="your_password",
    auth_type=AuthType.PASSWORD
)

# 登录
client.login()

# 查询物料
result = client.execute_bill_query(
    form_id="BD_MATERIAL",
    field_keys="FNumber,FName,FSpecification",
    limit=10
)

# 登出
client.logout()
```

### 方式二：使用 MCP Agent（推荐）

通过自然语言操作金蝶系统，无需编写代码。

#### 1. 安装依赖

```bash
cd kingdee_mcp_agent/mcp_server
pip install -r requirements.txt

cd kingdee_mcp_agent/agent
pip install -r requirements.txt
```

#### 2. 配置

复制配置示例文件：

```bash
cp kingdee_mcp_agent/config/settings.example.py kingdee_mcp_agent/config/settings.py
```

编辑 `settings.py` 填入：
- 金蝶服务器配置
- LLM API Key（腾讯云 GLM-5 / DeepSeek / OpenAI）

#### 3. 运行 Agent

```bash
cd kingdee_mcp_agent/agent

# 交互模式
python agent.py -i

# 单次查询
python agent.py -q "查询前5个物料"
```

#### 4. 对话示例

```
你: 查询前5个物料的信息

助手: 我为您查询了前5个物料：
| 序号 | 物料编码 | 物料名称 | 规格型号 |
|------|---------|---------|---------|
| 1 | MAT001 | 螺丝M6x20 | M6x20mm |
| 2 | MAT002 | 螺母M6 | M6 |
| 3 | MAT003 | 弹簧垫圈 | M6 |
...

你: 有哪些待审批的变更单？

助手: 当前有 3 个待审批的变更单：
1. ECO2026001 - 物料变更（张三创建）
2. ECO2026002 - BOM变更（李四创建）
3. ECO2026003 - 工艺变更（王五创建）
```

## MCP 工具列表

### 通用单据操作
| 工具名 | 功能 | 说明 |
|-------|------|------|
| `query_bill` | 通用单据查询 | 支持任意表单查询 |
| `view_bill` | 查看单据详情 | 查看单据完整信息 |
| `save_bill` | 创建/修改单据 | 保存单据数据 |
| `draft_bill` | 暂存单据 | 保存为草稿状态 |
| `batch_save_bill` | 批量保存单据 | 批量创建/修改 |
| `submit_bill` | 提交审批 | 提交单据审批流程 |
| `audit_bill` | 审核单据 | 审核通过单据 |
| `unaudit_bill` | 反审核单据 | 撤销审核状态 |
| `delete_bill` | 删除单据 | 删除未审核单据 |

### 附件管理
| 工具名 | 功能 | 说明 |
|-------|------|------|
| `upload_attachment` | 上传附件 | 上传文件到金蝶系统 |
| `download_attachment` | 下载附件 | 下载附件到本地 |

### PLM 物料管理
| 工具名 | 功能 | 说明 |
|-------|------|------|
| `search_materials` | 搜索物料 | 模糊搜索物料 |
| `get_material_detail` | 物料详情 | 查看物料完整信息 |
| `create_material` | 创建物料 | 新建物料主数据 |
| `batch_create_materials` | 批量创建物料 | 批量新建物料 |

### PLM BOM 管理
| 工具名 | 功能 | 说明 |
|-------|------|------|
| `get_bom` | 获取 BOM | 查看物料 BOM 结构 |
| `create_bom` | 创建 BOM | 新建 BOM 关系 |
| `batch_create_boms` | 批量创建 BOM | 批量新建 BOM |

### PLM 变更管理
| 工具名 | 功能 | 说明 |
|-------|------|------|
| `get_pending_ecos` | 待审批变更单 | 查询待审批 ECO |
| `approve_eco` | 审批变更单 | 审批通过 ECO |
| `reject_eco` | 驳回变更单 | 驳回 ECO |

### PLM 图纸管理
| 工具名 | 功能 | 说明 |
|-------|------|------|
| `upload_drawing` | 上传图纸 | 上传图纸并关联物料 |
| `download_drawing` | 下载图纸 | 下载图纸文件 |
| `search_drawings` | 搜索图纸 | 按物料或名称搜索 |

## 认证方式

### 1. 用户名密码认证

```python
client = KingdeeClient(
    server_url="http://your-server/K3Cloud",
    acct_id="your_acct_id",
    username="your_username",
    password="your_password",
    auth_type=AuthType.PASSWORD
)
```

### 2. API签名认证（推荐）

需要在金蝶后台配置应用，获取 AppID 和 AppSecret：

```python
client = KingdeeClient(
    server_url="http://your-server/K3Cloud",
    acct_id="your_acct_id",
    username="your_username",
    app_id="your_app_id",
    app_secret="your_app_secret",
    auth_type=AuthType.SIGN_SHA256
)
```

## 常用表单ID

| 表单ID | 说明 |
|-------|------|
| BD_MATERIAL | 物料 |
| BD_CUSTOMER | 客户 |
| BD_SUPPLIER | 供应商 |
| BD_STOCK | 仓库 |
| SAL_SaleOrder | 销售订单 |
| PUR_PurchaseOrder | 采购订单 |
| ENG_BOM | BOM |
| ENG_ECO | 工程变更单 |

## 工具程序

### 示例脚本 (examples/)

| 脚本 | 说明 |
|------|------|
| `demo.py` | SDK 功能演示 |
| `example.py` | PLM 完整示例 |
| `material_query.py` | 交互式物料查询工具 |
| `view_material_full.py` | 物料详情查看 |

### 业务脚本 (scripts/)

| 脚本 | 说明 |
|------|------|
| `detect_acct_id.py` | 自动检测可用的数据中心ID |
| `extract_submitted_items.py` | 提取已提交项目清单 |
| `verify_material_codes.py` | 子物料编码校验 |

运行示例：

```bash
# 物料查询
python examples/material_query.py

# ID检测
python scripts/detect_acct_id.py
```

## 注意事项

1. **配置安全**：`config.py` 和 `settings.py` 包含敏感信息，已被 `.gitignore` 忽略
2. **会话管理**：SDK 自动管理会话，无需手动处理 Cookie
3. **超时设置**：默认超时 30 秒，可通过 `timeout` 参数调整
4. **调试模式**：设置 `debug=True` 可查看请求详情
5. **生产环境**：建议使用 API 签名认证而非密码认证

## 参考文档

- [金蝶云星空 WebAPI 接口说明书](./kingdee_sdk/api文档.md)
- [MCP Agent 详细说明](./kingdee_mcp_agent/README.md)
- [快速开始](./docs/guides/快速开始.md)
- [使用指南](./docs/guides/使用指南.md)
- [API 探索记录](./docs/reference/金蝶云API探索记录.md)
- [金蝶官方文档](https://help.kingdee.com/)

## License

MIT License