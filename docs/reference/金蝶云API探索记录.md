# 金蝶云星空 API 探索记录

## 探索目的

探索金蝶云星空 API 是否能访问"文档库/软件源代码/试产程序"文件夹，用于自动化程序文件管理。

## 系统信息

- **服务器地址**: `http://192.168.0.200/K3Cloud`
- **账套 ID**: `668f7c152248a3`
- **用户名**: 冯冰
- **SDK 路径**: `/Users/fengbing/git_prj/kingdee_webapi_sdk`

## GUI 路径映射

根据用户提供的 GUI 路径信息：

| 功能 | GUI 路径 | 实际表单 ID | 状态 |
|------|----------|-------------|------|
| 物料库 | PLM → 研发物料管理 → 物料库 | `BD_MATERIAL` | ✓ 可用 |
| 文档库 | PLM → 文档管理 → 文档库 | 待确认 | ✗ WebAPI 不可用 |

## 已验证可用的表单

| 表单 ID | 名称 | 主键字段 | 说明 |
|---------|------|----------|------|
| `BD_MATERIAL` | 物料 | `FMaterialID` | 物料基础信息，已成功查询 |
| `ENG_BOM` | 工程 BOM | `FID` | 工程物料清单 |
| `BOS_Attachment` | 附件 | `FID` | 通用附件表单 |

## 已探索但不可用的表单

### PLM 文档相关表单（全部返回"业务对象不存在"）

| 表单 ID | 错误信息 |
|---------|----------|
| `PLM_DOCLIB` | 业务对象不存在 |
| `PLM_DOC` | 业务对象不存在 |
| `PLM_DOCMASTER` | 业务对象不存在 |
| `PLM_DOCFILE` | 业务对象不存在 |
| `PLM_FOLDER` | 业务对象不存在 |
| `PLM_FILE` | 业务对象不存在 |
| `PLM_DRAWING` | 业务对象不存在 |
| `PLM_ATTACHMENT` | 业务对象不存在 |

### 其他尝试的表单 ID（全部不存在）

尝试了以下命名规则，均返回"业务对象不存在"：
- `PLM_*` 系列：PLM_DOCUMENTMANAGER, PLM_DOCMANAGER, PLM_DOCLIBRARY 等
- `BOS_*` 系列：BOS_DOCUMENT, BOS_FILE, BOS_PLMDOC 等
- `ENG_*` 系列：ENG_ECO, ENG_ECN, ENG_DRAWING, ENG_DOC, ENG_FILE
- `KM_*` 系列：KM_DOC, KM_DOCUMENT, KM_LIBRARY
- `PDM_*` 系列：PDM_DOCUMENT, PDM_DOCLIB 等
- `RDM_*` 系列：RDM_DOCUMENT 等

## 物料详情分析

通过 `view` 接口查看物料 `3.R.C01.000006` 详情，发现：

| 字段 | 值 | 说明 |
|------|-----|------|
| `PLMMaterialId` | 空 | PLM 物料关联字段（未关联） |
| `ImageFileServer` | 空 | 图片服务器路径 |
| `ImgStorageType` | B | 图片存储类型 |
| `Image` | null | 物料图片 |

**结论**：物料详情中没有附件分录字段，该物料目前没有关联附件。

## BOS_Attachment 附件表

可用字段：
- `FID` - 附件 ID
- `FEntryKey` - 分录键
- `FInterID` - 内码
- `FATTACHMENTNAME` - 附件名称
- `FBillNo` - 单据编号
- `FBillType` - 单据类型

示例数据：
```
[1225616, 'Temp_0b56f19c-...', '泰易81薄膜开关报价单.pdf', ' ', 'PUR_PriceCategory']
```

**发现**：附件主要关联到采购相关单据（`PUR_PriceCategory`），未发现物料附件。

## 用户提供的文档实例探索

用户提供了一个真实存在于文档库中的实例：

