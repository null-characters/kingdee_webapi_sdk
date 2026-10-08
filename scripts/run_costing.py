#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行跑成本核算并导出 Excel（正式使用走 windows_tool 的图形界面）。

流程和界面一致：
    扫描缺价子件 → 把缺价料号预填进维护表 CSV → 还有没填的就不导出（退出码 2）
    → 财务在 CSV 里填完单价 → 再跑一次（或加 --recheck 用上次快照重算）→ 导出

用法：
    # 整月
    KINGDEE_PASSWORD='xxx' python3 scripts/run_costing.py --month 2026-09
    # 任意区间（例如本月 5 号到 15 号）
    KINGDEE_PASSWORD='xxx' python3 scripts/run_costing.py --from 2026-09-05 --to 2026-09-15
    # 常用开关
    #   --tax 含税              含税口径（默认未税）
    #   --rate 6.7809           外币整批按这个汇率折算（默认用单据自带汇率）
    #   --manual-table PATH     指定维护表 CSV（默认自动定位）
    #   --allow-missing         仍有缺价也导出（按 0 计并在备注/表里标注）
    #   --recheck               不登录金蝶，用上次快照 + 最新维护表重算后导出

    退出码：0 成功导出；1 参数/运行错误；2 缺价子件未补齐（已更新维护表、未导出）
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kingdee_sdk import KingdeeClient, load_kingdee_config
from kingdee_sdk.costing import (
    TAX_MODES,
    CostingCalculator,
    CostingError,
    check_recalc_compatible,
    export_xlsx,
    load_snapshot,
    month_range,
    normalize_range,
    range_file_label,
    range_label,
    recalculate,
    save_snapshot,
)
from kingdee_sdk.manual_prices import ManualPriceError, ManualPriceTable

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NEED_PRICE = 2


def build_parser():
    ap = argparse.ArgumentParser(description="按财务口径核算某区间的料本与毛利")
    ap.add_argument("--month", default="", help="整月，如 2026-09")
    ap.add_argument("--from", dest="date_from", default="", help="起始日期，如 2026-09-05")
    ap.add_argument("--to", dest="date_to", default="", help="结束日期，如 2026-09-15")
    ap.add_argument("--tax", default="未税", choices=list(TAX_MODES), help="计价方式（默认未税）")
    ap.add_argument("--rate", type=float, default=None,
                    help="覆盖汇率（外币整批折算）；不填则用单据自带汇率")
    ap.add_argument("--limit", type=int, default=1000, help="最多取多少条销售记录")
    ap.add_argument("--out", default=None, help="输出 xlsx 路径")
    ap.add_argument("--manual-table", default=None, help="采购价维护表 CSV 路径")
    ap.add_argument("--allow-missing", action="store_true",
                    help="仍有缺价子件时也导出（按 0 计并标注）")
    ap.add_argument("--recheck", action="store_true",
                    help="不登录金蝶，用上次快照 + 最新维护表重算并导出")
    ap.add_argument("--list-missing", action="store_true",
                    help="只扫描并列印缺价子件（不导出）")
    return ap


def resolve_period(args):
    if args.month and (args.date_from or args.date_to):
        raise CostingError("--month 和 --from/--to 只能用一个")
    if args.month:
        return month_range(args.month)
    if args.date_from or args.date_to:
        if not (args.date_from and args.date_to):
            raise CostingError("--from 和 --to 要同时给")
        return normalize_range(args.date_from, args.date_to)
    raise CostingError("请用 --month 2026-09 或 --from/--to 指定统计区间")


def print_missing(run, table):
    print(f"\n⚠ 有 {len(run.missing)} 个子件缺采购价，已把料号预填进维护表：")
    print(f"   {table.path}")
    print(f"\n   {'子件编码':<22}{'子件名称':<20}{'单位':<8}{'出现':>5}{'产品':>5}  说明")
    for m in run.missing[:40]:
        print(f"   {str(m['子件编码']):<22}{str(m['子件名称'])[:18]:<20}"
              f"{str(m['单位']):<8}{m['出现次数']:>5}{m['涉及产品数']:>5}  {m['说明']}")
    if len(run.missing) > 40:
        print(f"   …… 其余 {len(run.missing) - 40} 个请看维护表或导出的 Excel")
    print(f"\n请用 Excel 打开维护表，在这些行的「未税单价 / 含税单价」里填价，"
          f"然后重新运行：")
    print(f"   python3 scripts/run_costing.py --recheck")


def export(run, args, table, out_path):
    if out_path is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        stamp = f"costing_{range_file_label(run.meta['起始日期'], run.meta['结束日期'])}_{args.tax}"
        if not run.complete:
            stamp += "_含缺价"
        out_path = os.path.join(root, "data", "sample_export", stamp + ".xlsx")
    export_xlsx(out_path, run, extra_meta={"缺价子件": len(run.missing)})
    return out_path


