#!/usr/bin/env python3
"""
只读抽样：把一个真实产品在「销售订单 / 物料清单 / 采购订单」三张表单里的数据
导出到本地目录，用于查看账套数据的真实形式（列名、取值、实体结构）。

- 只用只读接口：QueryBusinessInfo / ExecuteBillQuery / View
- 产物写入输出目录（默认 data/sample_export/）：CSV（utf-8-sig，可直接用 Excel 打开）+ 原始 JSON
- 不做任何计算，只把原始数据摊开，便于确认字段语义与后续实现方式

用法：
    KINGDEE_PASSWORD='xxx' python3 scripts/explore_sample_data.py [目标产品编码] [输出目录]
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kingdee_sdk import KingdeeClient, KingdeeAPIError, load_kingdee_config

DEFAULT_MATERIAL = "1.LA.LE.001083"  # 航空应急灯（账套里已确认有 BOM 与销售订单）
DEFAULT_OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample_export"
)

SALES_FIELDS = (
    "FBillNo,FDate,FDocumentStatus,FMaterialId.FNumber,FMaterialId.FName,FQty,"
    "FTaxPrice,FPrice,FTaxRate,FAllAmount,FAmount,FExchangeRate"
)
PUR_FIELDS = (
    "FBillNo,FDate,FDocumentStatus,FMaterialId.FNumber,FMaterialId.FName,FQty,"
    "FTaxPrice,FPrice,FEntryTaxRate,FAllAmount,FAmount,FSupplierId.FName"
)
BOM_FIELDS = "FID,FNumber,FMaterialId.FNumber,FMaterialId.FName,FDocumentStatus,FCreateDate"

OUT_DIR = DEFAULT_OUT
_raw_cache = {}


def dump_json(name, obj):
    path = os.path.join(OUT_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return path


def write_csv(name, header, rows):
    path = os.path.join(OUT_DIR, name)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])
    return path


def preview(header, rows, n=3, width=42):
    print(f"    列({len(header)}): {header}")
    for r in rows[:n]:
        cells = []
        for v in r:
            s = "" if v is None else str(v)
            cells.append(s[:width])
        print(f"      {cells}")
    if len(rows) > n:
        print(f"      …（共 {len(rows)} 行，完整见 CSV）")


def run_query(client, label, form_id, field_keys, filter_string=None, order_string=None, limit=50):
    """执行查询并保存原始返回；失败时返回 None 并把错误打印出来"""
    print(f"\n  ▸ {label}")
    print(f"    form_id={form_id}  filter={filter_string or '(无)'}  limit={limit}")
    try:
        rows = client.execute_bill_query(
            form_id=form_id,
            field_keys=field_keys,
            filter_string=filter_string,
            order_string=order_string,
            limit=limit,
        )
    except KingdeeAPIError as exc:
        print(f"    ❌ 查询失败: {exc}")
        return None
    rows = [r for r in rows if isinstance(r, (list, tuple))]
    header = [f.strip() for f in field_keys.split(",")]
    safe = label.replace("/", "_")
    p1 = write_csv(f"{safe}.csv", header, rows)
    p2 = dump_json(f"{safe}.raw.json", rows)
    print(f"    ✅ {len(rows)} 行 -> {os.path.relpath(p1, os.getcwd())} / {os.path.relpath(p2, os.getcwd())}")
    preview(header, rows)
    return rows


def walk(node, path="", hits=None):
    """收集 JSON 里所有「列表<对象>」的位置，用来找出单据体(entity)结构"""
    if hits is None:
        hits = []
    if isinstance(node, dict):
        for k, v in node.items():
            walk(v, f"{path}.{k}" if path else k, hits)
    elif isinstance(node, list):
        if node and all(isinstance(x, dict) for x in node):
            keys = set()
            for x in node[:3]:
                keys |= set(x)
            hits.append((path, len(node), sorted(keys)))
        for i, x in enumerate(node[:3]):
            walk(x, f"{path}[{i}]", hits)
    return hits


def find_child_materials(node, out=None):
    """递归找子件物料的编码/名称（字段名形如 FMaterialIdCoby / FMATERIALIDCOBY）"""
    if out is None:
        out = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k.upper() in ("FMATERIALIDCOBY", "FMATERIALIDCHILD"):
                if isinstance(v, dict):
                    out.append((v.get("FNumber"), v.get("FName"), v.get("Id")))
                elif v is not None:
                    out.append((str(v), None, None))
            find_child_materials(v, out)
    elif isinstance(node, list):
        for x in node:
            find_child_materials(x, out)
    return out


def main():
    global OUT_DIR, _raw_cache
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MATERIAL
    out_dir = sys.argv[2] if len(sys.argv) > 2 else OUT_DIR
    OUT_DIR = os.path.abspath(out_dir)
    os.makedirs(OUT_DIR, exist_ok=True)

    cfg = load_kingdee_config()
    if not cfg.get("password"):
        print("[配置缺失] 需要 KINGDEE_PASSWORD")
        return 1
    client = KingdeeClient(
        server_url=cfg["server_url"],
        acct_id=cfg["acct_id"],
        username=cfg["username"],
        password=cfg["password"],
        auth_type=cfg["auth_type"],
    )
    client.login()
    print(f"[登录成功] {cfg['username']} / 账套 {cfg['acct_id']}")
    print(f"[输出目录] {OUT_DIR}     [目标产品] {target}")

    # ---------- 1) 销售订单分录 ----------
    print("\n" + "=" * 72)
    print("1) 销售订单 SAL_SaleOrder（分录行）")
    print("=" * 72)
    sales = run_query(
        client, "sales_orders_audited", "SAL_SaleOrder", SALES_FIELDS,
        filter_string="FDocumentStatus='C'", order_string="FID DESC", limit=50,
    )
    if not sales:
        sales = run_query(
            client, "sales_orders_all", "SAL_SaleOrder", SALES_FIELDS,
            order_string="FID DESC", limit=50,
        )
    # 附加字段探测（是否含税 / 折扣 / 成本）
    run_query(
        client, "sales_orders_extra", "SAL_SaleOrder",
        "FBillNo,FMaterialId.FNumber,FIsIncludedTax,FTaxNetPrice,FDiscountRate,"
        "FCostAmount,FCostPercent,FPriceUnitQty,FMaterialPriceUnitID.FName",
        order_string="FID DESC", limit=20,
    )

    # 目标产品在销售订单里的价格行
    target_sales = [r for r in (sales or []) if str(r[3]) == target] if sales else []
    if target_sales:
        print(f"\n  ▸ 目标产品 {target} 在销售订单里的价格行（{len(target_sales)} 行）")
        preview([f.strip() for f in SALES_FIELDS.split(",")], target_sales, n=5)
        dump_json("target_sales_rows.json", target_sales)

    # ---------- 2) 物料清单 ----------
    print("\n" + "=" * 72)
    print("2) 物料清单 ENG_BOM")
    print("=" * 72)
    boms = run_query(
        client, "bom_by_material", "ENG_BOM", BOM_FIELDS,
        filter_string=f"FMaterialId.FNumber='{target}'", order_string="FID DESC", limit=20,
    )

    bom_no = None
    if boms:
        audited = [r for r in boms if r[4] == "C"]
        bom_no = (audited[0] if audited else boms[0])[1]
    if bom_no:
        print(f"\n  ▸ View 拉取 BOM 全量数据：FNumber={bom_no}")
        try:
            view = client.view("ENG_BOM", {"Number": bom_no})
            p = dump_json("bom_view_full.json", view)
            print(f"    ✅ 已保存 {os.path.relpath(p, os.getcwd())}")
            hits = walk(view)
            print("    ── 单据体(entity)结构（路径 / 行数 / 字段名）──")
            for path, n, keys in hits:
                if path == "":
                    continue
                interesting = any(
                    t in k for k in keys for t in ("MaterialId", "Qty", "Unit", "Coby", "COBY")
                )
                if interesting:
                    print(f"      {path}  rows={n}")
                    print(f"        keys: {', '.join(keys)[:600]}")
            kids = find_child_materials(view)
            seen, uniq = set(), []
            for code, name, _id in kids:
                if code and code not in seen:
                    seen.add(code)
                    uniq.append((code, name))
            print(f"    ── 子件物料（BOM 展开第一层，{len(uniq)} 个）──")
            for code, name in uniq[:30]:
                print(f"      {code}  {name}")
            dump_json("bom_child_materials.json", uniq)
            _raw_cache["children"] = uniq
        except KingdeeAPIError as exc:
            print(f"    ❌ View 失败: {exc}")

    # ---------- 3) 采购订单（目标产品自身的采购） ----------
    print("\n" + "=" * 72)
    print("3) 采购订单 PUR_PurchaseOrder")
    print("=" * 72)
    run_query(
        client, "purchase_orders_audited", "PUR_PurchaseOrder", PUR_FIELDS,
        filter_string="FDocumentStatus='C'", order_string="FID DESC", limit=20,
    )
    run_query(
        client, "purchase_by_target_material", "PUR_PurchaseOrder", PUR_FIELDS,
        filter_string=f"FMaterialId.FNumber='{target}'", order_string="FID DESC", limit=20,
    )

    # 子件的采购价（成本侧的关键取数）
    kids = _raw_cache.get("children") or []
    codes = [c for c, _n in kids][:8]
    if codes:
        in_list = ",".join(f"'{c}'" for c in codes)
        run_query(
            client, "purchase_by_child_materials", "PUR_PurchaseOrder", PUR_FIELDS,
            filter_string=f"FMaterialId.FNumber in ({in_list})",
            order_string="FID DESC", limit=50,
        )
    else:
        print("\n  ⚠ 没取到 BOM 子件物料，跳过子件采购价查询")

    client.logout()
    print(f"\n[已登出] 产物目录：{OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
