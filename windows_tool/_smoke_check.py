# -*- coding: utf-8 -*-
"""打包前冒烟验证（开发者自查用，正式打包时可以不带上这个文件）

依次做四件事：
    1. 语法编译检查 app.py / selfcheck.py / kingdee_sdk/costing.py
    2. 构建一次界面后立刻销毁（等价于 --smoke-gui）
    3. 若提供了口令，跑一次真实登录 + 三表单自检（只读查询）
    4. 若提供了口令和月份，跑一次真实核算并导出 xlsx（只读查询）

用法：
    PYTHONDONTWRITEBYTECODE=1 python3 _smoke_check.py
    PYTHONDONTWRITEBYTECODE=1 KINGDEE_PASSWORD=xxx python3 _smoke_check.py --month 2026-09 --limit 3
"""

import argparse
import os
import py_compile
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

COMPILE_TARGETS = (
    os.path.join(HERE, "app.py"),
    os.path.join(HERE, "selfcheck.py"),
    os.path.join(ROOT, "kingdee_sdk", "costing.py"),
)


def check_compile():
    for path in COMPILE_TARGETS:
        if not os.path.exists(path):
            print(f"[1/4] 跳过（文件不存在）：{path}")
            continue
        py_compile.compile(path, doraise=True)
    print("[1/4] 语法检查通过：" + ", ".join(os.path.basename(p) for p in COMPILE_TARGETS))


def check_gui():
    import app
    rc = app.main(["--smoke-gui"])
    print(f"[2/4] 界面构建返回码：{rc}")
    return rc


def check_login():
    pwd = os.getenv("KINGDEE_PASSWORD", "")
    if not pwd:
        print("[3/4] 跳过登录自检（未提供 KINGDEE_PASSWORD）")
        return 0
    import selfcheck
    ok, msg = selfcheck.run_selfcheck(os.getenv("KINGDEE_USERNAME", ""), pwd)
    print(f"[3/4] 登录自检：{'通过' if ok else '未通过'} {msg}")
    return 0 if ok else 1


def check_costing(month, limit):
    pwd = os.getenv("KINGDEE_PASSWORD", "")
    if not pwd or not month:
        print("[4/4] 跳过核算验证（需要 KINGDEE_PASSWORD 与 --month）")
        return 0
    import app
    out = os.path.join(tempfile.gettempdir(), f"smoke_costing_{month}.xlsx")
    ok, msg, _path, rows = app.run_costing_once(
        os.getenv("KINGDEE_USERNAME", ""), pwd, month, "未税", None,
        limit=limit, out_path=out, log=lambda t: print("      " + str(t)),
    )
    print(f"[4/4] 核算验证：{'通过' if ok else '未通过'} {msg}")
    if ok and rows:
        first = rows[0]
        print(f"      首条：{first['销售单号']} {first['产品编码']} 数量 {first['数量']:g} "
              f"售价(人民币) {first['售价(人民币)']:.4f} 料本 {first['总料本(人民币)']:,.2f} "
              f"毛利 {first['毛利(人民币)']:,.2f} 子件 {first['子件数']} {first['备注'] or ''}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="打包前冒烟验证")
    ap.add_argument("--month", default="", help="核算验证用月份，如 2026-09")
    ap.add_argument("--limit", type=int, default=3, help="核算验证取多少条销售记录")
    args = ap.parse_args()

    check_compile()
    rc_gui = check_gui()
    rc_login = check_login()
    rc_costing = check_costing(args.month, args.limit)
    ok = all(rc == 0 for rc in (rc_gui, rc_login, rc_costing))
    print("\n== 冒烟验证" + ("全部通过 ==" if ok else "存在失败，请看上面输出 =="))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
