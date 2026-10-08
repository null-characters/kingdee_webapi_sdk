#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核对核算输出（读导出的 xlsx）：
    1. 按「记录号 + 子件」检查明细有没有重复计数
    2. 看 BOM 展开层级是否正常
    3. 统计价格来源：金蝶最近采购价 / 手工维护价 / 缺价
    4. 核对「自动料本 + 手工维护料本 = 最终料本」
    5. 统计叶子件采购价的日期分布（提醒「不限时点取最新价」可能用到很久以前的老价）

用法：
    python3 scripts/check_costing_output.py [xlsx路径]
"""

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "sample_export", "costing_2026-09_未税.xlsx",
)
OLD_PRICE_BEFORE = "2026-01-01"  # 早于这个日期的采购价算「老价」
SRC_KINGDEE = "金蝶"
SRC_MANUAL = "手工维护"


def _col(idx, *names):
    """取列下标：兼容新旧列名，找不到返回 None"""
    for n in names:
        if n in idx:
            return idx[n]
    return None


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    if not os.path.exists(path):
        print(f"[找不到文件] {path}")
        return 1

    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    print(f"[读取] {path}")
    print(f"工作表：{wb.sheetnames}")

    # ---------------- 子件明细 ----------------
    ws = wb["子件明细"]
    rows = ws.iter_rows(values_only=True)
    header = list(next(rows))
    idx = {name: i for i, name in enumerate(header)}

    c_rec = _col(idx, "记录号")
    c_bill = _col(idx, "销售单号")
    c_prod = _col(idx, "产品编码")
    c_code = _col(idx, "子件编码")
    c_name = _col(idx, "子件名称")
    c_level = _col(idx, "层级")
    c_qty = _col(idx, "累计用量")
    c_src = _col(idx, "价格来源")
    c_note = _col(idx, "备注")
    c_date = _col(idx, "采购日期")
    c_billno = _col(idx, "采购单号")
    c_amount = _col(idx, "金额(人民币)")

    def src_of(row):
        """价格来源：新文件看「价格来源」列，旧文件用「备注」推断"""
        if c_src is not None:
            return row[c_src] or ""
        return "" if row[c_note] == "缺采购价" else SRC_KINGDEE

    groups = {}
    dates = []
    old_prices = []
    src_counter = Counter()
    manual_rows = []
    for r in rows:
        key = (r[c_rec] if c_rec is not None else r[c_bill], r[c_code])
        groups.setdefault(key, []).append(r)
        src = src_of(r)
        src_counter[src or "缺价"] += 1
        if src == SRC_MANUAL:
            manual_rows.append(r)
        d = r[c_date] if c_date is not None else None
        if d:
            dates.append(str(d))
            if str(d) < OLD_PRICE_BEFORE:
                old_prices.append((str(d), r[c_code], r[c_name],
                                   r[c_billno] if c_billno is not None else ""))

    print(f"\n{'记录号':>6} {'子件编码':<20}{'明细行':>7}{'去重子件':>9}{'重复行':>7}"
          f"{'缺价':>6}{'手工':>6}  层级分布")
    total_dup = 0
    for (rec, code), items in groups.items():
        codes = [x[c_code] for x in items]
        keys = [(x[c_code], x[c_level], x[c_qty]) for x in items]
        dup = len(keys) - len(set(keys))
        total_dup += dup
        levels = Counter(x[c_level] for x in items)
        missing = sum(1 for x in items if src_of(x) == "")
        manual = sum(1 for x in items if src_of(x) == SRC_MANUAL)
        level_txt = " ".join(f"L{k}:{v}" for k, v in sorted(levels.items()))
        print(f"{str(rec):>6} {str(code):<20}{len(items):>7}{len(set(codes)):>9}{dup:>7}"
              f"{missing:>6}{manual:>6}  {level_txt}")
    print(f"\n完全重复行合计：{total_dup}（应为 0，>0 说明同一层同一子件被算了两遍）")

    print(f"\n价格来源分布：金蝶最近采购价 {src_counter[SRC_KINGDEE]} 行、"
          f"手工维护价 {src_counter[SRC_MANUAL]} 行、缺价 {src_counter['缺价']} 行")
    if src_counter["缺价"]:
        print("  ⚠ 仍有缺价子件（正常流程下这些必须补完才会导出）")
    if manual_rows:
        print(f"  手工维护价明细（共 {len(manual_rows)} 行），前 8 条：")
        qty_i = c_qty
        for r in manual_rows[:8]:
            print(f"    {str(r[c_code]):<20}{str(r[c_name])[:16]:<18}"
                  f"用量 {r[qty_i]:<8g}金额 {r[c_amount]:>12,.4f}")

    # ---------------- 逐条核算：自动 + 手工 = 最终 ----------------
    ws2 = wb["逐条核算"]
    rows2 = list(ws2.iter_rows(values_only=True))
    head2 = list(rows2[0])
    i2 = {name: i for i, name in enumerate(head2)}
    print(f"\n逐条核算：{len(rows2) - 1} 条记录")
    print("  列：" + " | ".join(str(v) for v in head2))

    c_auto = _col(i2, "自动料本(人民币)")
    c_manual_t = _col(i2, "手工维护料本(人民币)")
    c_final = _col(i2, "最终料本(人民币)", "总料本(人民币)")
    c_gross = _col(i2, "毛利(人民币)")
    c_sale = _col(i2, "销售额(人民币)")
    if None not in (c_auto, c_manual_t, c_final):
        bad = [r for r in rows2[1:]
               if abs(float(r[c_auto] or 0) + float(r[c_manual_t] or 0)
                      - float(r[c_final] or 0)) > 0.01]
        print(f"  自动料本 + 手工维护料本 = 最终料本："
              f"{'全部一致 ✅' if not bad else f'有 {len(bad)} 条不一致 ❌'}")
        total_auto = sum(float(r[c_auto] or 0) for r in rows2[1:])
        total_manual = sum(float(r[c_manual_t] or 0) for r in rows2[1:])
        total_final = sum(float(r[c_final] or 0) for r in rows2[1:])
        total_sale = sum(float(r[c_sale] or 0) for r in rows2[1:]) if c_sale is not None else 0
        print(f"  合计：销售额 {total_sale:,.2f}  自动料本 {total_auto:,.2f}"
              f"  手工维护料本 {total_manual:,.2f}  最终料本 {total_final:,.2f}")
    if None not in (c_final, c_gross, c_sale):
        bad2 = [r for r in rows2[1:]
                if abs(float(r[c_sale] or 0) - float(r[c_final] or 0)
                       - float(r[c_gross] or 0)) > 0.01]
        print(f"  销售额 - 最终料本 = 毛利：{'全部一致 ✅' if not bad2 else f'有 {len(bad2)} 条不一致 ❌'}")

    # ---------------- 区间汇总 ----------------
    if "区间汇总" in wb.sheetnames:
        rows3 = list(wb["区间汇总"].iter_rows(values_only=True))
        print(f"\n区间汇总：{len(rows3) - 1} 行（末行为合计）")
        i3 = {name: i for i, name in enumerate(rows3[0])}
        for r in rows3[1:]:
            print(f"  {str(r[i3['产品编码']]):<20}{str(r[i3['产品名称']])[:16]:<18}"
                  f"记录 {r[i3['记录数']]:>4}  销售额 {float(r[i3['销售额(人民币)']] or 0):>14,.2f}"
                  f"  最终料本 {float(r[i3['最终料本(人民币)']] or 0):>14,.2f}"
                  f"  手工维护 {float(r[i3['手工维护料本(人民币)']] or 0):>12,.2f}"
                  f"  毛利 {float(r[i3['毛利(人民币)']] or 0):>14,.2f}")

    # ---------------- 缺价待维护 ----------------
    if "缺价待维护" in wb.sheetnames:
        rows4 = list(wb["缺价待维护"].iter_rows(values_only=True))
        left = [r for r in rows4[1:] if r[0] not in ("（无）", None, "")]
        print(f"\n缺价待维护：{len(left)} 个子件（导出时若 >0 说明是强制导出的）")
        for r in left[:10]:
            print(f"  {str(r[0]):<22}{str(r[1])[:16]:<18}{str(r[5]) if len(r) > 5 else ''}")

    if dates:
        years = Counter(d[:4] for d in dates)
        print(f"\n叶子件采购价日期分布（金蝶价，共 {len(dates)} 行）：")
        for y, c in sorted(years.items()):
            print(f"    {y} 年：{c} 行")
        if old_prices:
            print(f"\n⚠ 采购价早于 {OLD_PRICE_BEFORE} 的叶子件 {len(old_prices)} 行（老价），"
                  f"最老的 8 条：")
            for d, code, name, bill in sorted(old_prices)[:8]:
                print(f"    {d}  {str(code):<18}{str(name)[:16]:<18}来自 {bill}")
        else:
            print(f"\n没有早于 {OLD_PRICE_BEFORE} 的老价。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
