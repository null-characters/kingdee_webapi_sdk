# -*- coding: utf-8 -*-
"""打包前冒烟验证（开发者自查用，正式打包时可以不带上这个文件）

依次做六件事：
    1. 语法编译检查 app.py / selfcheck.py / kingdee_sdk/costing.py / manual_prices.py
    2. 构建一次主界面后立刻销毁（等价于 --smoke-gui）
    3. 构建一次「缺价补全」对话框（等价于 --smoke-dialog）
    4. 跑离线逻辑自检 scripts/verify_costing_offline.py（假客户端，不需要内网）
    5. 若提供了口令：真实登录 + 三表单自检（只读查询）
    6. 若提供了口令和区间：真实核算 + 导出 xlsx（缺价会一并列出，导出带「含缺价」标注）

用法：
    PYTHONDONTWRITEBYTECODE=1 python3 _smoke_check.py
    PYTHONDONTWRITEBYTECODE=1 KINGDEE_PASSWORD=xxx python3 _smoke_check.py --month 2026-09 --limit 3
    PYTHONDONTWRITEBYTECODE=1 KINGDEE_PASSWORD=xxx python3 _smoke_check.py --from 2026-09-05 --to 2026-09-15

提示：维护表/快照默认落在仓库根的「成本核算数据」目录（已在 .gitignore 里）。
      想换位置就设环境变量 KINGDEE_COSTING_DATA_DIR。
"""

import argparse
import os
import py_compile
import subprocess
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
    os.path.join(ROOT, "kingdee_sdk", "manual_prices.py"),
)

STEPS = 6


def check_compile():
    for path in COMPILE_TARGETS:
        if not os.path.exists(path):
            print(f"[1/{STEPS}] 跳过（文件不存在）：{path}")
            continue
        py_compile.compile(path, doraise=True)
    print(f"[1/{STEPS}] 语法检查通过："
          + ", ".join(os.path.basename(p) for p in COMPILE_TARGETS))


def check_gui():
    import app
    rc = app.main(["--smoke-gui"])
    print(f"[2/{STEPS}] 主界面构建返回码：{rc}")
    return rc


def check_dialog():
    import app
    rc = app.main(["--smoke-dialog"])
    print(f"[3/{STEPS}] 缺价补全对话框返回码：{rc}")
    return rc


def check_offline():
    script = os.path.join(ROOT, "scripts", "verify_costing_offline.py")
    if not os.path.exists(script):
        print(f"[4/{STEPS}] 跳过离线自检（找不到 {script}）")
        return 0
    proc = subprocess.run([sys.executable, script], capture_output=True, text=True)
    tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()][-1:]
    print(f"[4/{STEPS}] 离线逻辑自检：{'通过' if proc.returncode == 0 else '未通过'}"
          f"（{' '.join(tail)}）")
    if proc.returncode != 0:
        print(proc.stdout[-3000:])
        print(proc.stderr[-2000:])
    return proc.returncode


def check_login():
    pwd = os.getenv("KINGDEE_PASSWORD", "")
    if not pwd:
        print(f"[5/{STEPS}] 跳过登录自检（未提供 KINGDEE_PASSWORD）")
        return 0
    import selfcheck
    ok, msg = selfcheck.run_selfcheck(os.getenv("KINGDEE_USERNAME", ""), pwd)
    print(f"[5/{STEPS}] 登录自检：{'通过' if ok else '未通过'} {msg}")
    return 0 if ok else 1


def check_costing(date_from, date_to, limit, tax):
    """真实核算：扫描 → 缺价预填维护表 → 套用维护表重算 → 导出（缺价也导出，便于看输出）"""
    pwd = os.getenv("KINGDEE_PASSWORD", "")
    if not pwd or not (date_from and date_to):
        print(f"[6/{STEPS}] 跳过核算验证（需要 KINGDEE_PASSWORD 与 --month 或 --from/--to）")
        return 0
    import app

    user = os.getenv("KINGDEE_USERNAME", "")
    print(f"      · 扫描 {date_from} ~ {date_to}（计价 {tax}）……")
    ok, msg, run, table = app.scan_once(user, pwd, date_from, date_to, tax, None,
                                       limit=limit, log=lambda t: None)
    if not ok:
        print(f"[6/{STEPS}] 核算验证：未通过 {msg}")
        return 1
    print(f"      · 记录 {len(run.summary)} 条，子件明细 {len(run.details)} 行，"
          f"缺价子件 {len(run.missing)} 个")
    print(f"      · 维护表：{table.path}（{table.summary_text()}）")
    if run.missing:
        for m in run.missing[:5]:
            print(f"        缺价：{m['子件编码']:<22}{str(m['子件名称'])[:16]:<18}{m['说明']}")
        if len(run.missing) > 5:
            print(f"        其余 {len(run.missing) - 5} 个见维护表")
        # 再走一次「重新检查」，验证补价链路（填了价的会立刻计入手工维护料本）
        ok2, msg2, run2, _t = app.recheck_once(run, tax, None, table.path, log=lambda t: None)
        if ok2:
            run = run2
            print(f"      · 套用维护表重算：仍缺 {len(run.missing)} 个，"
                  f"手工维护料本 {run.totals()['手工维护料本']:,.2f}")

    out = os.path.join(tempfile.gettempdir(), f"smoke_costing_{date_from}_{date_to}_{tax}.xlsx")
    ok3, msg3, _path = app.export_run_once(run, out, log=lambda t: None)
    print(f"[6/{STEPS}] 核算验证：{'通过' if ok3 else '未通过'} {msg3.splitlines()[0]}")
    t = run.totals()
    print(f"      合计：销售额 {t['销售额']:,.2f}  自动料本 {t['自动料本']:,.2f}  "
          f"手工维护料本 {t['手工维护料本']:,.2f}  最终料本 {t['最终料本']:,.2f}  "
          f"毛利 {t['毛利']:,.2f}")
    return 0 if ok3 else 1


def main():
    ap = argparse.ArgumentParser(description="打包前冒烟验证")
    ap.add_argument("--month", default="", help="核算验证用整月，如 2026-09")
    ap.add_argument("--from", dest="date_from", default="", help="核算验证起始日期")
    ap.add_argument("--to", dest="date_to", default="", help="核算验证结束日期")
    ap.add_argument("--tax", default="未税", choices=["未税", "含税"], help="计价方式")
    ap.add_argument("--limit", type=int, default=3, help="核算验证取多少条销售记录")
    args = ap.parse_args()

    from kingdee_sdk.costing import month_range, normalize_range
    from kingdee_sdk.manual_prices import resolve_data_dir, resolve_snapshot_path, resolve_table_path

    date_from = date_to = ""
    if args.month:
        date_from, date_to = month_range(args.month)
    elif args.date_from and args.date_to:
        date_from, date_to = normalize_range(args.date_from, args.date_to)

    print(f"数据目录（维护表/快照）：{resolve_data_dir()}")
    print(f"  · 维护表：{resolve_table_path()}")
    print(f"  · 快照：  {resolve_snapshot_path()}\n")

    check_compile()
    rc_gui = check_gui()
    rc_dialog = check_dialog()
    rc_offline = check_offline()
    rc_login = check_login()
    rc_costing = check_costing(date_from, date_to, args.limit, args.tax)
    ok = all(rc == 0 for rc in (rc_gui, rc_dialog, rc_offline, rc_login, rc_costing))
    print("\n== 冒烟验证" + ("全部通过 ==" if ok else "存在失败，请看上面输出 =="))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
