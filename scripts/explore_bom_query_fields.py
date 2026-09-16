#!/usr/bin/env python3
"""
精确探测：ExecuteBillQuery 到底能不能按「BOM 子件行」取数（只读）。

背景：用 FMaterialIdCoby.FNumber 查询时返回 3 行（=3 张 BOM 单头）且值为 None，
说明字段名不对或查询本身不展开子件。本脚本逐一试探候选写法，并打印行数/取值判定。

判定标准：
- 返回行数明显大于单据头行数（>3），且子件编码列有值 → 「查询接口可展开子件」✅
- 行数 = 单据头行数 或 子件编码全为 None → 该写法不可用 ❌

用法：
    KINGDEE_PASSWORD='xxx' python3 scripts/explore_bom_query_fields.py [父项物料编码]
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kingdee_sdk import KingdeeClient, KingdeeAPIError, load_kingdee_config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_DIR = os.path.join(ROOT, "data", "sample_export")
PARENT = "1.LA.LE.001083"

# 候选写法：View 里子件实体是 TreeEntity、子件物料字段是 MATERIALIDCHILD、用量是 NUMERATOR/DENOMINATOR
CANDIDATES = [
    "FNumber,FMaterialId.FNumber,FMaterialIdChild.FNumber,FNumerator,FDenominator",
    "FNumber,FMaterialId.FNumber,FMaterialIdChild.FNumber,FMaterialIdChild.FName,FNumerator,FDenominator,FChildUnitID.FNumber",
    "FNumber,FMaterialId.FNumber,FMaterialIdCoby.FNumber,FNumerator,FDenominator",
    "FNumber,FMaterialId.FNumber,FMATERIALIDCHILD,FNUMERATOR,FDENOMINATOR",
    "FNumber,FMaterialId.FNumber,FTreeEntity_FMaterialIdChild.FNumber,FNumerator,FDenominator",
    "FID,FNumber,FMaterialId.FNumber,FMaterialIdChild.FNumber,FNumerator,FDenominator,FQty,FActualQty,FScrapRate",
]


def save_csv(name, header, rows):
    path = os.path.join(SAMPLE_DIR, name)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])
    return path


def main():
    parent = sys.argv[1] if len(sys.argv) > 1 else PARENT
    os.makedirs(SAMPLE_DIR, exist_ok=True)

    cfg = load_kingdee_config()
    if not cfg.get("password"):
        print("[配置缺失] 需要 KINGDEE_PASSWORD")
        return 1
    client = KingdeeClient(
        server_url=cfg["server_url"], acct_id=cfg["acct_id"], username=cfg["username"],
        password=cfg["password"], auth_type=cfg["auth_type"],
    )
    client.login()
    print(f"[登录成功] {cfg['username']}  [父项] {parent}\n")

    # 先看单据头的行数作为基准
    try:
        head_rows = client.execute_bill_query(
            form_id="ENG_BOM", field_keys="FID,FNumber,FMaterialId.FNumber",
            filter_string=f"FMaterialId.FNumber='{parent}'", limit=50,
        )
        head_rows = [r for r in head_rows if isinstance(r, (list, tuple))]
        print(f"[基准] 该父项的 BOM 单据头行数 = {len(head_rows)}（View 里的子件行数是 18）")
        for r in head_rows:
            print(f"    {r}")
    except KingdeeAPIError as exc:
        print(f"[基准] 查询失败: {exc}")
        head_rows = []

    print("\n候选字段写法试探：")
    best = None
    for keys in CANDIDATES:
        header = [k.strip() for k in keys.split(",")]
        try:
            rows = client.execute_bill_query(
                form_id="ENG_BOM", field_keys=keys,
                filter_string=f"FMaterialId.FNumber='{parent}'", limit=200,
            )
            rows = [r for r in rows if isinstance(r, (list, tuple))]
          # 找子件编码列
            idx = None
            for i, h in enumerate(header):
                if "Child" in h or "Coby" in h or "Child".upper() in h.upper():
                    if h.endswith(".FNumber"):
                        idx = i
            values = [r[idx] for r in rows if idx is not None and idx < len(r)]
            non_null = [v for v in values if v not in (None, "")]
            verdict = "✅ 展开成功" if len(rows) > len(head_rows) and non_null else "❌ 未展开（子件无值）"
            print(f"\n  {verdict}  {keys}")
            print(f"    行数={len(rows)}  子件编码非空数={len(non_null)}")
            if rows:
                print(f"    首行={rows[0]}")
            if verdict.startswith("✅"):
                p = save_csv("bom_query_child_rows.csv", header, rows)
                print(f"    ✅ 已保存 {os.path.relpath(p, os.getcwd())}")
                best = (keys, rows)
        except KingdeeAPIError as exc:
            print(f"\n  ❌ 字段/写法不可用  {keys}\n    原因: {exc}")

    if not best:
        print("\n结论：这些候选都没能通过 ExecuteBillQuery 取到 BOM 子件行，"
              "BOM 展开需要走 View 接口（或 BOM 正向展开模型）。")
    client.logout()
    print("\n[已登出]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
