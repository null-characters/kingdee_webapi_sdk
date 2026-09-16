#!/usr/bin/env python3
"""
币别与汇率折算的只读探测（承接 explore_pricing_rules.py 的结论）：

要弄清三点：
    1. BD_Currency（币别基础资料）里有哪些币别、哪个是人民币本位币
    2. 销售/采购订单里结算币别（FSettleCurrId）的实际分布，美元单据多不多
    3. 外币单据上「单价 × 数量 = 金额」等式是否成立、是原币还是本位币
       —— 决定人民币单价到底怎么算：FPrice × FExchangeRate，还是直接用 FAmount_LC / FQty

用法：
    KINGDEE_PASSWORD='xxx' python3 scripts/explore_currency.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kingdee_sdk import KingdeeAPIError, KingdeeClient, load_kingdee_config


def show(client, label, form_id, field_keys, filter_string=None, order_string=None, limit=3):
    print(f"\n  ▸ {label}")
    try:
        rows = client.execute_bill_query(
            form_id=form_id, field_keys=field_keys,
            filter_string=filter_string, order_string=order_string, limit=limit,
        )
        rows = [r for r in rows if isinstance(r, (list, tuple))]
        print(f"    列：{[k.strip() for k in field_keys.split(',')]}")
        for r in rows:
            print(f"    {r}")
        return rows
    except KingdeeAPIError as exc:
        print(f"    ❌ {exc}")
        return []


def main():
    cfg = load_kingdee_config()
    if not cfg.get("password"):
        print("[配置缺失] 需要 KINGDEE_PASSWORD")
        return 1
    client = KingdeeClient(
        server_url=cfg["server_url"], acct_id=cfg["acct_id"], username=cfg["username"],
        password=cfg["password"], auth_type=cfg["auth_type"],
    )
    client.login()
    print(f"[登录成功] {cfg['username']}")

    print("\n" + "=" * 72)
    print("1) 币别基础资料 BD_Currency")
    print("=" * 72)
    show(client, "币别清单（全部）", "BD_Currency", "FNumber,FName", limit=30)

    print("\n" + "=" * 72)
    print("2) 销售订单的结算币别分布（最近 200 行已审核）")
    print("=" * 72)
    try:
        rows = client.execute_bill_query(
            form_id="SAL_SaleOrder", field_keys="FSettleCurrId.FNumber,FBillNo",
            filter_string="FDocumentStatus='C'", order_string="FID DESC", limit=200,
        )
        rows = [r for r in rows if isinstance(r, (list, tuple))]
        stat = {}
        for r in rows:
            stat[r[0]] = stat.get(r[0], 0) + 1
        for k, v in sorted(stat.items(), key=lambda x: -x[1]):
            print(f"    结算币别 {k}: {v} 行")
        print(f"    合计 {len(rows)} 行")
    except KingdeeAPIError as exc:
        print(f"    ❌ {exc}")

    print("\n" + "=" * 72)
    print("3) 外币单据的单价与折算关系（原币 vs 本位币）")
    print("=" * 72)
    keys = ("FBillNo,FDate,FSettleCurrId.FNumber,FExchangeRate,FMaterialId.FNumber,FQty,"
            "FPrice,FTaxPrice,FAmount,FAllAmount,FAmount_LC,FAllAmount_LC,FPriceUnitQty")
    show(client, "销售订单：外币行明细", "SAL_SaleOrder", keys,
         filter_string="FExchangeRate <> 1", order_string="FID DESC", limit=3)
    show(client, "销售订单：人民币行明细（对照）", "SAL_SaleOrder", keys,
         filter_string="FExchangeRate = 1", order_string="FID DESC", limit=2)
    show(client, "采购订单：外币行明细", "PUR_PurchaseOrder", keys,
         filter_string="FExchangeRate <> 1", order_string="FID DESC", limit=3)
    show(client, "采购订单：人民币行明细（对照）", "PUR_PurchaseOrder", keys,
         filter_string="FExchangeRate = 1", order_string="FID DESC", limit=2)

    client.logout()
    print("\n[已登出]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
