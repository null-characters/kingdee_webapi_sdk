"""
金蝶API异常定义
"""


class KingdeeAPIError(Exception):
    """金蝶API通用错误"""
    
    def __init__(self, message, code=None, response_data=None):
        super().__init__(message)
        self.code = code
        self.response_data = response_data


class AuthenticationError(KingdeeAPIError):
    """认证错误（签名失败、Token过期等）"""
    pass


class ValidationError(KingdeeAPIError):
    """参数校验错误"""
    pass


class NotFoundError(KingdeeAPIError):
    """资源不存在"""
    pass


class RateLimitError(KingdeeAPIError):
    """请求频率超限"""
    pass
