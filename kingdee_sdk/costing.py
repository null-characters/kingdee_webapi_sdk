# -*- coding: utf-8 -*-
"""
成本核算核心：按日期区间、逐条销售记录，用 BOM 展开 + 采购价算出料本与毛利。

与财务确认的口径（2026-09）
--------------------------
1) 按**日期区间**结算（整月或 5 号~15 号这种任意区间），区间内每一条销售记录单独计算
2) 采购价取该物料「最近一次成交价」（最新一条已审核采购行，不限时点）
3) 按销售结算币别：外币折成人民币后再比；默认用订单自带汇率，也可整批指定覆盖汇率
4) **缺采购价的子件**：金蝶取不到价时，用财务在本地维护表（CSV）里手工填的单价补位；
   补位的成本单独成列（「手工维护料本」），与「自动料本」相加得到「最终料本」
5) 所有缺价子件都补齐之前**不导出最终表格**（由调用方用 ``CostingRun.complete`` 判断）

实现要点（均在账套实测过）
------------------------
- 币别字段是 FSettleCurrId（不是 FCurrencyId，后者不存在）；PRE001=人民币、PRE007=美元
- 销售/采购单价：未税用 FPrice、含税用 FTaxPrice；人民币单价 = 原币单价 × 汇率
- BOM 子件字段是 FMaterialIdChild.FNumber（不是 FMaterialIdCoby），用量 FNumerator/FDenominator
- 同一 BOM 编号可能有多条重复单据，取 FID 最大的那张（已审核）
- 采购订单的 FAmount（未税金额）实测恒为 0，所以金额一律用「单价 × 数量」自算
- 单价为 0 的采购记录不算成交，取价时会自动跳过
"""

from __future__ import annotations

import datetime
import gzip
import json
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .exceptions import KingdeeAPIError
from .manual_prices import (
    ManualPriceTable,
    resolve_snapshot_path,
    to_float,
)

# ==================== 常量 ====================

TAX_EXCLUDED = "未税"
TAX_INCLUDED = "含税"
TAX_MODES = (TAX_EXCLUDED, TAX_INCLUDED)

SALE_FORM = "SAL_SaleOrder"
PUR_FORM = "PUR_PurchaseOrder"
BOM_FORM = "ENG_BOM"

BASE_CURRENCY = "PRE001"  # 人民币（本位币）
CURRENCY_NAMES = {
    "PRE001": "人民币",
    "PRE002": "香港元",
    "PRE003": "欧元",
    "PRE004": "日本日圆",
    "PRE005": "新台币元",
    "PRE006": "英镑",
    "PRE007": "美元",
    "PRE008": "越南盾",
}

# ---- 销售订单分录字段（顺序与下面列索引一一对应）----
SALE_FIELDS = (
    "FBillNo,FDate,FDocumentStatus,FSettleCurrId.FNumber,FExchangeRate,"
    "FMaterialId.FNumber,FMaterialId.FName,FQty,FPrice,FTaxPrice"
)
(
    S_BILL_NO, S_DATE, S_STATUS, S_CURRENCY, S_RATE,
    S_MAT_CODE, S_MAT_NAME, S_QTY, S_PRICE, S_TAX_PRICE,
) = range(10)

# ---- BOM 单据体字段 ----
BOM_HEAD_FIELDS = "FID,FNumber"
BOM_ENTRY_FIELDS = (
    "FNumber,FMaterialId.FNumber,FMaterialIdChild.FNumber,FMaterialIdChild.FName,"
    "FNumerator,FDenominator,FChildUnitID.FNumber"
)
(
    B_BILL_NO, B_PARENT, B_CHILD_CODE, B_CHILD_NAME,
    B_NUMERATOR, B_DENOMINATOR, B_UNIT,
) = range(7)

# ---- 采购订单分录字段 ----
PUR_FIELDS = (
    "FBillNo,FDate,FDocumentStatus,FSettleCurrId.FNumber,FExchangeRate,"
    "FMaterialId.FNumber,FPrice,FTaxPrice"
)
(
    P_BILL_NO, P_DATE, P_STATUS, P_CURRENCY, P_RATE,
    P_MAT_CODE, P_PRICE, P_TAX_PRICE,
) = range(8)

# ---- 价格来源 / 备注 ----
PRICE_FROM_KINGDEE = "金蝶"
PRICE_FROM_MANUAL = "手工维护"
NO_PRICE_NOTE = "缺采购价"

MANUAL_TABLE_RELATIVE = os.path.join("成本核算数据", "采购价维护表.csv")


class CostingError(RuntimeError):
    """核算过程中的业务错误（账套拒绝、字段缺失、参数不对等）"""


def _num(value, default: float = 0.0) -> float:
    """金蝶返回的数字可能是 None / 空串 / 字符串，统一转 float"""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def currency_code(text) -> str:
    """币别文本 → 币别内码：认「美元」「PRE007」都可以，认不出就原样返回"""
    t = str(text or "").strip()
    if not t:
        return BASE_CURRENCY
    if t in CURRENCY_NAMES:
        return t
    for code, name in CURRENCY_NAMES.items():
        if t == name or t.upper() == code.upper():
            return code
    return t


