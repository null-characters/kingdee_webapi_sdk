# -*- coding: utf-8 -*-
"""
金蝶WebAPI配置示例
复制此文件为 config.py 并填入实际配置

注意：config.py 不会被git追踪，保护你的敏感信息
"""

KINGDEE_CONFIG = {
    # ========== 基础配置 ==========
    
    # 金蝶服务器地址
    "server_url": "http://your-server/K3Cloud",
    
    # 数据中心ID (账套ID)
    # 可通过 detect_acct_id.py 工具自动检测
    "acct_id": "your_acct_id",
    
    # 语言ID (2052=简体中文, 1033=英文)
    "lcid": 2052,
    
    # ========== 用户名密码认证 ==========
    # 适用于普通用户登录
    
    # 登录用户名
    "username": "your_username",
    
    # 登录密码
    "password": "your_password",
    
    # ========== API签名认证 (可选) ==========
    # 适用于第三方应用集成，需要管理员在金蝶后台配置
    
    # 应用ID (AppID)
    "app_id": "",
    
    # 应用密钥 (AppSecret)
    "app_secret": "",
}