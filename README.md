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
- ✅ 24 个 MCP 工具覆盖常用业务场景
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
│   ├── config_loader.py      # 配置加载（环境变量优先）
│   ├── config.py             # 本地覆盖配置（需自行创建，已被 .gitignore 忽略）
│   └── config.example.py     # 配置模板
│
├── kingdee_mcp_agent/        # MCP Agent
│   ├── mcp_server/           # MCP Server
│   │   ├── server.py         # 24 个金蝶工具
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

凭证统一从环境变量读取（不写入代码或仓库）：

```bash
export KINGDEE_SERVER_URL="http://your-server/K3Cloud"
export KINGDEE_ACCT_ID="your_acct_id"
export KINGDEE_USERNAME="your_username"
export KINGDEE_PASSWORD="your_password"
# 可选（API签名认证）：
# export KINGDEE_APP_ID="your_app_id"
# export KINGDEE_APP_SECRET="your_app_secret"
# export KINGDEE_AUTH_TYPE="SIGN_SHA256"     # PASSWORD(默认) / SIGN_SHA256 / SIGN_SHA1 / APP_SECRET
```

也可以复制 `kingdee_sdk/config.example.py` 为 `kingdee_sdk/config.py`（该文件已被 `.gitignore` 忽略）做本地覆盖。

配置优先级：代码显式传入 > 环境变量 > `kingdee_sdk/config.py` > `kingdee_mcp_agent/config/settings.py` > 内置默认值。

#### 3. 基础用法

```python
from kingdee_sdk import KingdeeClient
from kingdee_sdk.config_loader import KINGDEE_CONFIG, validate_config

# 检查配置是否完整（缺凭证时会提示具体缺哪几项）
missing = validate_config(KINGDEE_CONFIG)

# 创建客户端（KINGDEE_CONFIG 的键名与客户端参数一致）
client = KingdeeClient(**KINGDEE_CONFIG)

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

金蝶凭证与 LLM API Key 均从环境变量读取（MCP Server / Agent 共用）：

```bash
export KINGDEE_SERVER_URL="http://your-server/K3Cloud"
export KINGDEE_ACCT_ID="your_acct_id"
export KINGDEE_USERNAME="your_username"
export KINGDEE_PASSWORD="your_password"
export LLM_API_KEY="你的大模型 API Key"
```

如需调整非凭证选项（传输方式、模型名、端口、调试开关等），复制示例文件后按需修改：

```bash
cp kingdee_mcp_agent/config/settings.example.py kingdee_mcp_agent/config/settings.py
```

> ⚠️ 用 Claude Desktop 等 MCP 客户端启动本 Server 时，客户端默认只传递 `PATH`/`HOME` 等白名单
> 环境变量，因此凭证必须写进客户端的 `env` 配置（`mcpServers.<name>.env`）里，否则 server
> 子进程读不到 `KINGDEE_*`，会在调用工具时报“缺少金蝶连接配置项”。

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

运行示例（脚本会自动定位仓库根目录，可在任意目录执行）：

```bash
# SDK 功能演示
python examples/demo.py

# 交互式物料查询
python examples/material_query.py

# 物料详情查看
python examples/view_material_full.py

