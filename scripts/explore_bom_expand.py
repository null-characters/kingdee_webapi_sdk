#!/usr/bin/env python3
"""
BOM 展开与实现方式探测（只读）：

1. 把上一步导出的 bom_view_full.json 里的 TreeEntity（子件）拍平成 CSV，看清用量字段
2. 试探 ExecuteBillQuery 能不能直接取 ENG_BOM 的子件字段（决定实现方式：查询 vs View）
3. 检查每个第一层子件是否还有自己的 BOM（判断是否多层展开）
4. 用第一层子件物料编码去查采购订单的含税单价/总价（成本侧取数验证）

用法：
    KINGDEE_PASSWORD='xxx' python3 scripts/explore_bom_expand.py [父项物料编码]
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kingdee_sdk import KingdeeClient, KingdeeAPIError, load_kingdee_config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_DIR = os.path.join(ROOT, "data", "sample_export")
PARENT = "1.LA.LE.001083"  # 航空应急灯

PUR_FIELDS = (
    "FBillNo,FDate,FDocumentStatus,FMaterialId.FNumber,FMaterialId.FName,FQty,"
    "FTaxPrice,FPrice,FEntryTaxRate,FAllAmount,FAmount,FSupplierId.FName"
)

# ExecuteBillQuery 取 BOM 子件字段的候选写法（账套元数据里出现的是表列名风格 FMATERIALIDCOBY）
QUERY_CANDIDATES = [
    "FNumber,FMaterialId.FNumber,FMaterialIdCoby.FNumber,FNumerator,FDenominator",
    "FNumber,FMaterialId.FNumber,FMaterialIdCoby.FNumber,FQtyCoby",
    "FNumber,FMaterialId.FNumber,FMATERIALIDCOBY,FNUMERATOR,FDENOMINATOR",
    "FNumber,FMaterialId.FNumber,FTreeEntity_FMaterialIdCoby.FNumber",
]


def find_key(node, key):
    """在嵌套 JSON 里找第一个名为 key 的值"""
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for v in node.values():
            r = find_key(v, key)
            if r is not None:
                return r
    elif isinstance(node, list):
        for v in node:
            r = find_key(v, key)
            if r is not None:
                return r
    return None


def zh_name(field):
    """取多语言字段里的 2052（简体中文）值"""
    if isinstance(field, list):
        for item in field:
            if isinstance(item, dict) and item.get("Key") == 2052:
                return item.get("Value")
    return ""


def flatten_tree(rows):
    flat = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        child = r.get("MATERIALIDCHILD") or {}
        unit = r.get("CHILDUNITID") or {}
        item = {
            "Seq": r.get("Seq"),
            "RowId": r.get("RowId"),
            "child_code": child.get("Number") if isinstance(child, dict) else None,
            "child_name": zh_name(child.get("Name")) if isinstance(child, dict) else "",
            "child_unit": unit.get("Number") if isinstance(unit, dict) else None,
        }
        for k, v in r.items():
            if k in ("MATERIALIDCHILD", "CHILDUNITID", "Id", "RowId", "Seq"):
                continue
            u = k.upper()
            if "UMERAT" in u or "ENOMINAT" in u or "QTY" in u or "SCRAP" in u or "RATE" in u:
                item[k] = v if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False)
        flat.append(item)
    return flat


def save_csv(name, rows, header=None):
    if not rows:
        return None
    header = header or list(rows[0].keys())
    path = os.path.join(SAMPLE_DIR, name)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def main():
    parent = sys.argv[1] if len(sys.argv) > 1 else PARENT
    os.makedirs(SAMPLE_DIR, exist_ok=True)

    # ---------- 1) 拍平 BOM 子件 ----------
    view_path = os.path.join(SAMPLE_DIR, "bom_view_full.json")
    print(f"[读取] {view_path}")
    with open(view_path, encoding="utf-8") as f:
        view = json.load(f)

    tree = find_key(view, "TreeEntity") or []
    flat = flatten_tree(tree)
    print(f"\n1) BOM 子项（TreeEntity）共 {len(flat)} 行")

    qty_keys = []
    for r in flat:
        for k in r:
            if k not in ("Seq", "RowId", "child_code", "child_name", "child_unit") and k not in qty_keys:
                qty_keys.append(k)
    print(f"   用量/损耗类字段: {qty_keys}")
    print("   前 6 行：")
    for r in flat[:6]:
        brief = {k: r.get(k) for k in qty_keys}
        print(f"     Seq={r['Seq']:>3}  {str(r['child_code']):<20} {str(r['child_name'])[:24]:<26} {brief}")
    p = save_csv("bom_children_flat.csv", flat)
    print(f"   ✅ 已保存 {os.path.relpath(p, os.getcwd())}")

    # ---------- 2) 试探查询接口能否直接取子件 ----------
    cfg = load_kingdee_config()
    if not cfg.get("password"):
        print("[配置缺失] 需要 KINGDEE_PASSWORD")
        return 1
    client = KingdeeClient(
        server_url=cfg["server_url"], acct_id=cfg["acct_id"], username=cfg["username"],
        password=cfg["password"], auth_type=cfg["auth_type"],
    )
    client.login()
    print(f"\n[登录成功] {cfg['username']}")

    print("\n2) ExecuteBillQuery 直接取 ENG_BOM 子件字段的可行性")
    for keys in QUERY_CANDIDATES:
        try:
            rows = client.execute_bill_query(
                form_id="ENG_BOM", field_keys=keys,
                filter_string=f"FMaterialId.FNumber='{parent}'", limit=5,
            )
            rows = [r for r in rows if isinstance(r, (list, tuple))]
            print(f"   ✅ 可用: {keys}")
            print(f"      列: {[k.strip() for k in keys.split(',')]}")
            for r in rows[:3]:
                print(f"      {r}")
            save_csv(
                "bom_query_by_child_fields.csv",
                [dict(zip([k.strip() for k in keys.split(",")], r)) for r in rows],
            )
            break
        except KingdeeAPIError as exc:
            print(f"   ❌ 不可用: {keys}\n      原因: {exc}")

    # ---------- 3) 子件是否还有自己的 BOM（判断层数） ----------
    codes = [r["child_code"] for r in flat if r.get("child_code")]
    print(f"\n3) 第一层子件是否还有自己的 BOM（判断是否多层展开，共 {len(codes)} 个）")
    for code in codes:
        try:
            rows = client.execute_bill_query(
                form_id="ENG_BOM", field_keys="FNumber,FMaterialId.FNumber,FDocumentStatus",
                filter_string=f"FMaterialId.FNumber='{code}'", limit=2,
            )
            rows = [r for r in rows if isinstance(r, (list, tuple)) and any(v for v in r)]
            tag = "有 BOM: " + ", ".join(str(r[0]) for r in rows) if rows else "无 BOM（叶子/采购件）"
            print(f"   {str(code):<20} -> {tag}")
        except KingdeeAPIError as exc:
            print(f"   {str(code):<20} -> 查询失败: {exc}")

    # ---------- 4) 子件的采购价 ----------
    print("\n4) 第一层子件的采购订单价格（含税单价/价税合计）")
    if codes:
        in_list = ",".join(f"'{c}'" for c in codes)
        try:
            rows = client.execute_bill_query(
                form_id="PUR_PurchaseOrder", field_keys=PUR_FIELDS,
                filter_string=f"FDocumentStatus='C' and FMaterialId.FNumber in ({in_list})",
                order_string="FID DESC", limit=100,
            )
            rows = [r for r in rows if isinstance(r, (list, tuple))]
            header = [k.strip() for k in PUR_FIELDS.split(",")]
            print(f"   ✅ {len(rows)} 行")
            for r in rows[:8]:
                print(f"      {r}")
            p = save_csv(
                "purchase_by_child_codes.csv",
                [dict(zip(header, r)) for r in rows], header=header,
            )
            if p:
                print(f"   ✅ 已保存 {os.path.relpath(p, os.getcwd())}")
        except KingdeeAPIError as exc:
            print(f"   ❌ 查询失败: {exc}")

    client.logout()
    print(f"\n[已登出] 产物目录 {SAMPLE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