def currency_label(code) -> str:
    return CURRENCY_NAMES.get(code, code)


def manual_rate(code: str, row_rate: Optional[float], override_rate: Optional[float]) -> float:
    """手工维护价的折算汇率：人民币=1；表里填了汇率就用它；否则退到界面覆盖汇率"""
    if code == BASE_CURRENCY:
        return 1.0
    if row_rate and row_rate > 0:
        return row_rate
    if override_rate:
        return override_rate
    return 1.0


# ==================== 日期区间 ====================

def parse_date_text(text) -> str:
    """把用户填的日期转成 ISO：认 2026-09-05 / 2026/9/5 / 2026.9.5 / 20260905"""
    raw = str(text or "").strip()
    if not raw:
        raise CostingError("日期不能为空")
    clean = raw.replace("/", "-").replace(".", "-").replace("年", "-").replace("月", "-").replace("日", "")
    parts = [p for p in clean.split("-") if p != ""]
    try:
        if len(parts) == 1 and len(parts[0]) == 8 and parts[0].isdigit():
            d = datetime.date(int(parts[0][:4]), int(parts[0][4:6]), int(parts[0][6:8]))
        elif len(parts) == 3:
            d = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
        else:
            raise ValueError
    except ValueError as exc:
        raise CostingError(f"日期格式不对：{raw}（请填成 2026-09-05 这样）") from exc
    return d.isoformat()


def normalize_range(date_from, date_to) -> Tuple[str, str]:
    """校验并规范化日期区间，保证 起 <= 止"""
    start, end = parse_date_text(date_from), parse_date_text(date_to)
    if start > end:
        raise CostingError(f"起始日期（{start}）不能晚于结束日期（{end}）")
    return start, end


def month_range(month: str) -> Tuple[str, str]:
    """'2026-09' -> ('2026-09-01', '2026-09-30')"""
    year, mon = (int(x) for x in str(month).split("-")[:2])
    first = datetime.date(year, mon, 1)
    nxt = datetime.date(year + 1, 1, 1) if mon == 12 else datetime.date(year, mon + 1, 1)
    return first.isoformat(), (nxt - datetime.timedelta(days=1)).isoformat()


def month_bounds(offset: int = 0, today: Optional[datetime.date] = None) -> Tuple[str, str]:
    """界面快捷按钮用：offset=0 本月、-1 上月，返回 (1 号, 月末)"""
    today = today or datetime.date.today()
    year, mon = today.year, today.month + offset
    while mon <= 0:
        mon += 12
        year -= 1
    while mon > 12:
        mon -= 12
        year += 1
    return month_range(f"{year:04d}-{mon:02d}")


def range_label(date_from: str, date_to: str) -> str:
    """给界面/Excel 说明用的区间文字：整月就写「2026-09（整月）」"""
    if date_from[:7] == date_to[:7]:
        first, last = month_range(date_from[:7])
        if date_from == first and date_to == last:
            return f"{date_from[:7]}（整月）"
    return f"{date_from} ~ {date_to}"


def range_file_label(date_from: str, date_to: str) -> str:
    """给文件名用的短标签（不能有空格和 ~）"""
    if date_from[:7] == date_to[:7]:
        first, last = month_range(date_from[:7])
        if date_from == first and date_to == last:
            return date_from[:7]
    return f"{date_from}_{date_to}"


# ==================== 核算结果 ====================

@dataclass
class CostingRun:
    """一次核算的完整结果

    Attributes:
        meta: 本次核算的参数与口径（写进 Excel「说明」表）
        records: 逐条销售记录（含各自子件明细），重算时以它为准
        summary: 「逐条核算」表的行
        details: 「子件明细」表的行
        missing: 仍然缺采购价的子件（聚合去重）——非空就不允许导出最终表
        stale: 维护表里填了价、但金蝶现在已经能取到价的子件（提示财务清理）
        children: 本次涉及的全部子件及其价格状态（聚合去重，界面展示用）
    """

    meta: Dict[str, object] = field(default_factory=dict)
    records: List[dict] = field(default_factory=list)
    summary: List[dict] = field(default_factory=list)
    details: List[dict] = field(default_factory=list)
    missing: List[dict] = field(default_factory=list)
    stale: List[dict] = field(default_factory=list)
    children: List[dict] = field(default_factory=list)
    snapshot_path: str = ""

    @property
    def complete(self) -> bool:
        """缺价子件是否已全部补齐（补齐才允许导出最终表格）"""
        return not self.missing

    @property
    def missing_codes(self) -> List[str]:
        return [m["子件编码"] for m in self.missing]

    def totals(self) -> Dict[str, float]:
        sale = sum(r["销售额(人民币)"] for r in self.summary)
        auto = sum(r["自动料本(人民币)"] for r in self.summary)
        manual = sum(r["手工维护料本(人民币)"] for r in self.summary)
        final = sum(r["最终料本(人民币)"] for r in self.summary)
        return {
            "记录数": float(len(self.summary)),
            "销售额": sale,
            "自动料本": auto,
            "手工维护料本": manual,
            "最终料本": final,
            "毛利": sale - final,
            "毛利率": ((sale - final) / sale) if sale else 0.0,
        }


