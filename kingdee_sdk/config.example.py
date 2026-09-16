# -*- coding: utf-8 -*-
"""
金蝶 WebAPI 本地配置模板

凭证统一从环境变量读取；本文件只是“可选”的本地覆盖手段：
复制为 kingdee_sdk/config.py（该文件已被 .gitignore 忽略）后，可覆盖/补充环境变量中的值。

推荐做法（无需本文件）：
    export KINGDEE_SERVER_URL=http://<server>/K3Cloud
    export KINGDEE_ACCT_ID=<账套ID>
    export KINGDEE_USERNAME=<用户名>
    export KINGDEE_PASSWORD=<密码>
    # 可选：export KINGDEE_APP_ID=... / KINGDEE_APP_SECRET=... / KINGDEE_AUTH_TYPE=SIGN_SHA256

配置优先级（高 → 低）：
    代码显式传入 > 环境变量 > 本文件 > kingdee_mcp_agent/config/settings.py > 内置默认值

安全提醒：请勿把真实密码写进任何会被 git 提交的文件。
"""

import os

KINGDEE_CONFIG = {
    # ========== 基础配置 ==========

    # 金蝶服务器地址
    "server_url": os.getenv("KINGDEE_SERVER_URL", ""),

    # 数据中心ID (账套ID)，可通过 scripts/detect_acct_id.py 检测
    "acct_id": os.getenv("KINGDEE_ACCT_ID", ""),

    # 语言ID (2052=简体中文, 1033=英文)
    "lcid": int(os.getenv("KINGDEE_LCID", "2052")),

    # ========== 用户名密码认证 ==========

    "username": os.getenv("KINGDEE_USERNAME", ""),
    "password": os.getenv("KINGDEE_PASSWORD", ""),

    # ========== API签名认证 (可选) ==========
    # 需要在金蝶后台配置应用，获取 AppID 和 AppSecret

    "app_id": os.getenv("KINGDEE_APP_ID", ""),
    "app_secret": os.getenv("KINGDEE_APP_SECRET", ""),

    # 认证方式: PASSWORD(默认) / SIGN_SHA256 / SIGN_SHA1 / APP_SECRET
    "auth_type": os.getenv("KINGDEE_AUTH_TYPE", "PASSWORD"),
}
