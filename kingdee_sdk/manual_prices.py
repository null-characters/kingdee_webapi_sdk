# -*- coding: utf-8 -*-
"""
本地长期产物：缺采购价子件的「手工维护价」表（CSV） + 上次核算快照

为什么要有这个模块
------------------
账套里有些子件**根本取不到采购价**（临时换料、采购还没录单、自制件没维护 BOM 等），
这部分成本不能一直按 0 计。所以流程是：

    1. 跑核算 → 扫描出所有「金蝶取不到采购价」的子件
    2. 把这些**料号直接预填进维护表 CSV**（单价列留空）
    3. 财务在 CSV 里**该行的单价列直接填**（Excel 双击即可打开，不乱码）
    4. 点「重新检查」→ 工具读这份 CSV，把填好的价算成「手工维护料本」
    5. 所有缺价子件都填完之后，才允许导出最终表格

存放位置（按优先级，优先复用**已存在**维护表的目录，避免换目录后另起一份空表）
----------------------------------------------------------------------
    1. 环境变量 ``KINGDEE_COSTING_DATA_DIR``（自定义）
    2. exe 所在目录下的 ``成本核算数据/``（源码环境为仓库根目录）
    3. 用户主目录下的 ``金蝶成本核算/``（exe 放在只读目录 / 网络盘时回退到这里）

CSV 约定
--------
- 编码 **utf-8-sig**（带 BOM）：Excel 双击打开不乱码；也兼容 GBK 保存的旧文件
- **子件编码是唯一键**：同一编码只保留一行，重复行会告警并只用第一条
- 表头被手改过也能认（支持「未税价 / 未税单价(元) / 币种」等别名）
- 工具只自动**新增**缺价料号、补空白的名称/单位；**绝不覆盖**已填的单价
"""

from __future__ import annotations

import csv
import datetime
import os
import sys
from collections import OrderedDict
from typing import Dict, Iterable, List, Optional

# ==================== 常量 ====================

MANUAL_CSV_NAME = "采购价维护表.csv"
SNAPSHOT_NAME = "上次核算快照.json.gz"
DATA_DIR_NAME = "成本核算数据"

# 单价列紧跟在「料号 / 名称 / 单位」后面，方便财务在这一行直接往后填
CSV_HEADERS = (
    "子件编码", "子件名称", "单位",
    "未税单价", "含税单价",
    "币别", "汇率", "供应商", "维护人", "更新时间", "备注",
)

# 表头别名：财务手改表头 / 旧文件也能认出来
HEADER_ALIASES = {
    "子件编码": ("子件编码", "料号", "子件料号", "物料编码", "编码", "物料编号", "子件编号"),
    "子件名称": ("子件名称", "名称", "物料名称", "子件描述"),
    "单位": ("单位", "计量单位", "采购单位"),
    "未税单价": ("未税单价", "未税价", "不含税单价", "不含税价", "未税单价(元)"),
    "含税单价": ("含税单价", "含税价", "含税单价(元)"),
    "币别": ("币别", "币种", "货币"),
    "汇率": ("汇率", "折算汇率"),
    "供应商": ("供应商", "供应商名称"),
    "维护人": ("维护人", "填写人", "维护者"),
    "更新时间": ("更新时间", "更新日期", "修改时间"),
    "备注": ("备注", "说明"),
}

NO_TAX_COL = "未税单价"
TAX_COL = "含税单价"


class ManualPriceError(RuntimeError):
    """维护表读写失败（文件被 Excel 占用、格式不可识别等）"""


# ==================== 小工具 ====================

def to_float(value) -> Optional[float]:
    """把单元格转成 float；空 / 非数字返回 None（区分「没填」和「填了 0」）"""
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("，", "")
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def today_str() -> str:
    return datetime.date.today().isoformat()


def base_dir() -> str:
    """exe 所在目录；源码环境返回仓库根目录"""
    if getattr(sys, "frozen", False):  # PyInstaller 打包后
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def candidate_data_dirs() -> List[str]:
    dirs: List[str] = []
    env = (os.getenv("KINGDEE_COSTING_DATA_DIR") or "").strip()
    if env:
        dirs.append(os.path.abspath(os.path.expanduser(env)))
    dirs.append(os.path.join(base_dir(), DATA_DIR_NAME))
    dirs.append(os.path.join(os.path.expanduser("~"), "金蝶成本核算"))
    # 去重但保持顺序
    seen, uniq = set(), []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


def _writable(target_dir: str) -> bool:
    """目录（或它最近的已存在父目录）是否可写；不创建任何目录"""
    probe = target_dir
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            return False
        probe = parent
    if not os.path.isdir(probe):
        return False
    return os.access(probe, os.W_OK)


