#!/usr/bin/env python3
"""
命令行跑成本核算并导出 Excel（用于验证取数与试算，正式使用走 windows_tool）。

用法：
    KINGDEE_PASSWORD='xxx' python3 scripts/run_costing.py --month 2026-09 \
        [--tax 未税|含税] [--rate 6.7809] [--limit 20] [--out 输出.xlsx]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kingdee_sdk import KingdeeClient, load_kingdee_config
from kingdee_sdk.costing import TAX_MODES, CostingCalculator, export_xlsx, month_range


def main():
    ap = argparse.ArgumentParser(description="按财务口径核算某月销售记录的料本与毛利")
    ap.add_argument("--month", required=True, help="结算月份，如 2026-09")
    ap.add_argument("--tax", default="未税", choices=list(TAX_MODES), help="计价方式（默认未税）")
    ap.add_argument("--rate", type=float, default=None, help="覆盖汇率（外币整批折算）；不填则用单据自带汇率")
    ap.add_argument("--limit", type=int, default=1000, help="最多取多少条销售记录")
    ap.add_argument("--out", default=None, help="输出 xlsx 路径")
    args = ap.parse_args()

    cfg = load_kingdee_config()
    if not cfg.get("password"):
        print("[配置缺失] 需要 KINGDEE_PASSWORD")
        return 1

    date_from, date_to = month_range(args.month)
    print(f"[登录] {cfg['username']}    期间 {date_from} ~ {date_to}    计价 {args.tax}"
          f"{'    覆盖汇率 ' + str(args.rate) if args.rate else ''}")

    client = KingdeeClient(
        server_url=cfg["server_url"], acct_id=cfg["acct_id"], username=cfg["username"],
        password=cfg["password"], auth_type=cfg["auth_type"],
    )
    client.login()

    calc = CostingCalculator(client, tax_mode=args.tax, override_rate=args.rate, log=print)
    summary, details = calc.run(date_from, date_to, limit=args.limit)
    client.logout()

    print(f"\n共 {len(summary)} 条销售记录；子件明细 {len(details)} 行")
    for row in summary[:6]:
        print(
            f"  {row['销售单号']} {row['单据日期']} {row['币别']:<4} {row['产品编码']:<18}"
            f" 数量 {row['数量']:>8g}  售价(人民币) {row['售价(人民币)']:>12,.4f}"
            f"  料本 {row['总料本(人民币)']:>12,.2f}  毛利 {row['毛利(人民币)']:>12,.2f}"
            f"  子件 {row['子件数']:>3}  {row['备注']}"
        )

    if summary:
        sale = sum(r["销售额(人民币)"] for r in summary)
        cost = sum(r["总料本(人民币)"] for r in summary)
        gross = sale - cost
        print(f"\n合计：销售额 {sale:,.2f}  料本 {cost:,.2f}  毛利 {gross:,.2f}"
              f"  毛利率 {(gross / sale * 100) if sale else 0:.1f}%")
        with_note = [r for r in summary if r["备注"]]
        if with_note:
            print(f"有备注（需人工核对）的记录：{len(with_note)} 条")
            for r in with_note[:5]:
                print(f"  {r['销售单号']} {r['产品编码']}：{r['备注']}")

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = args.out or os.path.join(root, "data", "sample_export", f"costing_{args.month}_{args.tax}.xlsx")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    export_xlsx(out, summary, details, meta={
        "结算月份": args.month,
        "期间": f"{date_from} ~ {date_to}",
        "计价方式": args.tax,
        "汇率处理": "单据自带汇率" if not args.rate else f"整批按 {args.rate} 折算",
        "采购取价": "该物料最近一次已审核采购行的单价（不限时点）",
        "成本口径": "BOM 展开到无 BOM 的叶子件，按最近采购价 × 累计用量汇总",
        "数据来源": "金蝶云星空 WebAPI（只读查询）",
    })
    print(f"\n已导出 Excel：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
