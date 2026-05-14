# 金蝶云星空 WebAPI SDK

一个简洁易用的金蝶云星空（K3Cloud）WebAPI Python SDK，支持用户名密码认证和API签名认证。

## 功能特性

- ✅ 用户名密码认证
- ✅ API签名认证（SHA256/SHA1）
- ✅ 第三方应用授权认证
- ✅ 单据查询、保存、提交、审核等操作
- ✅ 附件上传（支持大文件分块上传）
- ✅ 自动会话管理
- ✅ 完善的错误处理

## 快速开始

### 安装依赖

```bash
pip install requests
```

### 配置

1. 复制配置示例文件：

```bash
cp kingdee_sdk/config.example.py kingdee_sdk/config.py
```

2. 编辑 `config.py` 填入实际配置：

```python
KINGDEE_CONFIG = {
    "server_url": "http://your-server/K3Cloud",
    "acct_id": "your_acct_id",
    "username": "your_username",
    "password": "your_password",
    "lcid": 2052
}
```

### 基础用法

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

## API 方法

### 单据查询

```python
# 基础查询
result = client.execute_bill_query(
    form_id="BD_MATERIAL",
    field_keys="FNumber,FName,FSpecification",
    limit=20
)

# 带条件查询
result = client.execute_bill_query(
    form_id="BD_MATERIAL",
    field_keys="FNumber,FName",
    filter_string="FNumber like '%M%'",
    order_string="FNumber DESC",
    limit=20
)

# 分页查询
result = client.execute_bill_query(
    form_id="BD_MATERIAL",
    field_keys="FNumber,FName",
    start_row=0,
    limit=100
)
```

### 单据操作

```python
# 查看单据详情
detail = client.view("BD_MATERIAL", {"Number": "M001"})

# 保存单据
result = client.save("SAL_ORDER", {
    "FBillNo": "SO001",
    "FDate": "2026-05-14"
})

# 提交单据
result = client.submit("SAL_ORDER", {"Numbers": ["SO001"]})

# 审核单据
result = client.audit("SAL_ORDER", {"Numbers": ["SO001"]})

# 删除单据
result = client.delete("SAL_ORDER", {"Numbers": ["SO001"]})
```

### 附件上传

```python
# 上传附件
result = client.upload_attachment(
    file_path="/path/to/file.pdf",
    form_id="BD_MATERIAL",
    bill_no="M001"
)
```

## 工具程序

### 物料查询控制台

```bash
python material_query.py
```

交互式物料查询工具，支持：
- 查询所有物料
- 按编号精确查询
- 按名称模糊查询

### 数据中心ID检测

```bash
python detect_acct_id.py
```

自动检测可用的数据中心ID（acct_id）。

## 常用表单ID

| 表单ID | 说明 |
|-------|------|
| BD_MATERIAL | 物料 |
| BD_CUSTOMER | 客户 |
| BD_SUPPLIER | 供应商 |
| BD_STOCK | 仓库 |
| SAL_ORDER | 销售订单 |
| PUR_POOrder | 采购申请单 |
| STK_InStock | 入库单 |
| STK_MisDelivery | 出库单 |

## 错误处理

```python
from kingdee_sdk.exceptions import KingdeeAPIError, AuthenticationError

try:
    client.login()
except AuthenticationError as e:
    print(f"认证失败: {e}")
except KingdeeAPIError as e:
    print(f"API错误: {e}")
```

## 项目结构

```
kingdee_webapi_sdk/
├── kingdee_sdk/
│   ├── __init__.py      # 模块入口
│   ├── client.py        # 客户端实现
│   ├── auth.py          # 认证模块
│   ├── exceptions.py    # 异常定义
│   ├── config.py        # 配置文件（需自行创建）
│   └── config.example.py # 配置示例
├── demo.py              # 功能演示
├── material_query.py    # 物料查询工具
├── detect_acct_id.py    # ID检测工具
├── requirements.txt     # 依赖列表
└── README.md            # 本文档
```

## 注意事项

1. **配置安全**：`config.py` 包含敏感信息，已被 `.gitignore` 忽略，不会提交到仓库
2. **会话管理**：SDK 自动管理会话，无需手动处理 Cookie
3. **超时设置**：默认超时 30 秒，可通过 `timeout` 参数调整
4. **调试模式**：设置 `debug=True` 可查看请求详情

## 参考文档

- [金蝶云星空 WebAPI 接口说明书](./kingdee_sdk/api文档.md)
- [金蝶官方文档](https://help.kingdee.com/)

## License

MIT License