def resolve_data_dir() -> str:
    """选数据目录：优先「已经有维护表/快照」的目录，否则第一个可写的目录"""
    cands = candidate_data_dirs()
    for d in cands:
        if os.path.exists(os.path.join(d, MANUAL_CSV_NAME)) or \
           os.path.exists(os.path.join(d, SNAPSHOT_NAME)):
            return d
    for d in cands:
        if _writable(d):
            return d
    return cands[-1]


def resolve_table_path(path: Optional[str] = None, data_dir: Optional[str] = None) -> str:
    """维护表 CSV 的绝对路径；显式给了 path 就用它"""
    if path:
        return os.path.abspath(os.path.expanduser(path))
    return os.path.join(data_dir or resolve_data_dir(), MANUAL_CSV_NAME)


def resolve_snapshot_path(data_dir: Optional[str] = None, path: Optional[str] = None) -> str:
    """上次核算快照的绝对路径（补价后「重新检查」用它，不用再登录金蝶）"""
    if path:
        return os.path.abspath(os.path.expanduser(path))
    return os.path.join(data_dir or resolve_data_dir(), SNAPSHOT_NAME)


def ensure_parent(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)


# ==================== 维护表 ====================

class ManualPriceTable:
    """缺采购价子件的单价维护表（本地 CSV，长期保留）

    用法：
        table = ManualPriceTable()              # 自动定位路径
        table.load()                           # 读现有表（文件不存在也不报错）
        table.add_missing([{"code":..., "name":..., "unit":...}])   # 预填缺价料号
        table.save()                           # 落盘
        table.lookup("料号", "未税")            # 取财务填的价
    """

    def __init__(self, path: Optional[str] = None, data_dir: Optional[str] = None,
                 log=None):
        self.path = resolve_table_path(path, data_dir)
        self.log = log or (lambda _t: None)
        self.rows: "OrderedDict[str, Dict[str, str]]" = OrderedDict()
        self.extra_fields: List[str] = []   # 文件里额外的列，保存时原样带上
        self.duplicates: List[str] = []     # 重复的料号
        self.header_ok = True
        self.error: Optional[str] = None
        self.loaded = False

    # ---------- 读 ----------

    def exists(self) -> bool:
        return os.path.exists(self.path)

    def load(self) -> "ManualPriceTable":
        self.rows.clear()
        self.extra_fields = []
        self.duplicates = []
        self.header_ok = True
        self.error = None
        self.loaded = True

        if not self.exists():
            return self

        try:
            with open(self.path, "r", encoding="utf-8-sig", newline="") as f:
                text = f.read()
        except UnicodeDecodeError:
            try:
                with open(self.path, "r", encoding="gbk", newline="") as f:
                    text = f.read()
            except Exception as exc:
                self.error = f"维护表读取失败（编码无法识别）：{exc}"
                return self
        except OSError as exc:
            self.error = f"维护表读取失败：{exc}"
            return self

        if not text.strip():
            return self

        reader = csv.reader(text.splitlines())
        try:
            raw_header = next(reader)
        except StopIteration:
            return self

        header = [str(h).replace("\ufeff", "").strip() for h in raw_header]
        # 表头 → 标准列名
        mapping: Dict[int, str] = {}
        for idx, name in enumerate(header):
            if not name:
                continue
            std = self._match_header(name)
            if std and std not in mapping.values():
                mapping[idx] = std
            elif name not in self.extra_fields and not std:
                self.extra_fields.append(name)

        if "子件编码" not in mapping.values():
            self.header_ok = False
            self.error = (f"维护表缺少「子件编码」列，已忽略未使用：{self.path}"
                          f"（表头：{'/'.join(header)}）")
            return self

        for raw in reader:
            if not any(str(c).strip() for c in raw):
                continue
            row = {std: "" for std in CSV_HEADERS}
            for idx, std in mapping.items():
                row[std] = str(raw[idx]).strip() if idx < len(raw) else ""
            for name in self.extra_fields:
                if name in header:
                    i = header.index(name)
                    row[name] = str(raw[i]).strip() if i < len(raw) else ""
            code = row.get("子件编码", "").strip()
            if not code:
                continue
            if code in self.rows:
                if code not in self.duplicates:
                    self.duplicates.append(code)
                continue
            self.rows[code] = row
        return self

    @staticmethod
    def _match_header(name: str) -> Optional[str]:
        clean = name.replace(" ", "").replace("（", "(").replace("）", ")").strip()
        for std, aliases in HEADER_ALIASES.items():
            for alias in aliases:
                if clean == alias or clean.startswith(alias):
                    return std
        return None

    # ---------- 写 ----------

    def save(self) -> str:
        """落盘（先写临时文件再替换，避免写一半把表写坏）"""
        ensure_parent(self.path)
        headers = list(CSV_HEADERS) + [c for c in self.extra_fields if c not in CSV_HEADERS]
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
                writer.writeheader()
                for row in self.rows.values():
                    writer.writerow({h: row.get(h, "") for h in headers})
            os.replace(tmp, self.path)
        except OSError as exc:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            raise ManualPriceError(
                f"维护表保存失败：{exc}\n"
                f"文件：{self.path}\n"
                f"如果它正被 Excel 打开，请先关闭 Excel 再点一次。"
            ) from exc
        return self.path

    def write_template(self) -> str:
        """表不存在时写一个只有表头的空表（让财务有东西可打开）"""
        if not self.exists():
            self.save()
        return self.path

    # ---------- 查 ----------

    def row_of(self, code: str) -> Optional[Dict[str, str]]:
        return self.rows.get(str(code).strip())

    def has_code(self, code: str) -> bool:
        return str(code).strip() in self.rows

    def lookup(self, code: str, tax_mode: str) -> Dict[str, object]:
        """查财务填的单价

        Returns:
            {"ok": bool, "reason": str, "price": float, "currency": str, "rate": float}
            ok=False 时 reason 说明为什么用不了（用来提示财务）
        """
        miss = {"ok": False, "reason": "", "price": None, "currency": "", "rate": 1.0}
        row = self.row_of(code)
        if row is None:
            return miss

        want = NO_TAX_COL if tax_mode == "未税" else TAX_COL
        other = TAX_COL if want == NO_TAX_COL else NO_TAX_COL
        raw = (row.get(want) or "").strip()
        price = to_float(raw)
        if price is None or price <= 0:
            other_val = to_float(row.get(other))
            if raw:
                miss["reason"] = f"维护表「{want}」填的内容无法识别：{raw}"
            elif other_val and other_val > 0:
                miss["reason"] = f"维护表只填了「{other}」，缺「{want}」"
            else:
                miss["reason"] = f"维护表有该行，但「{want}」还没填"
            return miss

        currency = (row.get("币别") or "").strip()
        rate = to_float(row.get("汇率")) or 0.0
        return {"ok": True, "reason": "", "price": price,
                "currency": currency, "rate": rate}

    # ---------- 增 / 改 ----------

    def add_missing(self, items: Iterable[dict]) -> Dict[str, int]:
        """把扫描出来的缺价子件料号预填进表（已存在的行绝不动它的单价）

        Args:
            items: 缺价子件清单，键名英文（code/name/unit）或中文（子件编码/子件名称/单位）都认，
                   所以可以直接把 ``CostingRun.missing`` 丢进来

        Returns:
            {"added": 新增行数, "backfilled": 补了名称/单位的行数}
        """
        added, backfilled = 0, 0
        new_rows: List[Dict[str, str]] = []
        for item in items:
            code = self._pick(item, "code", "子件编码")
            if not code:
                continue
            name = self._pick(item, "name", "子件名称")
            unit = self._pick(item, "unit", "单位")
            row = self.rows.get(code)
            if row is None:
                row = {std: "" for std in CSV_HEADERS}
                row["子件编码"] = code
                row["子件名称"] = name
                row["单位"] = unit
                row["更新时间"] = today_str()
                row["备注"] = "工具自动登记（缺采购价）"
                self.rows[code] = row
                new_rows.append(row)
                added += 1
            else:
                changed = False
                if not (row.get("子件名称") or "").strip() and name:
                    row["子件名称"] = name
                    changed = True
                if not (row.get("单位") or "").strip() and unit:
                    row["单位"] = unit
                    changed = True
                if changed:
                    backfilled += 1
        # 新增的行按料号排序插到末尾，方便财务找
        new_rows.sort(key=lambda r: r["子件编码"])
        if new_rows:
            ordered = OrderedDict()
            new_set = {id(r) for r in new_rows}
            for code, row in self.rows.items():
                if id(row) not in new_set:
                    ordered[code] = row
            for row in new_rows:
                ordered[row["子件编码"]] = row
            self.rows = ordered
        return {"added": added, "backfilled": backfilled}

    @staticmethod
    def _pick(item: dict, *keys: str) -> str:
        for k in keys:
            val = item.get(k)
            if val is not None and str(val).strip():
                return str(val).strip()
        return ""

    def filled_count(self) -> Dict[str, int]:
        """统计表里已填单价的行数（给界面/日志显示）"""
        no_tax = tax = both = 0
        for row in self.rows.values():
            a = to_float(row.get(NO_TAX_COL))
            b = to_float(row.get(TAX_COL))
            if a and a > 0:
                no_tax += 1
            if b and b > 0:
                tax += 1
            if a and a > 0 and b and b > 0:
                both += 1
        return {"rows": len(self.rows), "未税": no_tax, "含税": tax, "both": both}

    def summary_text(self) -> str:
        st = self.filled_count()
        return (f"维护表 {st['rows']} 行（已填未税价 {st['未税']} 行、"
                f"含税价 {st['含税']} 行）")
