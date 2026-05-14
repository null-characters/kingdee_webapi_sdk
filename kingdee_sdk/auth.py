"""
金蝶WebAPI认证模块（改进版）
支持多种认证方式：API签名、AppSecret、密码登录、密钥文件
"""

import hashlib
import base64
import hmac
import time
from typing import Tuple, Optional
from enum import Enum


class AuthType(Enum):
    """认证方式枚举"""
    SIGN_SHA256 = "sign_sha256"      # API签名认证（SHA256）- 推荐
    SIGN_SHA1 = "sign_sha1"          # API签名认证（SHA1）- 旧版本兼容
    APP_SECRET = "app_secret"        # 第三方授权认证（AppSecret）
    PASSWORD = "password"            # 用户名密码认证


class KingdeeAuth:
    """
    金蝶WebAPI认证类
    支持多种认证方式
    """
    
    def __init__(self, auth_type: AuthType = AuthType.SIGN_SHA256):
        """
        初始化认证
        
        Args:
            auth_type: 认证方式
        """
        self.auth_type = auth_type
    
    def prepare_auth_data(
        self,
        acct_id: str,
        username: str,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        password: Optional[str] = None,
        lcid: int = 2052
    ) -> Tuple[dict, str]:
        """
        准备认证数据
        
        Args:
            acct_id: 账套ID
            username: 用户名
            app_id: 应用ID（签名认证需要）
            app_secret: 应用密钥（签名认证需要）
            password: 密码（密码认证需要）
            lcid: 语言编码
            
        Returns:
            (认证数据字典, 时间戳或空字符串)
        """
        if self.auth_type == AuthType.SIGN_SHA256:
            return self._prepare_sign_auth(acct_id, username, app_id, app_secret, lcid, "sha256")
        elif self.auth_type == AuthType.SIGN_SHA1:
            return self._prepare_sign_auth(acct_id, username, app_id, app_secret, lcid, "sha1")
        elif self.auth_type == AuthType.APP_SECRET:
            return self._prepare_app_secret_auth(acct_id, username, app_id, app_secret, lcid)
        elif self.auth_type == AuthType.PASSWORD:
            return self._prepare_password_auth(acct_id, username, password, lcid)
        else:
            raise ValueError(f"不支持的认证方式: {self.auth_type}")
    
    def _prepare_sign_auth(
        self,
        acct_id: str,
        username: str,
        app_id: str,
        app_secret: str,
        lcid: int,
        algorithm: str
    ) -> Tuple[dict, str]:
        """
        准备API签名认证数据
        
        签名规则：
        1. 将 [acct_id, username, app_id, app_secret, timestamp] 放入数组
        2. 对数组排序（按字母顺序）
        3. 将数组合并成一个字符串
        4. 使用SHA1或SHA256加密
        5. 返回16进制小写字符串
        """
        if not app_id or not app_secret:
            raise ValueError("API签名认证需要提供 app_id 和 app_secret")
        
        timestamp = int(time.time())
        
        # 构建签名数组
        arr = [acct_id, username, app_id, app_secret, str(timestamp)]
        arr.sort()
        sign_str = "".join(arr)
        
        # 计算签名
        if algorithm == "sha256":
            signature = hashlib.sha256(sign_str.encode('utf-8')).hexdigest()
        else:
            signature = hashlib.sha1(sign_str.encode('utf-8')).hexdigest()
        
        data = {
            "acctID": acct_id,
            "username": username,
            "appId": app_id,
            "timestamp": timestamp,
            "sign": signature.lower(),
            "lcid": lcid
        }
        
        return data, str(timestamp)
    
    def _prepare_app_secret_auth(
        self,
        acct_id: str,
        username: str,
        app_id: str,
        app_secret: str,
        lcid: int
    ) -> Tuple[dict, str]:
        """准备AppSecret认证数据"""
        if not app_id or not app_secret:
            raise ValueError("AppSecret认证需要提供 app_id 和 app_secret")
        
        data = {
            "acctID": acct_id,
            "username": username,
            "appId": app_id,
            "appSecret": app_secret,
            "lcid": lcid
        }
        return data, ""
    
    def _prepare_password_auth(
        self,
        acct_id: str,
        username: str,
        password: str,
        lcid: int
    ) -> Tuple[dict, str]:
        """准备密码认证数据 - 使用 ValidateLogin 接口"""
        if not password:
            raise ValueError("密码认证需要提供 password")
        
        # 金蝶密码认证 - 使用 ValidateUser 接口
        # 参数: acctID, username, password, lcid
        data = {
            "acctID": acct_id,
            "username": username,
            "password": password,
            "lcid": lcid
        }
        return data, ""
    
    @staticmethod
    def generate_request_sign(
        params: dict,
        app_secret: str,
        method: str = "POST"
    ) -> str:
        """
        生成API请求头签名（直接通过请求头签名访问，减少一次HTTP请求）
        
        注意：金蝶官方已删除相关文档，谨慎使用
        
        Args:
            params: 请求参数
            app_secret: 应用密钥
            method: HTTP方法
            
        Returns:
            签名字符串
        """
        # 按参数名排序
        sorted_params = sorted(params.items())
        param_str = "&".join([f"{k}={v}" for k, v in sorted_params])
        
        # 添加方法
        sign_str = f"{method}&{param_str}&{app_secret}"
        
        return hashlib.sha256(sign_str.encode('utf-8')).hexdigest().lower()