# ID检测
python scripts/detect_acct_id.py
```

> 运行前请先按上文设置环境变量（`KINGDEE_SERVER_URL` 等），
> 否则脚本会提示具体缺少哪几项配置。

## 注意事项

1. **配置安全**：凭证（金蝶密码、LLM API Key）只从环境变量读取，不写入代码或仓库；`kingdee_sdk/config.py` 与 `kingdee_mcp_agent/config/settings.py` 是可选的本地覆盖文件，已被 `.gitignore` 忽略，请勿提交
2. **配置来源**：环境变量 > `kingdee_sdk/config.py` > `kingdee_mcp_agent/config/settings.py` > 内置默认值；`kingdee_sdk/config_loader.py` 提供 `load_kingdee_config()` / `validate_config()` / `describe_config()`
3. **会话管理**：SDK 自动管理会话，无需手动处理 Cookie
4. **超时设置**：默认超时 30 秒，可通过 `timeout` 参数调整
5. **调试模式**：设置 `debug=True` 可查看请求详情
6. **生产环境**：建议使用 API 签名认证而非密码认证

## 接口与账套事实（实测）

以下结论来自对当前账套的只读实测，换账套或升级版本后请重新验证：

- **查询接口 `ExecuteBillQuery` 的错误形态**：出错时不返回 HTTP 错误，而是把错误体塞进结果里，
  形如 `[[{"Result": {"ResponseStatus": {"IsSuccess": false, "Errors": [{"Message": "..."}]}}}]]`
  （官方文档亦载明“错误结果只有一行数据且 IsSuccess 为 False”）。SDK 已在 `execute_bill_query`
  中识别该形态并抛出 `KingdeeAPIError`，不再把错误体当数据返回。
- **字段命名规则**：基础资料用 `字段.FNumber`（如 `FMaterialId.FNumber`），分录主键用 `FEntity_FEntryID`；
  字段不存在时接口会明确报“元数据中标识为 X 的字段不存在”，可据此校验字段名。
- **`ENG_BOM`（BOM）**：没有 `FBomNo` / `FVersion` 字段；BOM 编号就是 `FNumber`
  （形如 `1.LE.CC.050010_V.0`，版本信息已包含在编号里），过滤条件用 `FMaterialId.FNumber`。
- **附件接口**（已用真实上传/下载闭环验证过）：
  - 上传 `AttachmentUpLoad` 参数：`FileName` / `FormId` / `InterId` / `BillNO` / `SendByte`（Base64）
    / `IsLast` / `Entrykey` / `EntryinterId` / `AliasFileName` / `FileId`；**整文件一次性上传，接口不支持分片**，
    大文件会以 Base64 全量读入内存。
  - **参数必须包在 `{"data": "<json字符串>"}` 里**（与 `execute_bill_query` 一致）；直接放顶层会报
    “接口参数data不能为空”。SDK 已按此实现。
  - 下载 `AttachmentDownLoad` 参数：`FileId` + `StartIndex`（按 `StartIndex` 分片，首次传 0）；
    `FileId` 取自附件表 `BOS_Attachment` 的 `FFileId`（形如 `Temp_xxx-xxx`）。
  - 实测闭环（2026-09 已验证）：上传到**已审核的业务单据**成功并返回 `FileId` → `BOS_Attachment`
    可查到该记录 → 下载回来 md5 与原文一致；上传到**基础资料/物料**（`BD_MATERIAL`）会被账套拒绝，
    报“当前单据状态不允许上传附件（MsgCode 11）”，属账套对该对象的管控，与参数无关。
- **当前账套未安装 PLM 模块（已排除账号权限因素）**：`ENG_ECO` / `ENG_ECN` / `PLM_DOC` /
  `PLM_DRAWING` / `PLM_PROJECT` / `PLM_TASK` 均报「标识为 X 的业务对象不存在，或者被删除」，
  而 `ENG_BOM` / `ENG_ROUTE` / `BOS_Attachment` 可正常访问；用金蝶内置管理员账号复测的结果与
  普通账号完全一致（两组均只能访问上述三个对象），说明是账套未安装/未启用这些模块，而非账号权限不足。
  因此变更单与图纸相关功能在本账套不可用：查询类会降级返回空列表，写入类会报“业务对象不存在”。

## 参考文档

- [金蝶云星空 WebAPI 接口说明书](./kingdee_sdk/api文档.md)
- [金蝶云星空开放平台 API 文档](https://openapi.open.kingdee.com/ApiDoc)（JS 单页应用，需用浏览器打开）
- [MCP Agent 详细说明](./kingdee_mcp_agent/README.md)
- [快速开始](./docs/guides/快速开始.md)
- [使用指南](./docs/guides/使用指南.md)
- [API 探索记录](./docs/reference/金蝶云API探索记录.md)
- [金蝶官方文档](https://help.kingdee.com/)

## License

MIT License