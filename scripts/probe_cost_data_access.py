#!/usr/bin/env python3
"""
只读探针：确认账号对「销售订单 / 物料清单(成本查询) / 采购订单」的访问权限与字段名。

- 只执行 QueryBusinessInfo 与 ExecuteBillQuery（均为只读接口），不写任何账套数据
- 完整字段清单写入 /tmp/kingdee_fields_<form>.json，终端只打印摘要

用法：
    KINGDEE_PASSWORD='xxx' python3 scripts/probe_cost_data_access.py
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kingdee_sdk import KingdeeClient, KingdeeAPIError, load_kingdee_config

QUERY_BUSINESS_INFO = (
    "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.QueryBusinessInfo.common.kdsvc"
)

# 关注的字段关键词（含税单价 / 价税合计 / 金额 / 数量 / 物料 / 成本）
KEY_TOKENS = (
    "Price", "Amount", "Tax", "Qty", "Material", "Cost", "Number", "BillNo",
    "Unit", "Currency", "Rate", "Supplier", "Customer", "Date", "Status",
)

TARGET_FORMS = {
    "SAL_SaleOrder": "销售订单",
    "PUR_PurchaseOrder": "采购订单",
    "ENG_BOM": "物料清单",
}

# 物料清单成本查询的候选标识（账套里可能以报表/动态表单存在）
COST_QUERY_CANDIDATES = [
    "ENG_BOMCostQuery",
    "ENG_BomCostQuery",
    "ENG_BOMCost",
    "ENG_BOMCostRpt",
    "BOM_COST_QUERY",
    "ENG_BomExpandBill_B_R",
]


def collect_fields(node, out):
    """递归收集字段名：QueryBusinessInfo 的 Fields 数组用 FieldName 承载字段标识"""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and re.fullmatch(r"F[A-Za-z0-9_]{1,40}", k):
                out.add(k)
            if k in ("FieldName", "FieldKey", "Key") and isinstance(v, str):
                m = re.match(r"(F[A-Za-z0-9_]{1,40})", v)
                if m:
                    out.add(m.group(1))
            collect_fields(v, out)
    elif isinstance(node, list):
        for item in node:
            collect_fields(item, out)


def query_business_info(client, form_id):
    """QueryBusinessInfo：返回 (受理状态, 错误消息, 字段集合, 原始结果)"""
    raw = client._request(QUERY_BUSINESS_INFO, {"data": json.dumps({"FormId": form_id}, ensure_ascii=False)})
    with open(f"/tmp/kingdee_businessinfo_{form_id}.json", "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=1)
    joined = json.dumps(raw, ensure_ascii=False)
    err = None
    m = re.search(r'"Message"\s*:\s*"([^"]{1,200})"', joined)
    if m:
        err = m.group(1)
    ok = '"IsSuccess":true' in joined.replace(" ", "") or '"IsSuccess": true' in joined
    fields = set()
    collect_fields(raw, fields)
    return ok, err, fields, raw


def main():
    cfg = load_kingdee_config()
    missing = [k for k in ("server_url", "acct_id", "username") if not cfg.get(k)]
    if missing or not cfg.get("password"):
        print(f"[配置缺失] 需要环境变量：{missing} + KINGDEE_PASSWORD")
        return 1

    client = KingdeeClient(
        server_url=cfg["server_url"],
        acct_id=cfg["acct_id"],
        username=cfg["username"],
        password=cfg["password"],
        auth_type=cfg["auth_type"],
    )
    client.login()
    print(f"[登录成功] {cfg['username']} @ {cfg['server_url']} / 账套 {cfg['acct_id']}\n")

    print("=" * 72)
    print("1) 三个目标表单：对象是否存在 / 字段是否能取到")
    print("=" * 72)
    for form_id, label in TARGET_FORMS.items():
        try:
            ok, err, fields, raw = query_business_info(client, form_id)
            payload = {k: v for k, v in raw.items() if k != "Result"} if isinstance(raw, dict) else {}
            table = ""
            m = re.search(r'"TableName"\s*:\s*"([^"]+)"', json.dumps(raw, ensure_ascii=False))
            if m:
                table = m.group(1)
            tag = "✅ 可访问" if ok else "❌ 拒绝/报错"
            print(f"\n[{form_id}] {label}：{tag}  表名={table or '未取到'}")
            if err:
                print(f"    消息: {err}")
            print(f"    字段数: {len(fields)}")
            if fields:
                with open(f"/tmp/kingdee_fields_{form_id}.json", "w", encoding="utf-8") as f:
                    json.dump(sorted(fields), f, ensure_ascii=False, indent=1)
                hits = sorted(x for x in fields if any(t in x for t in KEY_TOKENS))
                print(f"    关键字段({len(hits)}): {', '.join(hits)}")
                print(f"    完整清单: /tmp/kingdee_fields_{form_id}.json")
            if payload:
                print(f"    其他返回键: {list(payload)[:8]}")
        except Exception as exc:  # noqa: BLE001
            print(f"\n[{form_id}] {label}：❌ 调用异常 -> {exc}")

        # 读权限 + 数据量
        try:
            rows = client.execute_bill_query(form_id=form_id, field_keys="FID", limit=1)
            print(f"    查询(FID, limit=1): ✅ 返回 {len(rows)} 行 -> {rows}")
        except KingdeeAPIError as exc:
            print(f"    查询(FID, limit=1): ❌ {exc}")

    print("\n" + "=" * 72)
    print("2) 「物料清单成本查询」候选标识探测（是否存在该业务对象）")
    print("=" * 72)
    for cand in COST_QUERY_CANDIDATES:
        try:
            ok, err, fields, _raw = query_business_info(client, cand)
            print(f"  {cand:28s} -> {'存在/可访问 ✅ 字段数=%d' % len(fields) if ok else '不存在或无权 ❌ %s' % (err or '')}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {cand:28s} -> 调用异常: {exc}")

    print("\n" + "=" * 72)
    print("3) 单据类型与样例单据编号（判断实际在用的是哪种单据类型）")
    print("=" * 72)
    type_fields = {
        "SAL_SaleOrder": "FBillNo,FBillTypeID.FNumber,FBillTypeID.FName,FDocumentStatus,FDate",
        "PUR_PurchaseOrder": "FBillNo,FBillTypeID.FNumber,FBillTypeID.FName,FDocumentStatus,FDate",
        "ENG_BOM": "FNumber,FMaterialId.FNumber,FMaterialId.FName,FDocumentStatus",
    }
    for form_id, keys in type_fields.items():
        try:
            rows = client.execute_bill_query(
                form_id=form_id, field_keys=keys, order_string="FID DESC", limit=3
            )
            print(f"\n[{form_id}] {keys}")
            for r in rows:
                print(f"    {r}")
        except KingdeeAPIError as exc:
            print(f"\n[{form_id}] ❌ {exc}")

    client.logout()
    print("\n[已登出] 探针结束")
    return 0


if __name__ == "__main__":
    sys.exit(main())
