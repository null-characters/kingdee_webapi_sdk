# 金蝶云星空 API 探索记录

## 探索目的

探索金蝶云星空 WebAPI 能力范围，确认可用于业务流程自动化的接口。

## 系统信息

| 配置项 | 值 |
|--------|-----|
| 服务器地址 | `http://192.168.0.200/K3Cloud` |
| 账套 ID | `668f7c152248a3` |
| 用户名 | 冯冰 |

## API 能力总览

### 已验证可用的接口

| 接口类型 | 方法 | 状态 | 说明 |
|----------|------|------|------|
| **查询** | `execute_bill_query` | ✓ | 通用单据查询 |
| **详情** | `view` | ✓ | 查看单据完整信息 |
| **保存** | `save` | ✓ | 创建/修改单据 |
| **批量保存** | `batch_save` | ✓ | 批量创建/修改 |
| **暂存** | `draft` | ✓ | 保存为草稿 |
| **提交** | `submit` | ✓ | 提交审批流程 |
| **审核** | `audit` | ✓ | 审核单据 |
| **反审核** | `unaudit` | ✓ | 撤销审核 |
| **删除** | `delete` | ✓ | 删除未审核单据 |
| **上传附件** | `upload_attachment` | ✓ | 支持大文件分块上传 |
| **下载附件** | `download_attachment` | ✓ | 下载附件到本地 |

### 已验证可用的表单

#### 基础资料模块

| 表单 ID | 名称 | 主键字段 | 常用字段 |
|---------|------|----------|----------|
| `BD_MATERIAL` | 物料 | `FMaterialID` | `FNumber, FName, FSpecification, FMaterialGroup, FBaseUnitId, FDocumentStatus` |
| `BD_SUPPLIER` | 供应商 | `FSupplierId` | `FNumber, FName, FContact` |
| `BD_CUSTOMER` | 客户 | `FCustomerId` | `FNumber, FName, FContact` |
| `BD_UNIT` | 计量单位 | `FUnitId` | `FNumber, FName, FPrecision` |
| `BD_MATERIALCATEGORY` | 物料分组 | `FCategoryId` | `FNumber, FName` |
| `BD_STOCK` | 仓库 | `FStockId` | `FNumber, FName, FStockProperty` |
| `SEC_User` | 用户 | `FUserId` | `FNumber, FName, FPhone` |

#### 工程数据模块

| 表单 ID | 名称 | 主键字段 | 常用字段 |
|---------|------|----------|----------|
| `ENG_BOM` | 工程 BOM | `FID` | `FBillNo, FMaterialId, FVersionNo, FDocumentStatus` |
| `ENG_BOMVERSION` | BOM 版本 | `FID` | `FVersionNo, FMaterialId` |
| `ENG_ECO` | 工程变更单 | `FID` | `FBillNo, FChangeType, FDocumentStatus` |

#### 采购管理模块

| 表单 ID | 名称 | 主键字段 | 常用字段 |
|---------|------|----------|----------|
| `PUR_PurchaseOrder` | 采购订单 | `FID` | `FBillNo, FDate, FSupplierId, FDocumentStatus` |
| `PUR_ReqBill` | 采购申请单 | `FID` | `FBillNo, FDate, FDocumentStatus` |

#### 销售管理模块

| 表单 ID | 名称 | 主键字段 | 常用字段 |
|---------|------|----------|----------|
| `SAL_SaleOrder` | 销售订单 | `FID` | `FBillNo, FDate, FCustomerId, FDocumentStatus` |

#### 生产管理模块

| 表单 ID | 名称 | 主键字段 | 常用字段 |
|---------|------|----------|----------|
| `PRD_MO` | 生产工单 | `FID` | `FBillNo, FDate, FMaterialId, FDocumentStatus` |

#### 库存管理模块

| 表单 ID | 名称 | 主键字段 | 常用字段 |
|---------|------|----------|----------|
| `STK_InStock` | 入库单 | `FID` | `FBillNo, FDate, FStockId, FDocumentStatus` |
| `STK_Inventory` | 即时库存 | `FID` | `FMaterialId, FStockId, FQty` |

#### 系统管理模块

| 表单 ID | 名称 | 主键字段 | 常用字段 |
|---------|------|----------|----------|
| `BOS_BillType` | 单据类型 | `FID` | `FFormId, FName`（共 528 种） |
| `BOS_Attachment` | 附件 | `FID` | `FATTACHMENTNAME, FBillNo, FBillType` |

### 单据状态说明

| 状态码 | 含义 | 可执行操作 |
|--------|------|------------|
| `A` | 新建（未提交） | 修改、删除、提交 |
| `B` | 已提交（待审核） | 审核、驳回 |
| `C` | 已审核 | 反审核、关闭 |
| `D` | 已关闭 | 无 |

---

## SDK 实现说明

### 认证方式

| 认证类型 | AuthType | 参数要求 |
|----------|----------|----------|
| 用户名密码 | `PASSWORD` | `username, password` |
| API 签名 SHA256 | `SIGN_SHA256` | `username, app_id, app_secret` |
| API 签名 SHA1 | `SIGN_SHA1` | `username, app_id, app_secret` |

