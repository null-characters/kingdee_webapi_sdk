# 金蝶云星空 PLM WebAPI Python SDK

基于金蝶官方WebAPI规范实现的Python SDK，支持物料查询、BOM创建、变更单审批、图纸上传等PLM核心业务操作。

## 功能特性

- **多种认证方式**: API签名认证(SHA256)、AppSecret认证、用户名密码认证
- **完整表单操作**: 查看、保存、删除、提交、审核、反审核
- **PLM业务封装**: 物料/BOM/变更单/图纸的便捷操作方法
- **附件管理**: 分块上传、下载附件（支持大文件图纸）
- **批量操作**: 批量创建物料、批量审核等
- **调试模式**: 输出请求详情，便于排查问题
- **自动重试**: 网络错误自动重试机制
- **Cookie复用**: 登录状态保持，避免重复登录

## 快速开始

### 1. 安装依赖

```bash
pip install requests
```

### 2. 配置参数

编辑 `kingdee_sdk/config.py`:

```python
KINGDEE_CONFIG = {
    "server_url": "http://your-server/k3cloud",
    "acct_id": "your_acct_id",          # 数据中心ID
    "username": "Administrator",
    "app_id": "your_app_id",            # 应用ID（从开放平台获取）
    "app_secret": "your_app_secret",    # 应用密钥
    "lcid": 2052                        # 语言编码（2052=简体中文）
}
```

### 3. 运行示例

```bash
python example.py
```

## 使用示例

### API签名认证（推荐）

```python
from kingdee_sdk import KingdeeClient, PLMTools
from kingdee_sdk.config import KINGDEE_CONFIG

# 初始化客户端
client = KingdeeClient(
    server_url=KINGDEE_CONFIG["server_url"],
    acct_id=KINGDEE_CONFIG["acct_id"],
    username=KINGDEE_CONFIG["username"],
    app_id=KINGDEE_CONFIG["app_id"],
    app_secret=KINGDEE_CONFIG["app_secret"],
    lcid=KINGDEE_CONFIG["lcid"]
)

# 开启调试模式
client.set_debug(True)

# 登录
client.login()

# 使用PLM工具
plm = PLMTools(client)
```

### 查询物料

```python
# 根据编码查询
material = plm.query_material_by_code("MAT001")

# 模糊搜索
materials = plm.search_materials(keyword="电阻", limit=10)
```

### 创建BOM

```python
result = plm.create_bom(
    bom_no="BOM-2024-001",
    parent_material_code="PARENT001",
    items=[
        {"material_code": "CHILD001", "qty": 2},
        {"material_code": "CHILD002", "qty": 1},
    ]
)
```

### 审批变更单

```python
# 获取待审批列表
pending = plm.get_pending_ecos(limit=5)

# 审批变更单
plm.approve_eco(eco_id=12345)
```

### 上传图纸

```python
result = plm.upload_drawing(
    file_path=r"C:\drawings\assembly.pdf",
    drawing_name="装配图",
    drawing_code="DRW-001",
    chunk_size=1024*1024  # 1MB分块上传
)
```

### 批量操作

```python
# 批量创建物料
materials = [
    {"FNumber": "MAT001", "FName": "物料1"},
    {"FNumber": "MAT002", "FName": "物料2"},
]
result = plm.batch_create_materials(materials)
```

## 项目结构

```
kingdee_sdk/
├── __init__.py           # 包初始化
├── auth.py               # 认证模块（SHA256签名等）
├── client.py             # HTTP客户端和WebAPI操作
├── plm_tools.py          # PLM业务工具封装
├── exceptions.py         # 异常定义
├── config.py             # 配置文件
└── README.md             # 使用文档
```

## API对照表

| SDK方法 | 对应WebAPI | 说明 |
|---------|-----------|------|
| `client.login()` | `AuthService.LoginBySign` | 登录获取Cookie |
| `client.view()` | `DynamicFormService.View` | 查看单据 |
| `client.save()` | `DynamicFormService.Save` | 保存单据 |
| `client.delete()` | `DynamicFormService.Delete` | 删除单据 |
| `client.submit()` | `DynamicFormService.Submit` | 提交单据 |
| `client.audit()` | `DynamicFormService.Audit` | 审核单据 |
| `client.unaudit()` | `DynamicFormService.UnAudit` | 反审核单据 |
| `client.execute_bill_query()` | `DynamicFormService.ExecuteBillQuery` | 查询数据 |
| `client.upload_attachment()` | `AttachmentService.Upload` | 上传附件 |

## 常见问题

### Q1: 登录失败，提示签名错误？
A: 请检查：
- `app_id` 和 `app_secret` 是否正确
- 系统时间是否准确（签名有时间戳校验）
- 认证方式是否选择正确

### Q2: FormId是什么？
A: FormId是金蝶表单的唯一标识，常见有：
- `BD_MATERIAL`: 物料
- `ENG_BOM`: BOM
- `ENG_ECO`: 工程变更单
- `PLM_DRAWING`: PLM图纸

### Q3: 如何获取详细的调试信息？
A: 在调用login()前设置：`client.set_debug(True)`

### Q4: 支持批量上传图纸吗？
A: 支持！使用 `plm.upload_drawing()` 的批量接口。

## 参考资源

- [金蝶开放平台](https://open.kingdee.com)
- [WebAPI接口说明书](api文档.md)
- [YiKdWebClient (C#参考)](https://github.com/1609676823/YiKdWebClient)