def main(argv=None):
    args = build_parser().parse_args(argv)
    table = ManualPriceTable(args.manual_table).load()
    if table.error:
        print(f"[维护表告警] {table.error}")
    if table.duplicates:
        print(f"[维护表告警] 有重复料号（只用第一条）：{'、'.join(table.duplicates[:10])}")

    try:
        date_from, date_to = resolve_period(args)
    except CostingError as exc:
        print(f"[参数错误] {exc}")
        return EXIT_ERROR

    print(f"[区间] {range_label(date_from, date_to)}    计价 {args.tax}"
          f"{'    覆盖汇率 ' + str(args.rate) if args.rate else ''}")

    # ---------- 套用上次快照重算（不登录）----------
    if args.recheck:
        try:
            base = load_snapshot()
        except CostingError as exc:
            print(f"[无法重算] {exc}")
            return EXIT_ERROR
        problem = check_recalc_compatible(base.meta, args.tax, args.rate)
        if problem:
            print(f"[口径不一致] {problem}")
            return EXIT_ERROR
        print(f"[快照] 用上次取数（{base.meta.get('期间')}）重算：{base.snapshot_path}")
        run = recalculate(base, table, override_rate=args.rate)
        date_from = str(run.meta.get("起始日期") or date_from)
        date_to = str(run.meta.get("结束日期") or date_to)
    else:
        cfg = load_kingdee_config()
        if not cfg.get("password"):
            print("[配置缺失] 需要 KINGDEE_PASSWORD")
            return EXIT_ERROR
        client = KingdeeClient(
            server_url=cfg["server_url"], acct_id=cfg["acct_id"], username=cfg["username"],
            password=cfg["password"], auth_type=cfg["auth_type"],
        )
        print(f"[登录] {cfg['username']}")
        client.login()
        try:
            calc = CostingCalculator(client, tax_mode=args.tax, override_rate=args.rate,
                                     manual_table=table, log=print)
            run = calc.run(date_from, date_to, limit=args.limit)
        finally:
            client.logout()

        # 缺价料号预填进维护表（长期产物）
        stats = table.add_missing(run.missing)
        if stats["added"] or stats["backfilled"]:
            try:
                table.save()
                print(f"[维护表] 新增缺价料号 {stats['added']} 行，补全名称/单位 "
                      f"{stats['backfilled']} 行 → {table.path}")
            except ManualPriceError as exc:
                print(f"[维护表告警] {exc}")
        try:
            save_snapshot(run)
            print(f"[快照] 已保存，补价后可用 --recheck 秒级重算")
        except OSError as exc:
            print(f"[快照告警] 保存失败：{exc}")

    # ---------- 汇总 ----------
    t = run.totals()
    print(f"\n共 {len(run.summary)} 条销售记录；子件明细 {len(run.details)} 行")
    for row in run.summary[:6]:
        print(f"  {row['销售单号']} {row['单据日期']} {row['币别']:<4} {row['产品编码']:<18}"
              f" 数量 {row['数量']:>8g}  售价(人民币) {row['售价(人民币)']:>12,.4f}"
              f"  自动料本 {row['自动料本(人民币)']:>12,.2f}"
              f"  手工维护 {row['手工维护料本(人民币)']:>10,.2f}"
              f"  最终 {row['最终料本(人民币)']:>12,.2f}"
              f"  毛利 {row['毛利(人民币)']:>12,.2f}  {row['备注']}")
    print(f"\n合计：销售额 {t['销售额']:,.2f}  自动料本 {t['自动料本']:,.2f}"
          f"  手工维护料本 {t['手工维护料本']:,.2f}  最终料本 {t['最终料本']:,.2f}"
          f"  毛利 {t['毛利']:,.2f}  毛利率 {t['毛利率'] * 100:.1f}%")
    print(f"维护表：{table.summary_text()}    维护表位置：{table.path}")

    if run.stale:
        print(f"\n提示：维护表里有 {len(run.stale)} 个子件金蝶现在已经能取到价"
              f"（本次按金蝶价算），可考虑删除这些行："
              f"{'、'.join(s['子件编码'] for s in run.stale[:10])}")

    # ---------- 卡口：缺价没补齐就不导出 ----------
    if not run.complete:
        print_missing(run, table)
        if not args.allow_missing:
            print(f"\n[未导出] 还有 {len(run.missing)} 个子件缺采购价。"
                  f"补齐后重跑（或用 --allow-missing 强制导出，缺价部分按 0 计）。")
            return EXIT_NEED_PRICE
        print(f"\n[--allow-missing] 仍有 {len(run.missing)} 个子件缺价，按 0 计并标注后导出。")

    if args.list_missing:
        print("\n[--list-missing] 只扫描不导出。")
        return EXIT_OK if run.complete else EXIT_NEED_PRICE

    out = export(run, args, table, args.out)
    print(f"\n已导出 Excel：{out}")
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CostingError as exc:
        print(f"[核算失败] {exc}")
        sys.exit(EXIT_ERROR)
