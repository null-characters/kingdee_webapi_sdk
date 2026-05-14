"""
金蝶云星空 PLM API SDK（改进版）

特性：
- 多种认证方式（API签名SHA256/SHA1、AppSecret、密码登录）
- 附件上传下载（支持分块上传大文件）
- 调试模式（输出请求详情，便于排查问题）
- 自动登录和会话保持
- PLM业务封装（物料、BOM、变更单、图纸）

使用示例:
    >>> from kingdee_sdk import KingdeeClient, AuthType
    >>> client = KingdeeClient(
    ...     server_url="http://localhost/k3cloud",
    ...     acct_id="账套ID",
    ...     username="用户名",
    ...     app_id="应用ID",
    ...     app_secret="应用密钥",
    ...     auth_type=AuthType.SIGN_SHA256,
    ...     debug=True
    ... )
    >>> client.login()
    >>> materials = client.execute_bill_query(
    ...     form_id="BD_MATERIAL",
    ...     field_keys="FNumber,FName"
    ... )
"""

from .client import KingdeeClient
from .auth import KingdeeAuth, AuthType
from .exceptions import KingdeeAPIError, AuthenticationError, ValidationError, NotFoundError
from .plm_tools import PLMTools

__version__ = "2.0.0"
__all__ = [
    "KingdeeClient",
    "KingdeeAuth",
    "AuthType",
    "PLMTools",
    "KingdeeAPIError",
    "AuthenticationError",
    "ValidationError",
    "NotFoundError"
]
