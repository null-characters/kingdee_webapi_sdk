# -*- coding: utf-8 -*-
"""
成本核算核心：按月、逐条销售记录，用 BOM 展开 + 最近一次采购价算出料本与毛利。

与财务确认的口径（2026-09）：
    1) 按月结算，每个月里每一条销售记录单独计算
    2) 采购价取该物料「最近一次成交价」（最新一条已审核采购行，不限时点），默认按不含税算
    3) 按销售结算币别：外币（如美元）折成人民币后再比；默认用订单自带汇率，
       也可以整批指定一个汇率覆盖；取销售的「单价」列参与计算

实现要点（均在账套实测过）：
    - 币别字段是 FSettleCurrId（不是 FCurrencyId，后者不存在）；PRE001=人民币、PRE007=美元
    - 销售/采购单价：未税用 FPrice、含税用 FTaxPrice；人民币单价 = 原币单价 × 汇率
    - BOM 子件字段是 FMaterialIdChild.FNumber（不是 FMaterialIdCoby），用量 FNumerator/FDenominator
    - 同一 BOM 编号可能有多条重复单据，取 FID 最大的那张（已审核）
    - 采购订单的 FAmount（未税金额）实测恒为 0，所以金额一律用「单价 × 数量」自算
    - 单价为 0 的采购记录不算成交，取价时会自动跳过
"""

from __future__ import annotations

import datetime
from typing import Callable, Dict, List, Optional, Tuple

from .exceptions import KingdeeAPIError

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

NO_PRICE_NOTE = "缺采购价"


class CostingError(RuntimeError):
    """核算过程中的业务错误（账套拒绝、字段缺失等）"""


def _num(value, default: float = 0.0) -> float:
    """金蝶返回的数字可能是 None / 空串 / 字符串，统一转 float"""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def month_range(month: str) -> Tuple[str, str]:
    """'2026-09' -> ('2026-09-01', '2026-09-30')"""
    year, mon = (int(x) for x in month.split("-")[:2])
    first = datetime.date(year, mon, 1)
    nxt = datetime.date(year + 1, 1, 1) if mon == 12 else datetime.date(year, mon + 1, 1)
    return first.isoformat(), (nxt - datetime.timedelta(days=1)).isoformat()