### SDK 核心方法

```python
from kingdee_sdk import KingdeeClient, AuthType

# 创建客户端
client = KingdeeClient(
    server_url="http://your-server/K3Cloud",
    acct_id="your_acct_id",
    username="your_username",
    password="your_password",
    auth_type=AuthType.PASSWORD,
    debug=False
)

# 自动登录
client.login()

# 查询物料
result = client.execute_bill_query(
    form_id="BD_MATERIAL",
    field_keys="FNumber,FName,FSpecification,FDocumentStatus",
    filter_string="FDocumentStatus='C'",  # 已审核
    limit=10
)

# 查看详情
detail = client.view("BD_MATERIAL", {"Number": "MAT001"})

# 创建单据
client.save("BD_MATERIAL", {
    "Model": {
        "FNumber": "NEW001",
        "FName": "新物料"
    }
})

# 提交审批
client.submit("BD_MATERIAL", {"Numbers": ["NEW001"]})

# 审核
client.audit("BD_MATERIAL", {"Numbers": ["NEW001"]})

# 登出
client.logout()
```

---

## MCP Agent 实现

### MCP 工具列表（22 个）

#### 通用单据操作（10 个）

| 工具名 | 功能 | 对应 SDK 方法 |
|--------|------|---------------|
| `query_bill` | 通用单据查询 | `execute_bill_query` |
| `view_bill` | 查看单据详情 | `view` |
| `save_bill` | 创建/修改单据 | `save` |
| `draft_bill` | 暂存单据 | `draft` |
| `batch_save_bill` | 批量保存单据 | `batch_save` |
| `submit_bill` | 提交审批 | `submit` |
| `audit_bill` | 审核单据 | `audit` |
| `unaudit_bill` | 反审核单据 | `unaudit` |
| `delete_bill` | 删除单据 | `delete` |
| `upload_attachment` | 上传附件 | `upload_attachment` |
| `download_attachment` | 下载附件 | `download_attachment` |

#### PLM 物料管理（4 个）

| 工具名 | 功能 |
|--------|------|
| `search_materials` | 搜索物料（模糊匹配） |
| `get_material_detail` | 获取物料详情 |
| `create_material` | 创建新物料 |
| `batch_create_materials` | 批量创建物料 |

#### PLM BOM 管理（3 个）

| 工具名 | 功能 |
|--------|------|
| `get_bom` | 获取物料 BOM 结构 |
| `create_bom` | 创建 BOM |
| `batch_create_boms` | 批量创建 BOM |

#### PLM 变更管理（3 个）

| 工具名 | 功能 |
|--------|------|
| `get_pending_ecos` | 获取待审批变更单 |
| `approve_eco` | 审批变更单 |
| `reject_eco` | 驳回变更单 |

#### PLM 图纸管理（3 个）

| 工具名 | 功能 |
|--------|------|
| `upload_drawing` | 上传图纸并关联物料 |
| `download_drawing` | 下载图纸 |
| `search_drawings` | 搜索图纸 |

### MCP 使用示例

```bash
# 启动 MCP Server（stdio 模式）
python kingdee_mcp_agent/mcp_server/server.py --transport stdio

# 启动 MCP Server（HTTP 模式）
python kingdee_mcp_agent/mcp_server/server.py --transport sse --port 8000
```

---

## 探索结论

### 可用能力

| 能力 | 状态 | 说明 |
|------|------|------|
| 物料查询/创建 | ✓ | 完整可用 |
| BOM 查询/创建 | ✓ | 完整可用 |
| 采购/销售/生产单据 | ✓ | 完整可用 |
| 单据审批流程 | ✓ | 提交、审核、反审核 |
| 附件上传/下载 | ✓ | 支持大文件分块上传 |
| 批量操作 | ✓ | 批量创建、批量审核 |
| MCP Agent | ✓ | 22 个工具，自然语言交互 |

### 不可用能力

| 能力 | 状态 | 说明 |
|------|------|------|
| PLM 文档库 | ✗ | WebAPI 未开放，需联系金蝶实施顾问 |
| PLM 图纸管理 | ⚠️ | MCP 工具已实现，但依赖 BOS_Attachment |

### 建议

1. **业务流程自动化**：SDK 和 MCP 完全支持物料、BOM、采购、销售、生产等业务流程自动化
2. **PLM 文档库**：联系金蝶实施顾问确认 WebAPI 是否开放，或使用 SVN/Git 管理源代码
3. **扩展开发**：可通过 MCP Agent 接入企业微信/钉钉，实现自然语言交互

---

## 更新记录

| 日期 | 内容 |
|------|------|
| 2026-05-20 | 初始探索，确认物料查询可用 |
| 2026-05-20 | 深入探索 PLM 文档库，确认 WebAPI 不可用 |
| 2026-05-20 | 探索业务流程 API，确认单据操作完整可用 |
| 2026-05-20 | 整合 SDK 和 MCP 实现，优化文档结构 |