| 属性 | 值 |
|------|-----|
| 文件名 | BLD-GM480-277_1127.7z |
| 编码 | DOC-软件程序-2025.12.08-17706 |
| 业务类型 | WD-024 |
| 文件夹 | 2025.12.08-0001 / 试产程序 |
| 创建日期 | 2025/12/8 20:09:31 |
| 创建人 | 付政云 |
| 文档路径 | 软件源代码\试产程序\ |

### 探索过程

1. **搜索文件名 `BLD-GM480-277_1127.7z`**
   - 在 `BOS_Attachment` 中搜索：未找到
   - 在 `BD_MATERIAL` 中搜索：未找到

2. **搜索编码 `DOC-软件程序-2025.12.08-17706`**
   - 在所有可用表单中搜索：未找到匹配记录

3. **搜索创建人 `付政云`**
   - 在 `SEC_User` 中找到：用户 ID = 1221062
   - 在 `BOS_Attachment` 中搜索该用户创建的附件：未找到（创建人字段不可用）

4. **查询 BOS_BillType 所有单据类型**
   - 总共 528 种单据类型
   - PLM 相关：仅 `PLMTDFA01_SYS: PLM替代方案` 一种
   - WD- 相关：无
   - 文档相关：无

5. **测试所有可能的 PLM 表单 ID**
   - 全部返回"业务对象不存在"
   - 包括：PLM_DOC, PLM_DOCLIB, PLM_FILE, PLM_FOLDER, PLM_DRAWING 等

### 结论

**PLM 文档库模块的 WebAPI 接口未开放**

尽管用户可以通过 GUI 访问 PLM 文档库，但 WebAPI 接口不可用。原因可能是：
1. PLM 文档库模块的 WebAPI 接口需要单独购买或配置
2. PLM 文档库使用的是自定义表单，不在标准 WebAPI 范围内
3. 需要特定权限才能通过 API 访问

## 业务流程 API 探索

### 已验证的 API 能力

#### 1. 查询能力 (execute_bill_query)
| 模块 | 表单 ID | 状态 | 说明 |
|------|---------|------|------|
| 基础资料 | `BD_MATERIAL` | ✓ | 物料信息查询 |
| 基础资料 | `BD_SUPPLIER` | ✓ | 供应商查询 |
| 基础资料 | `BD_CUSTOMER` | ✓ | 客户查询 |
| 基础资料 | `BD_UNIT` | ✓ | 单位查询 |
| 基础资料 | `BD_MATERIALCATEGORY` | ✓ | 物料分组查询 |
| 工程数据 | `ENG_BOM` | ✓ | BOM 查询 |
| 采购管理 | `PUR_PurchaseOrder` | ✓ | 采购订单查询 |
| 销售管理 | `SAL_SaleOrder` | ✓ | 销售订单查询 |
| 生产管理 | `PRD_MO` | ✓ | 生产工单查询 |
| 库存管理 | `STK_InStock` | ✓ | 入库单查询 |
| 系统管理 | `SEC_User` | ✓ | 用户查询 |
| 系统管理 | `BOS_BillType` | ✓ | 单据类型查询 |
| 附件管理 | `BOS_Attachment` | ✓ | 附件查询 |

#### 2. 详情查询 (view)
- 获取单据完整详情 ✓
- 返回所有字段及关联对象信息

#### 3. 单据操作接口
| 操作 | 方法 | 状态 | 说明 |
|------|------|------|------|
| 保存/创建 | `save` | ✓ | 创建新单据或修改已有单据 |
| 提交 | `submit` | ✓ | 提交单据进入审批流程 |
| 审核 | `audit` | ✓ | 审核单据 |
| 反审核 | `unaudit` | ✓ | 撤销审核 |
| 删除 | `delete` | ✓ | 删除未审核的单据 |
| 草稿 | `draft` | ✓ | 保存为草稿 |
| 批量保存 | `batch_save` | ✓ | 批量创建/修改单据 |

