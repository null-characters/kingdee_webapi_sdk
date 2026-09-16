# -*- coding: utf-8 -*-
"""
金蝶 WebAPI 配置加载器

统一从环境变量 / 本地配置文件读取连接参数，避免在源码中硬编码凭证。

优先级（高 → 低）：
    1. 调用方显式传入的参数（load_kingdee_config(server_url=...)）
    2. 环境变量：
       KINGDEE_SERVER_URL / KINGDEE_ACCT_ID / KINGDEE_USERNAME / KINGDEE_PASSWORD
       KINGDEE_APP_ID / KINGDEE_APP_SECRET / KINGDEE_LCID / KINGDEE_AUTH_TYPE
    3. kingdee_sdk/config.py              （本地文件，需自行创建，已被 .gitignore 忽略）
    4. kingdee_mcp_agent/config/settings.py（本地文件，需自行创建，已被 .gitignore 忽略）
    5. 内置默认值（不含任何凭证）

用法：
    from kingdee_sdk.config_loader import KINGDEE_CONFIG
    from kingdee_sdk import KingdeeClient

    client = KingdeeClient(**KINGDEE_CONFIG)   # 键名与 KingdeeClient 参数一致

需要时也可以重新读取（不会缓存）：
    from kingdee_sdk.config_loader import load_kingdee_config
    config = load_kingdee_config(debug=False)
"""

import importlib.util
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .auth import AuthType

logger = logging.getLogger(__name__)

__all__ = [
    "load_kingdee_config",
    "validate_config",
    "describe_config",
    "KINGDEE_CONFIG",
    "ENV_KEYS",
    "LOCAL_CONFIG_FILES",
    "PROJECT_ROOT",
]

# 配置项 -> 环境变量名
ENV_KEYS: Dict[str, str] = {
    "server_url": "KINGDEE_SERVER_URL",
    "acct_id": "KINGDEE_ACCT_ID",
    "username": "KINGDEE_USERNAME",
    "password": "KINGDEE_PASSWORD",
    "app_id": "KINGDEE_APP_ID",
    "app_secret": "KINGDEE_APP_SECRET",
    "lcid": "KINGDEE_LCID",
    "auth_type": "KINGDEE_AUTH_TYPE",
}

# 内置默认值（密码类凭证一律留空，必须由环境变量或本地配置文件提供）
DEFAULTS: Dict[str, Any] = {
    "server_url": "",
    "acct_id": "",
    "username": "",
    "password": "",
    "app_id": "",
    "app_secret": "",
    "lcid": 2052,
    "auth_type": AuthType.PASSWORD,
}

_PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _PACKAGE_DIR.parent

# 本地配置文件（均已被 .gitignore 忽略，按顺序先后决定优先级）
LOCAL_CONFIG_FILES = (
    _PACKAGE_DIR / "config.py",
    PROJECT_ROOT / "kingdee_mcp_agent" / "config" / "settings.py",
)

# 各认证方式额外必需的配置项
_REQUIRED_BY_AUTH = {
    AuthType.PASSWORD: ("password",),
    AuthType.SIGN_SHA256: ("app_id", "app_secret"),
    AuthType.SIGN_SHA1: ("app_id", "app_secret"),
    AuthType.APP_SECRET: ("app_id", "app_secret"),
}


def _is_set(value: Any) -> bool:
    """空串 / None 视为未设置"""
    return value is not None and str(value).strip() != ""


def _parse_auth_type(value: Any) -> AuthType:
    """把字符串（如 "PASSWORD" / "sign_sha256"）或枚举解析为 AuthType"""
    if isinstance(value, AuthType):
        return value
    if _is_set(value):
        raw = str(value).strip()
        if raw.upper() in AuthType.__members__:
            return AuthType[raw.upper()]
        for member in AuthType:
            if member.value.lower() == raw.lower():
                return member
        logger.warning("无法识别的 auth_type=%r，回退为 PASSWORD", value)
    return AuthType.PASSWORD


_LOADING_FILES: set = set()


