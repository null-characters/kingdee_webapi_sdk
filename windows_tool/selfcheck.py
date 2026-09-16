# -*- coding: utf-8 -*-
"""
金蝶云星空小工具 —— 固定配置 + 登录自检逻辑

这个文件只放「与界面无关」的逻辑，方便单独验证：
    python selfcheck.py --check --user 冯冰 --password xxx

固定项（按需求写死，用户不可修改）：
    - 服务器地址、账套 ID、语言
    - 登录方式：用户名 + 密码

安全约定：
    - 密码只在内存中使用，不写入磁盘、不写日志文件
"""

import os
import sys

# 让脚本在源码目录和 PyInstaller 打包后都能 import 到 kingdee_sdk
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(_ROOT, "kingdee_sdk")) and _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from kingdee_sdk import AuthType, KingdeeAPIError, KingdeeClient
except Exception as _exc:  # pragma: no cover - 打包环境异常时给出人话提示
    AuthType = KingdeeAPIError = KingdeeClient = None
    _IMPORT_ERROR = _exc
else:
    _IMPORT_ERROR = None


# ==================== 固定配置（界面上只读展示；换服务器/账套改这里） ====================

FIXED_CONFIG = {
    "server_url": "http://192.168.0.200/K3Cloud",  # 金蝶服务器地址（固定）
    "acct_id": "668f7c152248a3",                   # 数据中心/账套 ID（固定）
    "lcid": 2052,                                  # 中文简体
    "timeout": 30,                                  # 单次请求超时（秒）
    "max_retries": 2,                               # 网络重试次数
}

APP_TITLE = "金蝶成本核算工具（内部）"
APP_VERSION = "0.2.0"

# 自检项：成本核算要用到的三张表单（只读查询，不改任何数据）
SELFCHECK_FORMS = (
    ("SAL_SaleOrder", "销售订单"),
    ("PUR_PurchaseOrder", "采购订单"),
    ("ENG_BOM", "物料清单(BOM)"),
)


def build_client(username, password):
    """按固定配置创建客户端（不做登录）"""
    if KingdeeClient is None:
        raise RuntimeError(f"SDK 加载失败：{_IMPORT_ERROR}")
    return KingdeeClient(
        server_url=FIXED_CONFIG["server_url"],
        acct_id=FIXED_CONFIG["acct_id"],
        username=username,
        password=password,
        auth_type=AuthType.PASSWORD,
        lcid=FIXED_CONFIG["lcid"],
        timeout=FIXED_CONFIG["timeout"],
        max_retries=FIXED_CONFIG["max_retries"],
    )


def run_selfcheck(username, password, log=None):
    """登录 + 三表单只读自检

    Args:
        username: 金蝶账号
        password: 密码（仅内存使用）
        log: 接收进度文本的函数，默认 print

    Returns:
        (True, "") 全部通过；否则 (False, 失败原因)
    """
    log = log or print

    if not username or not password:
        msg = "请填写金蝶账号和密码"
        log(msg)
        return False, msg

    log(f"服务器：{FIXED_CONFIG['server_url']}    账套：{FIXED_CONFIG['acct_id']}")
    log(f"使用账号：{username}")

    try:
        client = build_client(username, password)
    except Exception as exc:
        log(f"初始化失败：{exc}")
        return False, str(exc)

    log("正在登录……")
    try:
        client.login()
    except KingdeeAPIError as exc:
        msg = f"登录失败：{exc}"
        log(msg)
        return False, str(exc)
    except Exception as exc:  # 网络不通等
        msg = f"登录异常：{exc}"
        log(msg)
        return False, str(exc)

    log("登录成功 ✅")
    log("开始自检三个表单（只读查询，不会改动任何数据）……")

    failed = []
    for form_id, label in SELFCHECK_FORMS:
        try:
            rows = client.execute_bill_query(form_id=form_id, field_keys="FID", limit=1)
            sample = rows[0][0] if rows and isinstance(rows[0], (list, tuple)) and rows[0] else "无数据"
            log(f"  [通过] {label}（{form_id}）可访问，样例单据内码：{sample}")
        except KingdeeAPIError as exc:
            failed.append(f"{label}（{form_id}）")
            log(f"  [失败] {label}（{form_id}）：{exc}")
        except Exception as exc:
            failed.append(f"{label}（{form_id}）")
            log(f"  [失败] {label}（{form_id}）：{exc}")

    try:
        client.logout()
        log("已退出登录。")
    except Exception:
        pass

    if failed:
        msg = "以下表单未能取数：" + "、".join(failed) + "（可把本窗口内容发给管理员）"
        log(msg)
        return False, msg

    log("自检全部通过：账号可正常读取销售订单、采购订单、物料清单。")
    return True, ""


def cli_main(argv=None):
    """命令行模式：python selfcheck.py --check --user 某某 --password xxx

    仅用于在没界面的机器上排查问题（也方便打包前验证）。密码优先取环境变量
    KINGDEE_PASSWORD，避免出现在命令历史里。
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    user = os.getenv("KINGDEE_USERNAME", "")
    password = os.getenv("KINGDEE_PASSWORD", "")
    for i, a in enumerate(argv):
        if a in ("--user", "-u") and i + 1 < len(argv):
            user = argv[i + 1]
        if a in ("--password", "-p") and i + 1 < len(argv):
            password = argv[i + 1]

    if not user:
        user = input("金蝶账号：").strip()
    if not password:
        import getpass
        password = getpass.getpass("密码：")

    ok, _msg = run_selfcheck(user, password)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(cli_main())