#### 4. 附件操作接口
| 操作 | 方法 | 状态 |
|------|------|------|
| 上传附件 | `upload_attachment` | ✓ |
| 下载附件 | `download_attachment` | ✓ |

### 单据状态说明
- `A` = 新建（未提交）
- `B` = 已提交（待审核）
- `C` = 已审核
- `D` = 已关闭

### 业务流程自动化示例

#### 创建采购订单
```python
result = client.save(
    form_id='PUR_PurchaseOrder',
    data={
        "Model": {
            "FBillNo": "CGDD001",
            "FDate": "2025-05-20",
            "FSupplierId": {"FNumber": "SUP001"},
            "FPOOrderEntry": [
                {
                    "FMaterialId": {"FNumber": "MAT001"},
                    "FQty": 100,
                    "FPrice": 10.0
                }
            ]
        }
    }
)
```

#### 提交并审核单据
```python
# 提交
client.submit(form_id='PUR_PurchaseOrder', data={"Numbers": ["CGDD001"]})
# 审核
client.audit(form_id='PUR_PurchaseOrder', data={"Numbers": ["CGDD001"]})
```

## 探索结论

### 当前状态

1. **PLM 文档库模块 WebAPI 不可用**
   - 所有尝试的 PLM 文档相关表单 ID 均返回"业务对象不存在"
   - BOS_BillType 中只有 1 个 PLM 相关单据类型：`PLMTDFA01_SYS: PLM替代方案`
   - 没有找到 WD- 开头的单据类型
   - 没有找到名称包含"文档"的单据类型

2. **业务流程 API 完全可用**
   - 查询能力 ✓
   - 单据操作（创建、提交、审核、删除） ✓
   - 附件操作 ✓
   - 批量操作 ✓

### 建议下一步

1. **业务流程自动化**：可以使用 API 实现采购、销售、生产等业务流程自动化
2. **PLM 文档库**：联系金蝶实施顾问确认 WebAPI 是否开放
3. **替代方案**：使用 SVN/Git 管理源代码，使用金蝶附件功能关联文件

## 相关文件

| 文件 | 说明 |
|------|------|
| `extract_submitted_items.py` | 提取已提交项目脚本 |
| `已提交项目清单.md` | 提取结果（40 条记录） |
| `verify_material_codes.py` | 子物料编码校验脚本 |
| `子物料编码校验结果.md` | 校验报告（全部通过） |
| `explore_plm_forms.py` | PLM 表单探索脚本 |
| `explore_plm_doclib.py` | PLM 文档库探索脚本 |
| `explore_plm_doclib_v2.py` | PLM 文档库精确查询脚本 |
| `query_form_metadata.py` | 表单元数据查询脚本 |
| `query_plm_real_forms.py` | PLM 真实表单探索脚本 |
| `explore_material_attachments.py` | 物料附件探索脚本 |
| `view_material_full.py` | 物料详情查看脚本 |
| `material_detail.json` | 物料详情 JSON 文件 |
| `search_doc_instance.py` | 根据文档实例搜索脚本 |
| `query_plm_doc_detail.py` | PLM_DOC 详细查询脚本 |
| `search_by_code.py` | 根据编码格式搜索脚本 |
| `list_all_bill_types.py` | 列出所有单据类型脚本 |
| `all_bill_types.json` | 所有单据类型 JSON 文件 |
| `bill_types_list.txt` | 所有单据类型文本列表 |
| `find_real_forms.py` | 正确测试表单存在脚本 |

## 更新记录

| 日期 | 内容 |
|------|------|
| 2026-05-20 | 初始探索，确认物料查询可用 |
| 2026-05-20 | 深入探索 PLM 文档库，确认 WebAPI 不可用 |
| 2026-05-20 | 探索物料附件，确认附件功能未启用 |
| 2026-05-20 | 根据用户提供的文档实例深入探索，确认 PLM 文档库 WebAPI 未开放 |