def _read_config_file(path: Path) -> Dict[str, Any]:
    """按路径读取本地配置文件中的 KINGDEE_CONFIG（文件不存在则返回空字典）"""
    if not path.is_file():
        return {}
    # 本地配置文件自身可能也在调用 load_kingdee_config()，这里防止循环加载
    if path in _LOADING_FILES:
        return {}

    module_name = "_kingdee_local_config_" + path.parent.name + "_" + path.stem
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return {}
        module = importlib.util.module_from_spec(spec)
        _LOADING_FILES.add(path)
        try:
            spec.loader.exec_module(module)
        finally:
            _LOADING_FILES.discard(path)
    except Exception as e:  # 本地配置写错时不要中断调用方
        logger.warning("读取本地配置 %s 失败: %s", path, e)
        return {}

    config = getattr(module, "KINGDEE_CONFIG", None)
    if not isinstance(config, dict):
        logger.warning("本地配置 %s 中未找到 KINGDEE_CONFIG 字典", path)
        return {}
    return config


def load_kingdee_config(**overrides: Any) -> Dict[str, Any]:
    """
    按优先级装载金蝶连接配置。

    Returns:
        与 KingdeeClient 参数同名的配置字典：
        server_url / acct_id / username / password / app_id / app_secret / lcid / auth_type
    """
    resolved: Dict[str, Any] = {}

    def _fill(key: str, value: Any) -> None:
        if key not in resolved and _is_set(value):
            resolved[key] = value

    # 1. 显式传入
    for key, value in overrides.items():
        _fill(key, value)

    # 2. 环境变量
    for key, env_name in ENV_KEYS.items():
        _fill(key, os.getenv(env_name))

    # 3. 本地配置文件
    for path in LOCAL_CONFIG_FILES:
        file_config = _read_config_file(path)
        for key in ENV_KEYS:
            _fill(key, file_config.get(key))

    # 4. 内置默认值
    for key, value in DEFAULTS.items():
        _fill(key, value)

    # 归一化
    try:
        resolved["lcid"] = int(resolved.get("lcid") or DEFAULTS["lcid"])
    except (TypeError, ValueError):
        logger.warning("lcid 非法: %r，回退为 %s", resolved.get("lcid"), DEFAULTS["lcid"])
        resolved["lcid"] = DEFAULTS["lcid"]
    resolved["auth_type"] = _parse_auth_type(resolved.get("auth_type"))

    return resolved


def validate_config(config: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    返回缺失的必填配置项列表（空列表表示配置完整）。

    密码类凭证永不写入源码默认值，因此未设置环境变量时会在这里被检出。
    """
    config = config if config is not None else load_kingdee_config()
    missing = [key for key in ("server_url", "acct_id", "username") if not _is_set(config.get(key))]
    auth_type = _parse_auth_type(config.get("auth_type"))
    missing += [key for key in _REQUIRED_BY_AUTH.get(auth_type, ()) if not _is_set(config.get(key))]
    return missing


def describe_config(config: Optional[Dict[str, Any]] = None) -> str:
    """返回可安全打印的配置摘要（凭证只显示是否已设置）"""
    config = config if config is not None else load_kingdee_config()
    sensitive = ("password", "app_secret")
    parts = []
    for key in ("server_url", "acct_id", "username", "auth_type", "lcid"):
        parts.append(f"{key}={config.get(key)!r}")
    for key in sensitive:
        parts.append(f"{key}={'***' if _is_set(config.get(key)) else '(未设置)'}")
    return ", ".join(parts)


def _env_hint() -> str:
    return (
        "请通过环境变量或本地配置文件提供金蝶连接信息：\n"
        "1) 设置环境变量：\n"
        "   export KINGDEE_SERVER_URL=http://<server>/K3Cloud\n"
        "   export KINGDEE_ACCT_ID=<账套ID>\n"
        "   export KINGDEE_USERNAME=<用户名>\n"
        "   export KINGDEE_PASSWORD=<密码>\n"
        "2) 或复制 kingdee_sdk/config.example.py 为 kingdee_sdk/config.py 后填写\n"
        "   （该文件已被 .gitignore 忽略，不要提交）"
    )


# 模块级配置，import 时求值一次；凭证来自环境变量或本地配置文件
KINGDEE_CONFIG: Dict[str, Any] = load_kingdee_config()

MISSING_CONFIG_HINT = _env_hint()