def build_note(*, missing: int, manual: int, leaf_count: int, issues: Iterable[str]) -> str:
    """拼「备注」列：手工维护 / 缺价 / 结构性问题"""
    parts: List[str] = []
    if manual:
        parts.append(f"{manual} 个子件按手工维护价计")
    if missing:
        parts.append(f"{missing} 个子件缺采购价")
    if leaf_count == 0:
        parts.append("未取到子件（该产品可能没有 BOM）")
    parts.extend(sorted({str(x) for x in issues if x}))
    return "；".join(parts)


def _finalize(records: List[dict], meta: Dict[str, object],
              table: Optional[ManualPriceTable] = None) -> CostingRun:
    """把「每条销售记录 + 子件明细」汇总成导出用的表（run 与重算共用，保证列一致）

    单件成本分三列：自动（金蝶价） / 手工维护（财务填的价） / 最终（两者相加）
    """
    tax = str(meta.get("计价方式") or TAX_EXCLUDED)
    price_col = f"采购价-{tax}(原币)"

    summary: List[dict] = []
    details: List[dict] = []
    missing_map: "Dict[str, dict]" = {}
    children_map: "Dict[str, dict]" = {}
    kingdee_codes: set = set()

    for rec in records:
        sale = dict(rec.get("sale") or {})
        leaves = list(rec.get("leaves") or [])
        qty = _num(sale.get("数量"), 0.0)

        auto_unit = sum(_num(l.get("amount_cny")) for l in leaves
                        if l.get("source") == PRICE_FROM_KINGDEE)
        manual_unit = sum(_num(l.get("amount_cny")) for l in leaves
                          if l.get("source") == PRICE_FROM_MANUAL)
        unit_cost = auto_unit + manual_unit

        missing_cnt = sum(1 for l in leaves if not l.get("source"))
        manual_cnt = sum(1 for l in leaves if l.get("source") == PRICE_FROM_MANUAL)
        sale_amount = _num(sale.get("销售额(人民币)"))

        auto_total = auto_unit * qty
        manual_total = manual_unit * qty
        total_cost = unit_cost * qty
        gross = sale_amount - total_cost
        margin = (gross / sale_amount) if sale_amount else 0.0

        row: Dict[str, object] = {}
        row["记录号"] = rec.get("记录号", "")
        row.update(sale)
        row.update({
            "自动料本-单件(人民币)": auto_unit,
            "手工维护料本-单件(人民币)": manual_unit,
            "最终料本-单件(人民币)": unit_cost,
            "自动料本(人民币)": auto_total,
            "手工维护料本(人民币)": manual_total,
            "最终料本(人民币)": total_cost,
            "毛利(人民币)": gross,
            "毛利率": margin,
            "子件数": len(leaves),
            "手工维护子件数": manual_cnt,
            "备注": build_note(missing=missing_cnt, manual=manual_cnt,
                               leaf_count=len(leaves), issues=rec.get("issues") or []),
        })
        summary.append(row)

        for leaf in leaves:
            code = str(leaf.get("code") or "")
            source = str(leaf.get("source") or "")
            if source == PRICE_FROM_KINGDEE:
                kingdee_codes.add(code)
            details.append({
                "记录号": rec.get("记录号", ""),
                "销售单号": sale.get("销售单号", ""),
                "产品编码": sale.get("产品编码", ""),
                "层级": leaf.get("level", ""),
                "子件编码": code,
                "子件名称": leaf.get("name", ""),
                "累计用量": _num(leaf.get("qty")),
                "单位": leaf.get("unit", ""),
                price_col: _num(leaf.get("price_orig")),
                "采购币别": currency_label(leaf.get("currency") or BASE_CURRENCY),
                "采购汇率": _num(leaf.get("rate"), 1.0),
                "采购价(人民币)": _num(leaf.get("price_cny")),
                "金额(人民币)": _num(leaf.get("amount_cny")),
                "采购单号": leaf.get("bill_no", ""),
                "采购日期": leaf.get("bill_date", ""),
                "价格来源": source,
                "备注": "" if source else NO_PRICE_NOTE,
            })

        # 聚合：缺价子件 / 全部子件价格状态
        for leaf in leaves:
            code = str(leaf.get("code") or "")
            if not code:
                continue
            src = str(leaf.get("source") or "缺价")
            ch = children_map.get(code)
            if ch is None:
                children_map[code] = ch = {
                    "子件编码": code, "子件名称": leaf.get("name", ""),
                    "单位": leaf.get("unit", ""), "价格来源": src,
                    price_col: _num(leaf.get("price_orig")),
                    "单价(人民币)": _num(leaf.get("price_cny")),
                    "出现次数": 0, "_products": set(), "_sources": {src},
                }
            else:
                ch["_sources"].add(src)
            ch["出现次数"] += 1
            ch["_products"].add(sale.get("产品编码", ""))
            if not _num(ch.get("单价(人民币)")) and _num(leaf.get("price_cny")):
                ch["单价(人民币)"] = _num(leaf.get("price_cny"))
                ch[price_col] = _num(leaf.get("price_orig"))

            if not leaf.get("source"):
                m = missing_map.get(code)
                if m is None:
                    missing_map[code] = m = {
                        "子件编码": code, "子件名称": leaf.get("name", ""),
                        "单位": leaf.get("unit", ""), "出现次数": 0,
                        "_products": set(), "_reasons": [],
                    }
                m["出现次数"] += 1
                m["_products"].add(sale.get("产品编码", ""))
                if leaf.get("hint"):
                    m["_reasons"].append(str(leaf["hint"]))

    children = []
    for ch in children_map.values():
        sources = ch.pop("_sources")
        if len(sources) > 1:
            ch["价格来源"] = "混合（" + "/".join(sorted(sources)) + "）"
        ch["涉及产品数"] = len(ch.pop("_products"))
        children.append(ch)
    children.sort(key=lambda x: (x["价格来源"] != "缺价", -x["出现次数"], x["子件编码"]))

    missing = []
    for m in missing_map.values():
        m["涉及产品数"] = len(m.pop("_products"))
        reasons = sorted({r for r in m.pop("_reasons") if r})
        m["说明"] = "；".join(reasons) if reasons else "金蝶没有该子件的已审核采购价，请在维护表里填单价"
        missing.append(m)
    missing.sort(key=lambda x: (-x["出现次数"], x["子件编码"]))

    stale: List[dict] = []
    if table is not None:
        for code, row in table.rows.items():
            if code in kingdee_codes:
                stale.append({
                    "子件编码": code,
                    "子件名称": row.get("子件名称", ""),
                    "维护表未税单价": row.get("未税单价", ""),
                    "维护表含税单价": row.get("含税单价", ""),
                    "说明": "金蝶现在已有该子件的采购价，本次按金蝶价计算（维护表该行未采用，可考虑删除）",
                })
        stale.sort(key=lambda x: x["子件编码"])

    return CostingRun(meta=dict(meta), records=records, summary=summary, details=details,
                      missing=missing, stale=stale, children=children)