class CostingCalculator:
    """按财务口径核算销售记录的料本与毛利"""

    def __init__(
        self,
        client,
        tax_mode: str = TAX_EXCLUDED,
        override_rate: Optional[float] = None,
        max_depth: int = 8,
        log: Optional[Callable[[str], None]] = None,
    ):
        if tax_mode not in TAX_MODES:
            raise CostingError(f"计价方式只能是 {TAX_MODES}，收到 {tax_mode!r}")
        self.client = client
        self.tax_mode = tax_mode
        self.override_rate = float(override_rate) if override_rate else None
        self.max_depth = max_depth
        self.log = log or (lambda _t: None)

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
        """把物料展开到「没有 BOM 的叶子件」，叶子件带累计用量与最近一次采购价"""
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
            if price is None:
                issues.append({"code": material_code, "name": name, "reason": "没有已审核采购记录，缺价"})
                out.append({
                    "code": material_code, "name": name, "level": depth, "qty": qty, "unit": unit,
                    "price_orig": 0.0, "currency": BASE_CURRENCY, "rate": 1.0,
                    "price_cny": 0.0, "amount_cny": 0.0, "bill_no": "", "bill_date": "",
                    "note": NO_PRICE_NOTE,
                })
                return out, issues

            rate = self.rate_of(price["currency"], price["rate"])
            price_cny = price["price"] * rate
            out.append({
                "code": material_code, "name": name, "level": depth, "qty": qty, "unit": unit,
                "price_orig": price["price"], "currency": price["currency"], "rate": rate,
                "price_cny": price_cny, "amount_cny": price_cny * qty,
                "bill_no": price["bill_no"], "bill_date": price["date"], "note": "",
            })
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

    def run(self, date_from: str, date_to: str, limit: int = 2000) -> Tuple[List[dict], List[dict]]:
        """按日期区间核算销售记录，返回 (汇总行, 子件明细行)"""
        rows = self._query(
            SALE_FORM, SALE_FIELDS,
            filter_string=(
                f"FDocumentStatus='C' and FDate >= '{date_from}' and FDate <= '{date_to}'"
            ),
            order_string="FID DESC", limit=limit,
        )
        summary: List[dict] = []
        details: List[dict] = []

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
            total_cost = unit_cost * qty
            gross = sale_amount - total_cost
            margin = (gross / sale_amount) if sale_amount else 0.0

            self.log(
                f"    [{i}/{len(rows)}] {bill_no} {code} × {qty:g} → "
                f"料本 {total_cost:,.2f}，毛利 {gross:,.2f}"
            )

            notes = []
            missing = sum(1 for x in leaves if x.get("note") == NO_PRICE_NOTE)
            if missing:
                notes.append(f"{missing} 个子件缺采购价")
            if not leaves:
                notes.append("未取到子件（该产品可能没有 BOM）")
            notes.extend(sorted({x["reason"] for x in issues}))

            summary.append({
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
                "单件料本(人民币)": unit_cost,
                "总料本(人民币)": total_cost,
                "毛利(人民币)": gross,
                "毛利率": margin,
                "子件数": len(leaves),
                "备注": "；".join(notes),
            })

            for leaf in leaves:
                details.append({
                    "销售单号": bill_no,
                    "产品编码": code,
                    "层级": leaf.get("level", ""),
                    "子件编码": leaf.get("code", ""),
                    "子件名称": leaf.get("name", ""),
                    "累计用量": leaf.get("qty", 0.0),
                    "单位": leaf.get("unit", ""),
                    f"采购价-{self.tax_mode}(原币)": leaf.get("price_orig", 0.0),
                    "采购币别": CURRENCY_NAMES.get(
                        leaf.get("currency", BASE_CURRENCY), leaf.get("currency", "")
                    ),
                    "采购汇率": leaf.get("rate", 1.0),
                    "采购价(人民币)": leaf.get("price_cny", 0.0),
                    "金额(人民币)": leaf.get("amount_cny", 0.0),
                    "采购单号": leaf.get("bill_no", ""),
                    "采购日期": leaf.get("bill_date", ""),
                    "备注": leaf.get("note", ""),
                })

        return summary, details


# ==================== 导出 Excel ====================


def export_xlsx(path: str, summary: List[dict], details: List[dict], meta: Optional[dict] = None) -> str:
    """写出 Excel（逐条核算 / 子件明细 / 说明 三个工作表）"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter
    except ImportError as exc:  # pragma: no cover
        raise CostingError("导出 Excel 需要 openpyxl，请先安装：pip install openpyxl") from exc

    wb = Workbook()

    def fill(sheet, rows: List[dict]):
        header = list(rows[0].keys()) if rows else ["（无数据）"]
        sheet.append(header)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in rows:
            sheet.append([row.get(h) for h in header])
        for idx, h in enumerate(header, 1):
            sheet.column_dimensions[get_column_letter(idx)].width = max(10, min(26, len(h) * 2 + 6))

    ws = wb.active
    ws.title = "逐条核算"
    fill(ws, summary)

    fill(wb.create_sheet("子件明细"), details)

    if meta:
        ws3 = wb.create_sheet("说明")
        ws3["A1"] = "核算参数与口径"
        ws3["A1"].font = Font(bold=True)
        for i, (k, v) in enumerate(meta.items(), start=3):
            ws3[f"A{i}"] = str(k)
            ws3[f"B{i}"] = str(v)
        ws3.column_dimensions["A"].width = 18
        ws3.column_dimensions["B"].width = 80

    wb.save(path)
    return path
