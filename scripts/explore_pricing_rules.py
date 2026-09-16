#!/usr/bin/env python3
"""
按财务口径落实取数规则前的只读探测：

财务口径（2026-09）：
    1) 按月结算，每月内每条销售记录单独计算
    2) 采购价取「最近一次成交价」，默认按不含税算（含税/未税做成选项）
    3) 按销售结算币种：美元按「当月初汇率」折人民币，取销售的「单价」列

需要落实的技术点：
    A. 销售/采购订单里「币别」和「汇率」的字段名
    B. 账套里有没有汇率表对象（用于取「月初汇率」），没有的话只能退回订单自带汇率
    C. 账套里到底有没有外币单据（决定这条口径是否需要实现）
    D. 销售订单里的物料，有多少能对上 BOM 父项（决定成本能算出来的比例）
    E. 「最近一次成交价」按物料取最新已审核采购行的取数写法

用法：
    KINGDEE_PASSWORD='xxx' python3 scripts/explore_pricing_rules.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kingdee_sdk import KingdeeAPIError, KingdeeClient, load_kingdee_config

QUERY_BUSINESS_INFO = (
    "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.QueryBusinessInfo.common.kdsvc"
)

# A. 币别/汇率字段候选（金蝶不同版本命名有差异，逐个试）
CURRENCY_CANDIDATES = [
    "FCurrencyId.FNumber",
    "FCurrencyId.FName",
    "FCURRENCYID.FNumber",
    "FExchangeRate",
    "FExchangeTypeId.FNumber",
    "FSettleCurrId.FNumber",
    "FBaseCurrencyId.FNumber",
]

# B. 汇率表业务对象候选
EXCHANGE_FORM_CANDIDATES = [
    "BD_ExchangeRate",
    "BD_EXCHANGERATE",
    "BD_CurrencyRate",
    "BD_ExchangeRateEntry",
    "SEC_ExchangeRate",
    "BD_Currency",
]

# E. 用来验证「最近一次成交价」的采样物料（取自上一轮的真实子件）
SAMPLE_MATERIALS = ["3.J.Q01.000008", "3.B.G01.000012", "3.B.S01.001465"]


def try_fields(client, form_id, fields, label):
    print(f"\n  ▸ {label}（{form_id}）")
    for f in fields:
        try:
            rows = client.execute_bill_query(form_id=form_id, field_keys=f"FBillNo,{f}", limit=1)
            rows = [r for r in rows if isinstance(r, (list, tuple))]
            print(f"    ✅ {f:<28} 样例值：{rows[0][1] if rows else '(无数据)'}")
        except KingdeeAPIError as exc:
            print(f"    ❌ {f:<28} {exc}")
        except Exception as exc:
            print(f"    ❌ {f:<28} {exc}")


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

    # ---------- A. 币别 / 汇率字段 ----------
    print("\n" + "=" * 72)
    print("A) 销售/采购订单的币别与汇率字段名")
    print("=" * 72)
    try_fields(client, "SAL_SaleOrder", CURRENCY_CANDIDATES, "销售订单")
    try_fields(client, "PUR_PurchaseOrder", CURRENCY_CANDIDATES, "采购订单")

    # ---------- B. 汇率表对象是否存在 ----------
    print("\n" + "=" * 72)
    print("B) 账套里有没有「汇率」业务对象（决定月初汇率从哪取）")
    print("=" * 72)
    for form_id in EXCHANGE_FORM_CANDIDATES:
        try:
            raw = client._request(
                QUERY_BUSINESS_INFO, {"data": '{"FormId":"%s"}' % form_id}
            )
            txt = str(raw)
            ok = "IsSuccess" in txt and "true" in txt
            print(f"  {form_id:<24} -> {'存在 ✅' if ok else '存在但返回异常'}")
        except KingdeeAPIError as exc:
            print(f"  {form_id:<24} -> 不存在/无权 ❌（{exc}）")
        except Exception as exc:
            print(f"  {form_id:<24} -> 异常 {exc}")

    # ---------- C. 有没有外币单据 ----------
    print("\n" + "=" * 72)
    print("C) 账套里有没有外币单据（汇率 <> 1）")
    print("=" * 72)
    for form_id in ("SAL_SaleOrder", "PUR_PurchaseOrder"):
        try:
            rows = client.execute_bill_query(
                form_id=form_id,
                field_keys="FBillNo,FDate,FExchangeRate,FExchangeTypeId.FNumber",
                filter_string="FExchangeRate <> 1",
                order_string="FID DESC", limit=5,
            )
            rows = [r for r in rows if isinstance(r, (list, tuple))]
            print(f"  {form_id}：{len(rows)} 行")
            for r in rows:
                print(f"    {r}")
            if not rows:
                print("    （没有外币单据 → 汇率这条口径目前不影响结果）")
        except KingdeeAPIError as exc:
            print(f"  {form_id}：查询失败 {exc}")

    # ---------- D. 销售物料能否对上 BOM ----------
    print("\n" + "=" * 72)
    print("D) 销售订单里的物料，有多少能对上 BOM 父项（决定成本可算比例）")
    print("=" * 72)
    try:
        rows = client.execute_bill_query(
            form_id="SAL_SaleOrder",
            field_keys="FBillNo,FMaterialId.FNumber,FMaterialId.FName",
            filter_string="FDocumentStatus='C'", order_string="FID DESC", limit=100,
        )
        rows = [r for r in rows if isinstance(r, (list, tuple))]
        seen, mats = set(), []
        for r in rows:
            code = r[1]
            if code and code not in seen:
                seen.add(code)
                mats.append((code, r[2]))
        print(f"  最近 100 条已审核销售行里，去重后 {len(mats)} 个物料；逐个查 BOM：")
        with_bom, without = [], []
        for code, name in mats[:30]:
            try:
                bom = client.execute_bill_query(
                    form_id="ENG_BOM", field_keys="FNumber,FMaterialId.FNumber,FDocumentStatus",
                    filter_string=f"FMaterialId.FNumber='{code}'", limit=1,
                )
                bom = [r for r in bom if isinstance(r, (list, tuple)) and any(v for v in r)]
                (with_bom if bom else without).append(code)
                print(f"    {code:<20} {str(name)[:18]:<20} {'有 BOM: ' + str(bom[0][0]) if bom else '无 BOM'}")
            except KingdeeAPIError as exc:
                print(f"    {code:<20} 查询失败 {exc}")
        total = len(with_bom) + len(without)
        if total:
            print(f"  小结：抽查 {total} 个销售物料，有 BOM 的 {len(with_bom)} 个，无 BOM 的 {len(without)} 个")
    except KingdeeAPIError as exc:
        print(f"  查询失败：{exc}")

    # ---------- E. 「最近一次成交价」取数写法 ----------
    print("\n" + "=" * 72)
    print("E) 「最近一次成交价」取数验证（每物料最新一条已审核采购行，未税 FPrice）")
    print("=" * 72)
    for code in SAMPLE_MATERIALS:
        try:
            rows = client.execute_bill_query(
                form_id="PUR_PurchaseOrder",
                field_keys="FBillNo,FDate,FDocumentStatus,FMaterialId.FNumber,FQty,FPrice,FTaxPrice,FEntryTaxRate,FSrcBillNo",
                filter_string=f"FDocumentStatus='C' and FMaterialId.FNumber='{code}'",
                order_string="FID DESC", limit=1,
            )
            rows = [r for r in rows if isinstance(r, (list, tuple))]
            print(f"  {code}: {rows[0] if rows else '（该物料没有已审核采购记录）'}")
        except KingdeeAPIError as exc:
            print(f"  {code}: 查询失败 {exc}")

    client.logout()
    print("\n[已登出] 探测结束")
    return 0


if __name__ == "__main__":
    sys.exit(main())