# ==================== 汇总 ====================

def summarize_by_product(summary: List[dict]) -> List[dict]:
    """按产品编码汇总（「区间汇总」工作表的内容）"""
    groups: "Dict[Tuple[str, str], dict]" = {}
    for r in summary:
        key = (str(r.get("产品编码", "")), str(r.get("产品名称", "")))
        g = groups.get(key)
        if g is None:
            groups[key] = g = {
                "产品编码": key[0], "产品名称": key[1], "记录数": 0, "数量": 0.0,
                "销售额(人民币)": 0.0, "自动料本(人民币)": 0.0,
                "手工维护料本(人民币)": 0.0, "最终料本(人民币)": 0.0, "毛利(人民币)": 0.0,
                "手工维护子件数": 0,
            }
        g["记录数"] += 1
        g["数量"] += _num(r.get("数量"))
        for col in ("销售额(人民币)", "自动料本(人民币)", "手工维护料本(人民币)",
                    "最终料本(人民币)", "毛利(人民币)"):
            g[col] += _num(r.get(col))
        g["手工维护子件数"] += int(_num(r.get("手工维护子件数")))

    rows = list(groups.values())
    for g in rows:
        sale = g["销售额(人民币)"]
        g["毛利率"] = (g["毛利(人民币)"] / sale) if sale else 0.0
    rows.sort(key=lambda g: -g["最终料本(人民币)"])

    if rows:
        total = {
            "产品编码": "合计", "产品名称": f"{len(rows)} 个产品", "记录数": 0, "数量": 0.0,
            "销售额(人民币)": 0.0, "自动料本(人民币)": 0.0, "手工维护料本(人民币)": 0.0,
            "最终料本(人民币)": 0.0, "毛利(人民币)": 0.0, "手工维护子件数": 0,
        }
        for g in rows:
            total["记录数"] += g["记录数"]
            total["手工维护子件数"] += g["手工维护子件数"]
            for col in ("数量", "销售额(人民币)", "自动料本(人民币)", "手工维护料本(人民币)",
                        "最终料本(人民币)", "毛利(人民币)"):
                total[col] += g[col]
        total["毛利率"] = (total["毛利(人民币)"] / total["销售额(人民币)"]) if total["销售额(人民币)"] else 0.0
        rows.append(total)
    return rows


# ==================== 快照（补价后重算用，不用再登录金蝶） ====================

SNAPSHOT_VERSION = 1


def save_snapshot(run: CostingRun, path: Optional[str] = None) -> str:
    """把本次核算的原始记录存到本地，供「套用维护表重新计算」使用"""
    target = path or resolve_snapshot_path()
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    payload = {"version": SNAPSHOT_VERSION, "meta": run.meta, "records": run.records}
    tmp = target + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, target)
    return target


def load_snapshot(path: Optional[str] = None) -> CostingRun:
    """读回上次核算快照（不查金蝶）"""
    target = path or resolve_snapshot_path()
    if not os.path.exists(target):
        raise CostingError(f"找不到上次核算的快照：{target}\n请先点「开始核算并导出」跑一次取数。")
    try:
        with gzip.open(target, "rt", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        raise CostingError(f"快照读取失败（可能已损坏，请重新核算）：{exc}") from exc
    if payload.get("version") != SNAPSHOT_VERSION:
        raise CostingError("快照版本不匹配，请重新核算。")
    run = _finalize(payload.get("records") or [], payload.get("meta") or {})
    run.snapshot_path = target
    return run


def check_recalc_compatible(meta: Dict[str, object], tax_mode: str,
                            override_rate: Optional[float]) -> Optional[str]:
    """检查「套用维护表重算」是否与快照时口径一致；不一致返回原因"""
    if str(meta.get("计价方式") or "") != tax_mode:
        return (f"上次取数用的是「{meta.get('计价方式')}」，现在选的是「{tax_mode}」——"
                f"两者的销售价/采购价列不同，必须重新登录取数。")
    old = meta.get("覆盖汇率")
    old_f = to_float(old)

    def _same(a, b):
        if a in (None, "", "未指定") and b in (None, ""):
            return True
        return a is not None and b is not None and abs(float(a) - float(b)) < 1e-9

    if not _same(old_f, override_rate):
        return (f"上次取数用的覆盖汇率是「{old or '未指定'}」，现在是"
                f"「{override_rate or '未指定'}」——折算口径变了，必须重新登录取数。")
    return None


def recalculate(run: CostingRun, table: ManualPriceTable,
                override_rate: Optional[float] = None) -> CostingRun:
    """用**最新的维护表**重算（不登录金蝶）

    金蝶取到价的子件保持原样；其余全部按维护表重新定价（填了就进「手工维护料本」，
    还没填就继续算缺价）。
    """
    tax = str(run.meta.get("计价方式") or TAX_EXCLUDED)
    new_records: List[dict] = []
    for rec in run.records:
        leaves: List[dict] = []
        for leaf in rec.get("leaves") or []:
            leaf = dict(leaf)
            if leaf.get("source") != PRICE_FROM_KINGDEE:
                res = table.lookup(str(leaf.get("code") or ""), tax)
                if res["ok"]:
                    cur = currency_code(res["currency"])
                    rate = manual_rate(cur, res["rate"], override_rate)
                    price = float(res["price"])
                    leaf.update({
                        "source": PRICE_FROM_MANUAL, "price_orig": price, "currency": cur,
                        "rate": rate, "price_cny": price * rate,
                        "amount_cny": price * rate * _num(leaf.get("qty")),
                        "bill_no": "", "bill_date": "", "hint": "",
                    })
                else:
                    leaf.update({
                        "source": "", "price_orig": 0.0, "currency": BASE_CURRENCY,
                        "rate": 1.0, "price_cny": 0.0, "amount_cny": 0.0,
                        "bill_no": "", "bill_date": "", "hint": res["reason"],
                    })
            leaves.append(leaf)
        new_records.append({
            "记录号": rec.get("记录号"),
            "issues": list(rec.get("issues") or []),
            "sale": dict(rec.get("sale") or {}),
            "leaves": leaves,
        })

    meta = dict(run.meta)
    meta["核算方式"] = "套用维护表重新计算（未重新登录金蝶）"
    meta["生成时间"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta["维护表"] = table.path
    meta["手工维护价口径"] = (
        f"金蝶取不到价的子件用维护表里的单价补位；{table.summary_text()}"
    )
    out = _finalize(new_records, meta, table)
    out.snapshot_path = run.snapshot_path
    return out


# ==================== 核算主体 ====================

class CostingCalculator:
    """按财务口径核算销售记录的料本与毛利"""

    def __init__(
        self,
        client,
        tax_mode: str = TAX_EXCLUDED,
        override_rate: Optional[float] = None,
        max_depth: int = 8,
        log: Optional[Callable[[str], None]] = None,
        manual_table: Optional[ManualPriceTable] = None,
    ):
        if tax_mode not in TAX_MODES:
            raise CostingError(f"计价方式只能是 {TAX_MODES}，收到 {tax_mode!r}")
        self.client = client
        self.tax_mode = tax_mode
        self.override_rate = float(override_rate) if override_rate else None
        self.max_depth = max_depth
        self.log = log or (lambda _t: None)
        self.manual_table = manual_table

        self._bom_cache: Dict[str, Optional[List[dict]]] = {}
        self._price_cache: Dict[str, Optional[dict]] = {}
        self._cost_cache: Dict[str, Tuple[float, List[dict], List[dict]]] = {}

        # 未税 / 含税 决定用哪个单价列
        self.price_field = "FPrice" if tax_mode == TAX_EXCLUDED else "FTaxPrice"

    # ---------------- 基础查询 ----------------

    def _query(self, form_id: str, field_keys: str, **kw) -> List[list]:
        try:
            rows = self.client.execute_bill_query(form_id=form_id, field_keys=field_keys, **kw)
        except KingdeeAPIError as exc:
            raise CostingError(f"查询 {form_id} 失败：{exc}") from exc
        return [r for r in rows if isinstance(r, (list, tuple))]

    def bom_of(self, material_code: str) -> Optional[List[dict]]:
        """取该物料最新一张已审核 BOM 的子件行；没有 BOM 返回 None"""
        if material_code in self._bom_cache:
            return self._bom_cache[material_code]

        heads = self._query(
            BOM_FORM, BOM_HEAD_FIELDS,
            filter_string=f"FMaterialId.FNumber='{material_code}' and FDocumentStatus='C'",
            order_string="FID DESC", limit=5,
        )
        if not heads:
            self._bom_cache[material_code] = None
            return None

        fid = heads[0][0]  # 同一 BOM 编号可能有重复单据，取 FID 最大的一张
        rows = self._query(BOM_FORM, BOM_ENTRY_FIELDS, filter_string=f"FID={fid}", limit=500)

        children: List[dict] = []
        for r in rows:
            if len(r) <= B_CHILD_CODE or not r[B_CHILD_CODE]:
                continue
            denominator = _num(r[B_DENOMINATOR], 1.0)
            children.append({
                "code": r[B_CHILD_CODE],
                "name": r[B_CHILD_NAME],
                "qty": _num(r[B_NUMERATOR], 1.0) / denominator if denominator else 1.0,
                "unit": r[B_UNIT],
                "bom_no": r[B_BILL_NO],
            })

        self._bom_cache[material_code] = children or None
        return self._bom_cache[material_code]

    def latest_purchase(self, material_code: str) -> Optional[dict]:
        """取该物料最近一次已审核采购价（单价为 0 的记录不算成交，会自动跳过）"""
        if material_code in self._price_cache:
            return self._price_cache[material_code]

        rows = self._query(
            PUR_FORM, PUR_FIELDS,
            filter_string=(
                f"FDocumentStatus='C' and FMaterialId.FNumber='{material_code}' "
                f"and {self.price_field} > 0"
            ),
            order_string="FID DESC", limit=1,
        )
        if not rows:
            self._price_cache[material_code] = None
            return None

        r = rows[0]
        rec = {
            "bill_no": r[P_BILL_NO],
            "date": str(r[P_DATE])[:10] if r[P_DATE] else "",
            "currency": r[P_CURRENCY] or BASE_CURRENCY,
            "rate": _num(r[P_RATE], 1.0) or 1.0,
            "no_tax_price": _num(r[P_PRICE]),
            "tax_price": _num(r[P_TAX_PRICE]),
        }
        rec["price"] = rec["no_tax_price"] if self.tax_mode == TAX_EXCLUDED else rec["tax_price"]
        self._price_cache[material_code] = rec
        return rec

    # ---------------- 汇率换算 ----------------

    def rate_of(self, currency: str, doc_rate: float) -> float:
        """折算汇率：界面指定了覆盖汇率就用它，否则用单据自带汇率"""
        if currency == BASE_CURRENCY:
            return 1.0
        if self.override_rate:
            return self.override_rate
        return doc_rate or 1.0

    # ---------------- BOM 递归展开 ----------------

    def _leaf(self, *, code, name, qty, unit, level, source, price_orig, currency,
              rate, price_cny, bill_no="", bill_date="", hint="") -> dict:
        return {
            "code": code, "name": name, "qty": qty, "unit": unit, "level": level,
            "source": source, "price_orig": price_orig, "currency": currency, "rate": rate,
            "price_cny": price_cny, "amount_cny": price_cny * qty,
            "bill_no": bill_no, "bill_date": bill_date, "hint": hint,
        }

    def expand(
        self,
        material_code: str,
        qty: float = 1.0,
        depth: int = 0,
        seen: Optional[set] = None,
        name: str = "",
        unit: str = "",
        out: Optional[List[dict]] = None,
        issues: Optional[List[dict]] = None,
    ) -> Tuple[List[dict], List[dict]]:
        """把物料展开到「没有 BOM 的叶子件」，叶子件带累计用量与采购价

        价格来源三选一：金蝶（最近采购价）/ 手工维护（财务填的单价）/ 空（仍缺价）
        """
        seen = set() if seen is None else seen
        out = [] if out is None else out
        issues = [] if issues is None else issues

        if depth > self.max_depth:
            issues.append({"code": material_code, "name": name, "reason": "BOM 层级超过上限，未继续展开"})
            return out, issues
        if material_code in seen:
            issues.append({"code": material_code, "name": name, "reason": "BOM 存在循环引用，已跳过"})
            return out, issues

        children = self.bom_of(material_code)
        if not children:
            price = self.latest_purchase(material_code)
            if price is not None:
                rate = self.rate_of(price["currency"], price["rate"])
                price_cny = price["price"] * rate
                out.append(self._leaf(
                    code=material_code, name=name, qty=qty, unit=unit, level=depth,
                    source=PRICE_FROM_KINGDEE, price_orig=price["price"],
                    currency=price["currency"], rate=rate, price_cny=price_cny,
                    bill_no=price["bill_no"], bill_date=price["date"],
                ))
                return out, issues

            # 金蝶没有价 → 看财务手工维护表里填了没有
            manual = (self.manual_table.lookup(material_code, self.tax_mode)
                      if self.manual_table is not None
                      else {"ok": False, "reason": ""})
            if manual["ok"]:
                cur = currency_code(manual["currency"])
                rate = manual_rate(cur, manual["rate"], self.override_rate)
                price_cny = float(manual["price"]) * rate
                out.append(self._leaf(
                    code=material_code, name=name, qty=qty, unit=unit, level=depth,
                    source=PRICE_FROM_MANUAL, price_orig=float(manual["price"]),
                    currency=cur, rate=rate, price_cny=price_cny,
                ))
                return out, issues

            hint = manual.get("reason") or ""
            if hint:
                self.log(f"      · 缺价子件 {material_code}：{hint}")
            out.append(self._leaf(
                code=material_code, name=name, qty=qty, unit=unit, level=depth,
                source="", price_orig=0.0, currency=BASE_CURRENCY, rate=1.0,
                price_cny=0.0, hint=hint,
            ))
            return out, issues

        next_seen = seen | {material_code}
        for child in children:
            self.expand(
                child["code"], qty * child["qty"], depth + 1, next_seen,
                name=child["name"], unit=child["unit"], out=out, issues=issues,
            )
        return out, issues

    def cost_of(self, material_code: str, name: str = "") -> Tuple[float, List[dict], List[dict]]:
        """单件料本（人民币）+ 子件明细 + 问题列表"""
        if material_code in self._cost_cache:
            return self._cost_cache[material_code]

        leaves, issues = self.expand(material_code, 1.0, 0, None, name=name)
        total = sum(x["amount_cny"] for x in leaves)

        # 同一子件同原因的问题去重，避免明细里刷屏
        uniq: List[dict] = []
        for item in issues:
            if not any(x["code"] == item["code"] and x["reason"] == item["reason"] for x in uniq):
                uniq.append(item)

        self._cost_cache[material_code] = (total, leaves, uniq)
        return self._cost_cache[material_code]

    # ---------------- 逐条销售记录核算 ----------------

    def fetch_sales(self, date_from: str, date_to: str, limit: int = 2000) -> List[list]:
        """取日期区间内已审核的销售订单分录行"""
        return self._query(
            SALE_FORM, SALE_FIELDS,
            filter_string=(
                f"FDocumentStatus='C' and FDate >= '{date_from}' and FDate <= '{date_to}'"
            ),
            order_string="FID DESC", limit=limit,
        )

    def run(self, date_from: str, date_to: str, limit: int = 2000) -> CostingRun:
        """按日期区间核算销售记录，返回 CostingRun（含缺价子件清单）"""
        date_from, date_to = normalize_range(date_from, date_to)
        rows = self.fetch_sales(date_from, date_to, limit)
        self.log(f"取到 {len(rows)} 条已审核销售记录（{date_from} ~ {date_to}）")

        records: List[dict] = []
        for i, r in enumerate(rows, 1):
            bill_no, date = r[S_BILL_NO], str(r[S_DATE])[:10]
            currency, doc_rate = r[S_CURRENCY] or BASE_CURRENCY, _num(r[S_RATE], 1.0) or 1.0
            code, mat_name = r[S_MAT_CODE], r[S_MAT_NAME]
            qty = _num(r[S_QTY])
            price_orig = _num(r[S_PRICE]) if self.tax_mode == TAX_EXCLUDED else _num(r[S_TAX_PRICE])

            rate = self.rate_of(currency, doc_rate)
            price_cny = price_orig * rate
            sale_amount = price_cny * qty

            unit_cost, leaves, issues = self.cost_of(code, name=mat_name)
            manual_cnt = sum(1 for x in leaves if x.get("source") == PRICE_FROM_MANUAL)
            missing_cnt = sum(1 for x in leaves if not x.get("source"))

            self.log(
                f"    [{i}/{len(rows)}] {bill_no} {code} × {qty:g} → 料本 {unit_cost * qty:,.2f}"
                f"（手工维护 {manual_cnt} 项）"
                + (f"，缺价 {missing_cnt} 项" if missing_cnt else "")
            )

            sale = {
                "月份": date[:7],
                "销售单号": bill_no,
                "单据日期": date,
                "币别": CURRENCY_NAMES.get(currency, currency),
                "汇率": rate,
                "产品编码": code,
                "产品名称": mat_name,
                "数量": qty,
                f"售价-{self.tax_mode}(原币)": price_orig,
                "售价(人民币)": price_cny,
                "销售额(人民币)": sale_amount,
            }
            records.append({
                "记录号": i, "issues": [x["reason"] for x in issues], "sale": sale,
                "leaves": leaves,
            })

        meta = self.build_meta(date_from, date_to, limit)
        return _finalize(records, meta, self.manual_table)

    def build_meta(self, date_from: str, date_to: str, limit: int = 0) -> Dict[str, object]:
        if self.manual_table is not None:
            manual_rule = (f"金蝶取不到价的子件用维护表里的单价补位；"
                           f"{self.manual_table.summary_text()}")
            table_path = self.manual_table.path
        else:
            manual_rule = "未启用维护表"
            table_path = f"未启用（默认位置：{MANUAL_TABLE_RELATIVE}）"
        return {
            "期间": range_label(date_from, date_to),
            "起始日期": date_from,
            "结束日期": date_to,
            "计价方式": self.tax_mode,
            "覆盖汇率": self.override_rate if self.override_rate else "未指定",
            "汇率处理": "单据自带汇率" if not self.override_rate else f"整批按 {self.override_rate} 折算",
            "采购取价": "该物料最近一次已审核采购行的单价（不限时点；单价为 0 不算成交）",
            "成本口径": "BOM 递归展开到没有 BOM 的叶子件，叶子件用量 × 单价汇总",
            "缺价处理": ("金蝶无采购价的子件 → 用本地维护表里财务填的单价补位；"
                         "维护表也没有则按 0 计并标注"),
            "维护表": table_path,
            "手工维护价口径": manual_rule,
            "记录上限": limit,
            "数据来源": "金蝶云星空 WebAPI（只读查询）",
            "生成时间": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


# ==================== 导出 Excel ====================

def _number_format(header: str) -> str:
    h = str(header)
    if "毛利率" in h:
        return "0.00%"
    if h == "汇率" or "汇率" in h:
        return "0.0000"
    if "人民币" in h or "原币" in h:
        return "#,##0.0000"
    if "数量" in h or "用量" in h or "次数" in h or "子件数" in h:
        return "#,##0.####"
    return "General"


def export_xlsx(path: str, run: CostingRun, extra_meta: Optional[dict] = None) -> str:
    """写出 Excel：逐条核算 / 区间汇总 / 子件价格总览 / 子件明细 / 缺价待维护 / 说明"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError as exc:  # pragma: no cover
        raise CostingError("导出 Excel 需要 openpyxl，请先安装：pip install openpyxl") from exc

    wb = Workbook()

    def fill(sheet, rows: List[dict], empty_hint: str = "（无数据）"):
        header = list(rows[0].keys()) if rows else [empty_hint]
        sheet.append(header)
        head_font = Font(bold=True)
        head_fill = PatternFill("solid", fgColor="DCE6F1")
        for cell in sheet[1]:
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
        for row in rows:
            sheet.append([row.get(h) for h in header])
        for idx, h in enumerate(header, 1):
            letter = get_column_letter(idx)
            sheet.column_dimensions[letter].width = max(
                10, min(30, max(len(str(h)) * 2 + 6, len(str(h)) + 4))
            )
            fmt = _number_format(h)
            if fmt != "General":
                for cell in sheet[letter][1:]:
                    cell.number_format = fmt
        if rows:
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = f"A1:{get_column_letter(len(header))}{len(rows) + 1}"
        return sheet

    fill(wb.active, run.summary, "（区间内没有已审核的销售记录）")
    wb.active.title = "逐条核算"

    fill(wb.create_sheet("区间汇总"), summarize_by_product(run.summary))

    fill(wb.create_sheet("子件价格总览"), run.children)

    fill(wb.create_sheet("子件明细"), run.details)

    missing_rows = list(run.missing)
    if not missing_rows:
        missing_rows = [{
            "子件编码": "（无）", "子件名称": "", "单位": "", "出现次数": 0, "涉及产品数": 0,
            "说明": "本次所有子件都有价（金蝶价或维护表手工价）",
        }]
    fill(wb.create_sheet("缺价待维护"), missing_rows)

    ws = wb.create_sheet("说明")
    ws["A1"] = "核算参数与口径"
    ws["A1"].font = Font(bold=True, size=12)
    meta = dict(run.meta)
    meta["记录数"] = len(run.summary)
    meta["本次手工维护子件数"] = sum(int(r.get("手工维护子件数") or 0) for r in run.summary)
    meta["仍缺价子件数"] = len(run.missing)
    if run.stale:
        meta["维护表提示"] = (f"有 {len(run.stale)} 个子件金蝶已有价（维护表该行未采用），"
                              f"详见「缺价待维护」表之后的提示")
    if extra_meta:
        meta.update(extra_meta)
    for i, (k, v) in enumerate(meta.items(), start=3):
        ws[f"A{i}"] = str(k)
        ws[f"B{i}"] = str(v)
    row_i = len(meta) + 5
    if run.stale:
        ws[f"A{row_i}"] = "维护表里金蝶已有价的子件（本次未采用手工价）"
        ws[f"A{row_i}"].font = Font(bold=True)
        for j, item in enumerate(run.stale, start=1):
            ws[f"A{row_i + j}"] = item["子件编码"]
            ws[f"B{row_i + j}"] = item["子件名称"]
            ws[f"C{row_i + j}"] = item["说明"]
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 70
    ws.column_dimensions["C"].width = 60

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    wb.save(path)
    return path
