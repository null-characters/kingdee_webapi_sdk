# -*- coding: utf-8 -*-
"""
金蝶成本核算工具（内部小工具）—— 图形界面

给财务同事用：
    1. 双击 exe → 输入自己的金蝶账号密码 → 「登录并自检」确认能取数
    2. 填「统计区间」（整月，或 5 号~15 号这种任意区间）→ 「开始核算并导出 Excel」
    3. 如果扫描出「缺采购价」的子件：工具会把这些料号**预填进本地的采购价维护表 CSV**，
       并弹出清单提示补价；**补完之前不会导出最终表格**
    4. 用 Excel 打开维护表，在缺价料号那一行的「未税单价 / 含税单价」里填价 → 保存
    5. 回到工具点「重新检查」（不用重新登录金蝶，秒级）→ 全部补齐后自动导出最终表格

说明：
    - 服务器地址、账套 ID 已固定写在 selfcheck.py 的 FIXED_CONFIG 里，界面上不可修改
    - 密码只保存在内存，不落盘、不写入日志
    - 所有对金蝶的操作都是只读查询（不新增、不修改、不删除任何单据）
    - 采购价维护表是本地长期产物（CSV，utf-8-sig，Excel 双击不乱码）

核算口径（与财务确认）：
    - 按日期区间结算，区间内每条销售记录单独计算
    - 采购价取该物料「最近一次成交价」（最新一条已审核采购行，不限时点）
    - 外币按汇率折人民币（默认用单据自带汇率，可手工指定覆盖）
    - 含税 / 未税 可切换（默认未税）
    - 缺价子件：金蝶价优先；金蝶取不到价时用手工维护价补位，
      成本分三列：自动料本（金蝶）+ 手工维护料本 = 最终料本

附属命令行参数（排查问题用）：
    --check        无界面自检（等价于 selfcheck.py --check）
    --costing      无界面核算：--costing --month 2026-09 或 --from 2026-09-05 --to 2026-09-15
                   [--tax 未税|含税] [--rate 6.7809] [--limit 50] [--allow-missing] [--recheck]
    --smoke-gui    只构建一次窗口后退出（验证界面）
    --smoke-dialog 用假数据构建一次缺价补全对话框后退出（验证界面）
"""

import argparse
import datetime
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import traceback

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(_ROOT, "kingdee_sdk")) and _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# GUI 依赖延迟判断：万一环境缺 tkinter，--check / --costing 仍然可用
try:
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk
    _TK_ERROR = None
except Exception as _exc:  # pragma: no cover
    tk = ttk = scrolledtext = messagebox = None
    _TK_ERROR = _exc

from selfcheck import APP_TITLE, APP_VERSION, FIXED_CONFIG, build_client, run_selfcheck  # noqa: E402

try:
    from kingdee_sdk import KingdeeAPIError
    from kingdee_sdk.costing import (
        TAX_EXCLUDED,
        TAX_INCLUDED,
        CostingCalculator,
        CostingError,
        check_recalc_compatible,
        export_xlsx,
        load_snapshot,
        month_bounds,
        month_range,
        normalize_range,
        range_file_label,
        range_label,
        recalculate,
        save_snapshot,
    )
    from kingdee_sdk.manual_prices import ManualPriceError, ManualPriceTable, to_float
    _COSTING_ERROR = None
except Exception as _exc:  # pragma: no cover
    CostingCalculator = export_xlsx = None
    ManualPriceTable = None
    KingdeeAPIError = RuntimeError
    TAX_EXCLUDED, TAX_INCLUDED = "未税", "含税"
    CostingError = ManualPriceError = RuntimeError
    _COSTING_ERROR = _exc

LOG_PATH = os.path.join(tempfile.gettempdir(), "kingdee_tool.log")
MISSING_ROW_LIMIT = 500  # 对话框最多显示多少行（其余请看维护表）


def desktop_dir() -> str:
    """Excel 默认导出到桌面（找不到桌面就用用户主目录）"""
    home = os.path.expanduser("~")
    for name in ("Desktop", "桌面"):
        path = os.path.join(home, name)
        if os.path.isdir(path):
            return path
    return home


def open_path(path: str):
    """用系统默认程序打开文件/文件夹"""
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606 - Windows
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def log_to_file(text):
    """把关键信息追加到临时目录日志（不含密码）"""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
    except Exception:
        pass


def override_from_meta(meta: dict):
    """把快照 meta 里记录的覆盖汇率还原成 float / None"""
    return to_float(meta.get("覆盖汇率"))


# ==================== 与界面无关的核心流程（命令行也能用） ====================

def load_table(manual_path=None, log=print) -> "ManualPriceTable":
    if ManualPriceTable is None:
        raise CostingError(f"核算模块加载失败：{_COSTING_ERROR}")
    # 兼容「未启用」这种占位文字（不该被当成路径）
    if manual_path and ("未启用" in str(manual_path) or not str(manual_path).strip()):
        manual_path = None
    table = ManualPriceTable(manual_path).load()
    if table.error:
        log(f"[维护表告警] {table.error}")
    if table.duplicates:
        log(f"[维护表告警] 维护表有重复料号（只用第一条）："
            f"{'、'.join(table.duplicates[:8])}")
    return table


def scan_once(username, password, date_from, date_to, tax_mode, override_rate,
              limit=5000, manual_path=None, log=print):
    """登录 → 按区间核算 → 缺价料号预填维护表 → 存快照（**不导出**）

    Returns: (ok, msg, run, table)
    """
    if CostingCalculator is None:
        return False, f"核算模块加载失败：{_COSTING_ERROR}", None, None

    date_from, date_to = normalize_range(date_from, date_to)
    table = load_table(manual_path, log)
    log(f"维护表：{table.path}（{table.summary_text()}）")

    client = build_client(username, password)
    try:
        log(f"正在登录（{username}）……")
        client.login()
        log(f"登录成功，开始核算 {range_label(date_from, date_to)}（计价：{tax_mode}"
            f"{'，覆盖汇率 ' + str(override_rate) if override_rate else ''}）")
        calc = CostingCalculator(client, tax_mode=tax_mode, override_rate=override_rate,
                                 manual_table=table, log=log)
        run = calc.run(date_from, date_to, limit=limit)
    finally:
        try:
            client.logout()
        except Exception:
            pass

    if not run.summary:
        return False, (f"{range_label(date_from, date_to)} 没有已审核的销售记录"
                       f"（或该账号查不到数据）"), run, table

    # 缺价料号预填进维护表（本地长期产物）
    stats = table.add_missing(run.missing)
    if stats["added"] or stats["backfilled"]:
        try:
            table.save()
            log(f"[维护表] 已把缺价料号预填进维护表：新增 {stats['added']} 行，"
                f"补全名称/单位 {stats['backfilled']} 行 → {table.path}")
        except ManualPriceError as exc:
            log(f"[维护表告警] {exc}")

    # 存快照：补价后「重新检查」用它，不用再登录
    try:
        run.snapshot_path = save_snapshot(run)
        log(f"[快照] 已保存本次取数结果（补价后可直接重算）：{run.snapshot_path}")
    except OSError as exc:
        log(f"[快照告警] 保存失败（不影响本次核算）：{exc}")

    t = run.totals()
    log(f"核算完成：{len(run.summary)} 条销售记录，{len(run.details)} 行子件明细；"
        f"自动料本 {t['自动料本']:,.2f}，手工维护料本 {t['手工维护料本']:,.2f}，"
        f"最终料本 {t['最终料本']:,.2f}")
    return True, f"扫描完成：{len(run.summary)} 条记录", run, table


def recheck_once(run, tax_mode, override_rate, manual_path=None, log=print):
    """读最新的维护表 CSV，重新定价（不登录金蝶）

    Returns: (ok, msg, run, table)
    """
    if run is None:
        return False, "还没有核算结果，请先点「开始核算」取一次数。", None, None
    table = load_table(manual_path or (run.meta.get("维护表") or None), log)
    log(f"重新读取维护表：{table.path}（{table.summary_text()}）")
    new_run = recalculate(run, table, override_rate=override_rate)
    new_run.snapshot_path = run.snapshot_path
    t = new_run.totals()
    if new_run.complete:
        log(f"✅ 缺价已全部补齐：手工维护料本 {t['手工维护料本']:,.2f}，"
            f"最终料本 {t['最终料本']:,.2f}")
    else:
        log(f"仍有 {len(new_run.missing)} 个子件缺采购价，请继续在维护表里补价：")
        for m in new_run.missing[:20]:
            log(f"    {m['子件编码']}（{m['子件名称']}，{m['单位']}）{m['说明']}")
    return True, f"重新检查完成：仍缺 {len(new_run.missing)} 个子件", new_run, table


def recheck_from_snapshot(tax_mode, override_rate, manual_path=None, log=print):
    """不登录金蝶：用上次快照 + 最新维护表重算

    Returns: (ok, msg, run, table)
    """
    try:
        base = load_snapshot()
    except CostingError as exc:
        return False, str(exc), None, None
    problem = check_recalc_compatible(base.meta, tax_mode, override_rate)
    if problem:
        return False, problem, None, None
    log(f"用上次取数的快照重算（区间 {base.meta.get('期间')}）：{base.snapshot_path}")
    run, table = None, None
    ok, msg, run, table = recheck_once(base, tax_mode, override_rate, manual_path, log)
    if ok:
        run.snapshot_path = base.snapshot_path
    return ok, msg, run, table


def default_out_path(run, forced=False) -> str:
    """导出路径：桌面/成本核算_区间_计价[_含缺价].xlsx（已存在就加时间戳，不覆盖）"""
    label = range_file_label(str(run.meta.get("起始日期") or ""), str(run.meta.get("结束日期") or ""))
    name = f"成本核算_{label}_{run.meta.get('计价方式')}"
    if forced:
        name += "_含缺价"
    path = os.path.join(desktop_dir(), name + ".xlsx")
    if os.path.exists(path):
        stamp = datetime.datetime.now().strftime("%H%M%S")
        path = os.path.join(desktop_dir(), f"{name}_{stamp}.xlsx")
    return path


def export_run_once(run, out_path=None, log=print):
    """导出最终表格（缺价未补齐时由调用方决定是否强制导出）

    Returns: (ok, msg, path)
    """
    if run is None:
        return False, "没有可导出的核算结果。", ""
    forced = not run.complete
    target = out_path or default_out_path(run, forced=forced)
    extra = {
        "导出说明": ("仍有缺价子件，按 0 计（强制导出）" if forced
                     else "缺价子件已全部补齐"),
        "缺价子件数": len(run.missing),
        "本次手工维护子件数": sum(int(r.get("手工维护子件数") or 0) for r in run.summary),
    }
    export_xlsx(target, run, extra_meta=extra)
    log(f"已导出 Excel：{target}")
    return True, (f"已导出 {len(run.summary)} 条记录到：\n{target}"), target


# ==================== 缺价补全对话框 ====================

class MissingPriceDialog(tk.Toplevel if tk else object):
    """缺价子件清单：提示财务在维护表 CSV 的这些行里填单价"""

    COLUMNS = (
        ("子件编码", 150), ("子件名称", 190), ("单位", 60),
        ("出现次数", 70), ("涉及产品数", 80), ("说明", 320),
    )

    def __init__(self, master, app, run, table):
        super().__init__(master)
        self.app = app
        self.table = table
        self.run = run
        self.busy = False

        self.title(f"缺采购价子件（{len(run.missing)} 个）——请先补价")
        self.geometry("900x520")
        self.minsize(760, 420)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build()
        self.refresh(run)
        try:
            self.transient(master)
            self.grab_set()
        except Exception:
            pass

    # ---------- 搭建 ----------
    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(10, 4))

        ttk.Label(
            top,
            text=("扫描出以下子件在金蝶里取不到采购价。工具已经把料号预填进维护表，"
                  "请用 Excel 打开维护表，在对应那一行的「未税单价 / 含税单价」里填价，"
                  "保存后回来点「重新检查」。"),
            wraplength=860, justify="left", foreground="#8a4b00",
        ).pack(anchor="w")

        path_row = ttk.Frame(self)
        path_row.pack(fill="x", padx=12, pady=(2, 6))
        ttk.Label(path_row, text="采购价维护表：").pack(side="left")
        self.var_path = tk.StringVar(value=self.table.path)
        ttk.Label(path_row, textvariable=self.var_path, foreground="#1a4f8b").pack(
            side="left", fill="x", expand=True)
        ttk.Button(path_row, text="打开所在文件夹", command=self.on_open_dir).pack(side="right")
        ttk.Button(path_row, text="打开维护表填写", command=self.on_open_table).pack(
            side="right", padx=(0, 6))

        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=12, pady=4)
        self.tree = ttk.Treeview(mid, columns=[c for c, _w in self.COLUMNS], show="headings")
        for name, width in self.COLUMNS:
            self.tree.heading(name, text=name)
            self.tree.column(name, width=width, anchor="w", stretch=(name == "说明"))
        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("odd", background="#f6f8fb")

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=12, pady=(6, 12))
        self.var_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(bottom, text="显示全部子件（含已有价的）", variable=self.var_all,
                        command=lambda: self.refresh(self.run)).pack(side="left")
        self.var_status = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.var_status, foreground="#555").pack(
            side="left", padx=(10, 0))
        self.btn_force = ttk.Button(bottom, text="仍有缺价也导出（按 0 计）",
                                    command=self.on_force_export)
        self.btn_force.pack(side="right")
        self.btn_check = ttk.Button(bottom, text="重新检查（读维护表）", command=self.on_recheck)
        self.btn_check.pack(side="right", padx=(0, 6))
        self.btn_close = ttk.Button(bottom, text="关闭", command=self.on_close)
        self.btn_close.pack(side="right", padx=(0, 6))

    # ---------- 数据 ----------
    def refresh(self, run):
        self.run = run
        show_all = bool(self.var_all.get())
        rows = run.children if show_all else run.missing
        self.tree.heading("说明", text="价格来源" if show_all else "说明")
        self.tree.delete(*self.tree.get_children())
        for i, m in enumerate(rows[:MISSING_ROW_LIMIT]):
            last = (m.get("价格来源", "") if show_all else m.get("说明", ""))
            self.tree.insert("", "end", values=(
                m.get("子件编码", ""), m.get("子件名称", ""), m.get("单位", ""),
                m.get("出现次数", ""), m.get("涉及产品数", ""), last,
            ), tags=("odd",) if i % 2 else ())
        n_missing = len(run.missing)
        self.title(f"缺采购价子件（{n_missing} 个）——请先补价")
        tail = f"（只显示前 {MISSING_ROW_LIMIT} 行，其余请看维护表）" \
            if len(rows) > MISSING_ROW_LIMIT else ""
        if show_all:
            self.var_status.set(f"共 {len(run.children)} 个子件，其中 {n_missing} 个缺价{tail}")
        else:
            self.var_status.set(f"还有 {n_missing} 个子件没填价{tail}，"
                                f"补完才能导出最终表格。")

    def set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for btn in (self.btn_check, self.btn_force, self.btn_close):
            btn.config(state=state)
        if busy:
            self.var_status.set("正在读取维护表并重新计算……")

    # ---------- 按钮 ----------
    def on_open_table(self):
        try:
            self.table.load()
            if not self.table.exists():
                self.table.save()
            open_path(self.table.path)
        except Exception as exc:
            messagebox.showwarning("打不开维护表", f"{exc}", parent=self)

    def on_open_dir(self):
        try:
            open_path(os.path.dirname(os.path.abspath(self.table.path)))
        except Exception as exc:
            messagebox.showwarning("打不开文件夹", f"{exc}", parent=self)

    def on_recheck(self):
        self.app.recheck_job(self)

    def on_force_export(self):
        n = len(self.run.missing)
        if not messagebox.askyesno(
            "确认强制导出",
            f"还有 {n} 个子件没填价。强制导出的话，这些子件成本按 0 计"
            f"（毛利会偏高），Excel 里会标注出来。\n\n确定要导出吗？",
            parent=self,
        ):
            return
        self.app.export_job(self.run, forced=True, dialog=self)

    def on_close(self):
        if self.busy:
            return
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


# ==================== 主窗口 ====================

class ToolApp:
    """主窗口"""

    def __init__(self, root):
        self.root = root
        self.queue = queue.Queue()
        self.running = False
        self.current_run = None
        self.table = None
        self.dialog = None

        root.title(f"{APP_TITLE} v{APP_VERSION}")
        root.geometry("980x760")
        root.minsize(840, 620)

        self._build_fixed_info()
        self._build_login_area()
        self._build_costing_area()
        self._build_log_area()
        self._build_status_bar()

        self.root.after(100, self._poll_queue)
        self._log(f"{APP_TITLE} v{APP_VERSION}")
        self._log("第 1 步：填账号密码 → 点「登录并自检」，确认账号能取数。")
        self._log("第 2 步：填统计区间（整月或任意起止日期）→ 点「开始核算并导出 Excel」。")
        self._log("第 3 步：如果提示有子件缺采购价，维护表里已预填好料号；")
        self._log("        用 Excel 打开维护表在那一行填单价 → 回来点「重新检查」→ 补齐后自动导出。")
        self._log("说明：本工具只做只读查询（不新增、不修改、不删除任何单据）。")
        self._show_table_path()

    # ---------------- 界面搭建 ----------------

    def _build_fixed_info(self):
        frame = ttk.LabelFrame(self.root, text="固定配置（不可修改）")
        frame.pack(fill="x", padx=12, pady=(12, 6))
        rows = [
            ("金蝶服务器", FIXED_CONFIG["server_url"]),
            ("账套（数据中心）", FIXED_CONFIG["acct_id"]),
            ("登录方式", "用户名 + 密码（密码不保存）"),
        ]
        for i, (k, v) in enumerate(rows):
            ttk.Label(frame, text=k + "：").grid(row=i, column=0, sticky="e", padx=(10, 4), pady=2)
            ttk.Label(frame, text=str(v), foreground="#1a4f8b").grid(
                row=i, column=1, sticky="w", padx=(0, 10), pady=2
            )
        return frame

    def _build_login_area(self):
        frame = ttk.LabelFrame(self.root, text="第 1 步：登录")
        frame.pack(fill="x", padx=12, pady=6)

        ttk.Label(frame, text="金蝶账号：").grid(row=0, column=0, sticky="e", padx=(10, 4), pady=6)
        self.entry_user = ttk.Entry(frame, width=24)
        self.entry_user.grid(row=0, column=1, sticky="w", pady=6)

        ttk.Label(frame, text="密码：").grid(row=0, column=2, sticky="e", padx=(16, 4), pady=6)
        self.entry_pwd = ttk.Entry(frame, width=24, show="*")
        self.entry_pwd.grid(row=0, column=3, sticky="w", pady=6)

        self.var_show_pwd = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame, text="显示密码", variable=self.var_show_pwd, command=self._toggle_pwd
        ).grid(row=0, column=4, sticky="w", padx=(10, 6))

        self.btn_run = ttk.Button(frame, text="登录并自检", command=self.on_run)
        self.btn_run.grid(row=1, column=1, sticky="w", pady=(2, 10))
        ttk.Button(frame, text="清空日志", command=self.on_clear).grid(
            row=1, column=2, sticky="e", pady=(2, 10)
        )
        ttk.Button(frame, text="打开日志文件夹", command=self.on_open_log_dir).grid(
            row=1, column=3, sticky="w", padx=(6, 0), pady=(2, 10)
        )
        ttk.Button(frame, text="退出", command=self.root.destroy).grid(
            row=1, column=4, sticky="w", padx=(6, 10), pady=(2, 10)
        )

        for w in (self.entry_user, self.entry_pwd):
            w.bind("<Return>", lambda _e: self.on_run())
        self.entry_user.focus_set()
        return frame

    def _build_costing_area(self):
        frame = ttk.LabelFrame(self.root, text="第 2 步：成本核算（销售价 vs 采购价）")
        frame.pack(fill="x", padx=12, pady=6)

        # ---- 统计区间 ----
        ttk.Label(frame, text="统计区间：").grid(row=0, column=0, sticky="e", padx=(10, 4), pady=6)
        first, last = month_bounds(0)
        self.entry_from = ttk.Entry(frame, width=13)
        self.entry_from.insert(0, first)
        self.entry_from.grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(frame, text=" ~ ").grid(row=0, column=2, sticky="w")
        self.entry_to = ttk.Entry(frame, width=13)
        self.entry_to.insert(0, last)
        self.entry_to.grid(row=0, column=3, sticky="w", pady=6)
        ttk.Button(frame, text="本月", width=6,
                   command=lambda: self._fill_month(0)).grid(row=0, column=4, padx=(10, 2))
        ttk.Button(frame, text="上月", width=6,
                   command=lambda: self._fill_month(-1)).grid(row=0, column=5, padx=(0, 6))
        ttk.Label(frame, text="格式 2026-09-05（可只算 5 号到 15 号）", foreground="#888").grid(
            row=0, column=6, columnspan=2, sticky="w", padx=(6, 10))

        # ---- 计价 / 汇率 ----
        ttk.Label(frame, text="计价方式：").grid(row=1, column=0, sticky="e", padx=(10, 4), pady=6)
        self.var_tax = tk.StringVar(value=TAX_EXCLUDED)
        ttk.Radiobutton(frame, text="未税", value=TAX_EXCLUDED, variable=self.var_tax).grid(
            row=1, column=1, sticky="w")
        ttk.Radiobutton(frame, text="含税", value=TAX_INCLUDED, variable=self.var_tax).grid(
            row=1, column=2, sticky="w", padx=(4, 10))

        ttk.Label(frame, text="覆盖汇率：").grid(row=1, column=3, sticky="e", padx=(10, 4), pady=6)
        self.entry_rate = ttk.Entry(frame, width=13)
        self.entry_rate.grid(row=1, column=4, sticky="w", pady=6)
        ttk.Label(frame, text="留空 = 用单据自带汇率", foreground="#888").grid(
            row=1, column=5, columnspan=3, sticky="w", padx=(6, 10))

        # ---- 按钮 ----
        self.btn_costing = ttk.Button(
            frame, text="开始核算并导出 Excel", command=self.on_run_costing
        )
        self.btn_costing.grid(row=2, column=1, sticky="w", pady=(2, 10))
        self.btn_recheck = ttk.Button(
            frame, text="套用维护表重新导出（不用登录）", command=self.on_recheck_snapshot
        )
        self.btn_recheck.grid(row=2, column=2, columnspan=2, sticky="w", pady=(2, 10))
        ttk.Label(frame, text="结果导出到桌面", foreground="#888").grid(
            row=2, column=4, columnspan=4, sticky="w", pady=(2, 10))

        # ---- 维护表 ----
        table_row = ttk.Frame(frame)
        table_row.grid(row=3, column=0, columnspan=8, sticky="we", padx=10, pady=(0, 10))
        ttk.Label(table_row, text="采购价维护表：").pack(side="left")
        self.var_table = tk.StringVar(value="（正在定位……）")
        ttk.Label(table_row, textvariable=self.var_table, foreground="#1a4f8b").pack(
            side="left", fill="x", expand=True)
        ttk.Button(table_row, text="打开所在文件夹", command=self.on_open_table_dir).pack(side="right")
        ttk.Button(table_row, text="打开维护表", command=self.on_open_table).pack(
            side="right", padx=(0, 6))
        return frame

    def _build_log_area(self):
        frame = ttk.LabelFrame(self.root, text="运行结果")
        frame.pack(fill="both", expand=True, padx=12, pady=6)
        self.txt = scrolledtext.ScrolledText(frame, height=16, wrap="word", state="disabled")
        self.txt.pack(fill="both", expand=True, padx=8, pady=8)
        return frame

    def _build_status_bar(self):
        self.var_status = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.var_status, anchor="w", foreground="#555").pack(
            fill="x", padx=14, pady=(0, 10)
        )

    # ---------------- 小动作 ----------------

    def _toggle_pwd(self):
        self.entry_pwd.config(show="" if self.var_show_pwd.get() else "*")

    def _fill_month(self, offset):
        first, last = month_bounds(offset)
        self.entry_from.delete(0, "end")
        self.entry_from.insert(0, first)
        self.entry_to.delete(0, "end")
        self.entry_to.insert(0, last)

    def _show_table_path(self):
        try:
            table = load_table(log=self._log_quiet)
            self.table = table
            self.var_table.set(table.path)
        except Exception as exc:
            self.var_table.set(f"定位失败：{exc}")

    def _log_quiet(self, text):
        log_to_file(str(text))

    def on_clear(self):
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.config(state="disabled")

    def on_open_log_dir(self):
        folder = os.path.dirname(LOG_PATH)
        try:
            open_path(folder)
        except Exception as exc:
            self._log(f"打开日志文件夹失败：{exc}")

    def on_open_table(self):
        try:
            table = self.table or load_table(log=self._log)
            table.load()
            if not table.exists():
                table.save()
                self._log(f"维护表不存在，已生成空表：{table.path}")
            open_path(table.path)
            self._log(f"已打开维护表：{table.path}")
        except Exception as exc:
            messagebox.showwarning("打不开维护表", f"{exc}")

    def on_open_table_dir(self):
        try:
            table = self.table or load_table(log=self._log)
            open_path(os.path.dirname(os.path.abspath(table.path)))
        except Exception as exc:
            messagebox.showwarning("打不开文件夹", f"{exc}")

    def _read_credentials(self):
        user = self.entry_user.get().strip()
        pwd = self.entry_pwd.get()
        if not user or not pwd:
            messagebox.showwarning("提示", "请先填写金蝶账号和密码。")
            return None, None
        return user, pwd

    def _read_period(self):
        try:
            return normalize_range(self.entry_from.get().strip(), self.entry_to.get().strip())
        except CostingError as exc:
            messagebox.showwarning("统计区间不对", str(exc))
            return None

    def _read_rate(self):
        text = self.entry_rate.get().strip()
        if not text:
            return True, None
        try:
            rate = float(text)
            if rate <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "覆盖汇率要填正数，比如 6.7809；留空表示用单据自带汇率。")
            return False, None
        return True, rate

    def _start_job(self, target, args, status_text, file_log, clear_log=True):
        if self.running:
            return
        self.running = True
        self.btn_run.config(state="disabled")
        self.btn_costing.config(state="disabled")
        self.btn_recheck.config(state="disabled")
        self.var_status.set(status_text)
        if clear_log:
            self.on_clear()
        log_to_file(file_log)
        threading.Thread(target=target, args=args, daemon=True).start()

    def _finish_job(self):
        self.running = False
        self.btn_run.config(state="normal")
        self.btn_costing.config(state="normal")
        self.btn_recheck.config(state="normal")

    # ---------------- 按钮入口 ----------------

    def on_run(self):
        user, pwd = self._read_credentials()
        if not user:
            return
        self._start_job(self._worker_selfcheck, (user, pwd),
                        "正在登录并自检……", f"开始自检，账号={user}")

    def on_run_costing(self):
        user, pwd = self._read_credentials()
        if not user:
            return
        period = self._read_period()
        if period is None:
            return
        ok, rate = self._read_rate()
        if not ok:
            return
        date_from, date_to = period
        self._start_job(
            self._worker_scan, (user, pwd, date_from, date_to, self.var_tax.get(), rate),
            f"正在核算 {range_label(date_from, date_to)}（{self.var_tax.get()}）……",
            f"开始核算 {date_from}~{date_to} {self.var_tax.get()}，账号={user}",
        )

    def on_recheck_snapshot(self):
        ok, rate = self._read_rate()
        if not ok:
            return
        self._start_job(
            self._worker_recheck_snapshot, (self.var_tax.get(), rate),
            "正在套用维护表重新计算（不用登录）……",
            f"套用维护表重算 {self.var_tax.get()}",
        )

    # ---------------- 后台线程 ----------------

    def _worker_selfcheck(self, user, pwd):
        def log(text):
            self.queue.put(str(text))

        try:
            ok, msg = run_selfcheck(user, pwd, log=log)
        except Exception:
            detail = traceback.format_exc()
            log_to_file("未预期异常：\n" + detail)
            log("发生未预期异常：")
            log(detail)
            ok, msg = False, "程序内部错误，请把本窗口内容发给管理员"
        self.queue.put({"job": "selfcheck", "ok": ok, "msg": msg})

    def _worker_scan(self, user, pwd, date_from, date_to, tax_mode, rate):
        def log(text):
            self.queue.put(str(text))

        run = table = None
        try:
            ok, msg, run, table = scan_once(user, pwd, date_from, date_to, tax_mode, rate,
                                           limit=5000, log=log)
        except KingdeeAPIError as exc:
            log(f"登录/取数失败：{exc}")
            ok, msg = False, f"登录或取数失败：{exc}"
        except CostingError as exc:
            log(f"核算失败：{exc}")
            ok, msg = False, str(exc)
        except ManualPriceError as exc:
            log(f"维护表错误：{exc}")
            ok, msg = False, str(exc)
        except Exception:
            detail = traceback.format_exc()
            log_to_file("核算未预期异常：\n" + detail)
            log("发生未预期异常：")
            log(detail)
            ok, msg = False, "程序内部错误，请把本窗口内容发给管理员"
        self.queue.put({"job": "scan", "ok": ok, "msg": msg, "run": run, "table": table})

    def _worker_recheck(self, dialog, run, tax_mode, rate):
        def log(text):
            self.queue.put(str(text))

        new_run = table = None
        try:
            ok, msg, new_run, table = recheck_once(run, tax_mode, rate, log=log)
        except Exception as exc:
            detail = traceback.format_exc()
            log_to_file("重新检查异常：\n" + detail)
            log(f"重新检查失败：{exc}")
            ok, msg = False, str(exc)
        self.queue.put({"job": "recheck", "ok": ok, "msg": msg,
                        "run": new_run, "table": table, "dialog": dialog})

    def _worker_recheck_snapshot(self, tax_mode, rate):
        def log(text):
            self.queue.put(str(text))

        run = table = None
        try:
            ok, msg, run, table = recheck_from_snapshot(tax_mode, rate, log=log)
        except Exception as exc:
            detail = traceback.format_exc()
            log_to_file("重算异常：\n" + detail)
            log(f"重算失败：{exc}")
            ok, msg = False, str(exc)
        self.queue.put({"job": "scan", "ok": ok, "msg": msg, "run": run, "table": table})

    def _worker_export(self, run, out_path, dialog):
        def log(text):
            self.queue.put(str(text))

        try:
            ok, msg, path = export_run_once(run, out_path, log=log)
        except Exception as exc:
            detail = traceback.format_exc()
            log_to_file("导出异常：\n" + detail)
            log(f"导出失败：{exc}")
            ok, msg, path = False, str(exc), ""
        self.queue.put({"job": "export", "ok": ok, "msg": msg, "path": path, "dialog": dialog})

    # ---------------- 供对话框调用 ----------------

    def recheck_job(self, dialog):
        if self.running:
            return
        run = self.current_run
        if run is None:
            messagebox.showwarning("提示", "没有可重算的结果，请先点「开始核算」。", parent=dialog)
            return
        dialog.set_busy(True)
        self._start_job(
            self._worker_recheck,
            (dialog, run, str(run.meta.get("计价方式") or TAX_EXCLUDED),
             override_from_meta(run.meta)),
            "正在读取维护表并重新计算……", "重新检查（套用维护表）", clear_log=False,
        )

    def export_job(self, run, forced=False, dialog=None):
        if self.running:
            return
        if not forced and not run.complete:
            messagebox.showwarning("提示", "还有子件缺采购价，请先补价。", parent=dialog)
            return
        # 自动导出时保留前面的扫描日志，方便财务对照
        self._start_job(self._worker_export, (run, None, dialog),
                        "正在导出 Excel……", "导出最终表格", clear_log=False)

    # ---------------- 主线程消费消息 ----------------

    def _poll_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                if isinstance(item, dict):
                    self._handle_done(item)
                else:
                    self._log(item)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _handle_done(self, msg):
        job = msg.get("job")
        ok = bool(msg.get("ok"))
        self._finish_job()

        if job == "selfcheck":
            self._log("=== 自检完成 ===" if ok else "=== 自检未通过 ===")
            self.var_status.set("自检通过 ✅" if ok else "自检未通过 ❌")
            if ok:
                messagebox.showinfo("自检通过", "账号可以正常读取销售订单、采购订单、物料清单。")
            else:
                messagebox.showwarning("自检未通过",
                                       "部分表单未能取数，请把「运行结果」里的内容截图或复制发给管理员。")
            log_to_file("自检结果：" + ("成功" if ok else "失败"))
            return

        if job == "scan":
            if not ok:
                self._log("=== 核算未完成 ===")
                self.var_status.set("核算未完成 ❌")
                messagebox.showwarning("核算未完成", msg.get("msg") or "请把运行结果发给管理员。")
                return
            self.current_run = msg.get("run")
            self.table = msg.get("table") or self.table
            if self.table is not None:
                self.var_table.set(self.table.path)
            self._log("=== 扫描完成 ===")
            run = self.current_run
            if run.complete:
                self.var_status.set("已取数，缺价已全部补齐，正在导出……")
                self.export_job(run)
            else:
                self.var_status.set(f"发现 {len(run.missing)} 个缺价子件，等待补价 ❌")
                self._log(f"发现 {len(run.missing)} 个子件缺采购价，"
                          f"料号已预填进维护表，补齐前不导出最终表格。")
                self._open_dialog(run)
            return

        if job == "recheck":
            dialog = msg.get("dialog")
            if not ok:
                if dialog is not None and dialog.winfo_exists():
                    dialog.set_busy(False)
                messagebox.showwarning("重新检查失败", msg.get("msg") or "请把运行结果发给管理员。")
                return
            self.current_run = msg.get("run")
            self.table = msg.get("table") or self.table
            run = self.current_run
            if run.complete:
                if dialog is not None and dialog.winfo_exists():
                    dialog.set_busy(False)
                self.var_status.set("缺价已补齐 ✅")
                if messagebox.askyesno("缺价已补齐",
                                       f"所有子件都有价了。现在导出最终表格吗？\n"
                                       f"（手工维护料本 "
                                       f"{run.totals()['手工维护料本']:,.2f} 元）",
                                       parent=dialog):
                    if dialog is not None and dialog.winfo_exists():
                        dialog.on_close()
                    self.export_job(run)
                elif dialog is not None and dialog.winfo_exists():
                    dialog.set_busy(False)
            else:
                self.var_status.set(f"仍缺 {len(run.missing)} 个，继续补价")
                if dialog is not None and dialog.winfo_exists():
                    dialog.refresh(run)
                    dialog.set_busy(False)
                messagebox.showwarning(
                    "还没补齐",
                    f"仍有 {len(run.missing)} 个子件没填价，请在维护表里继续填写后重新检查。",
                    parent=dialog)
            return

        if job == "export":
            dialog = msg.get("dialog")
            if dialog is not None and dialog.winfo_exists():
                dialog.on_close()
            if ok:
                self.var_status.set("导出完成 ✅")
                self._log("=== 导出完成 ===")
                messagebox.showinfo("导出完成", msg.get("msg") or "已导出。")
            else:
                self.var_status.set("导出失败 ❌")
                messagebox.showwarning("导出失败", msg.get("msg") or "请把运行结果发给管理员。")
            return

    def _open_dialog(self, run):
        if self.dialog is not None and self.dialog.winfo_exists():
            self.dialog.refresh(run)
            self.dialog.deiconify()
            self.dialog.lift()
            return
        try:
            self.dialog = MissingPriceDialog(self.root, self, run, self.table)
        except Exception as exc:
            log_to_file(f"缺价对话框创建失败：{exc}")
            messagebox.showwarning(
                "有子件缺采购价",
                f"有 {len(run.missing)} 个子件缺采购价，料号已预填进维护表：\n{self.table.path}\n\n"
                f"请在维护表里填好单价后，点「套用维护表重新导出」。",
            )

    def _log(self, text):
        self.txt.config(state="normal")
        self.txt.insert("end", str(text) + "\n")
        self.txt.see("end")
        self.txt.config(state="disabled")


# ==================== 命令行 ====================

def main(argv=None):
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--check", action="store_true", help="无界面自检")
    parser.add_argument("--costing", action="store_true", help="无界面核算")
    parser.add_argument("--month", default="", help="整月，如 2026-09（--costing 用）")
    parser.add_argument("--from", dest="date_from", default="", help="起始日期（--costing 用）")
    parser.add_argument("--to", dest="date_to", default="", help="结束日期（--costing 用）")
    parser.add_argument("--tax", default=TAX_EXCLUDED, choices=[TAX_EXCLUDED, TAX_INCLUDED],
                        help="计价方式（--costing 用，默认未税）")
    parser.add_argument("--rate", type=float, default=None, help="覆盖汇率（--costing 用）")
    parser.add_argument("--out", default="", help="导出 xlsx 路径（--costing 用）")
    parser.add_argument("--limit", type=int, default=5000, help="最多核算多少条销售记录")
    parser.add_argument("--manual-table", default="", help="采购价维护表 CSV 路径")
    parser.add_argument("--allow-missing", action="store_true",
                        help="仍有缺价子件时也导出（按 0 计并标注）")
    parser.add_argument("--recheck", action="store_true",
                        help="不登录金蝶，用上次快照 + 最新维护表重算并导出")
    parser.add_argument("--smoke-gui", action="store_true", help="只构建窗口后退出（验证界面）")
    parser.add_argument("--smoke-dialog", action="store_true",
                        help="用假数据构建一次缺价补全对话框后退出（验证界面）")
    parser.add_argument("-u", "--user", default="", help="金蝶账号（建议用环境变量）")
    parser.add_argument("-p", "--password", default="", help="密码（建议用环境变量）")
    args = parser.parse_args(argv)

    if args.check:
        if args.user and args.password:
            ok, _msg = run_selfcheck(args.user, args.password)
            return 0 if ok else 1
        import selfcheck
        return selfcheck.cli_main([])

    if args.costing:
        user = args.user or os.getenv("KINGDEE_USERNAME", "")
        password = args.password or os.getenv("KINGDEE_PASSWORD", "")
        manual = args.manual_table or None

        if args.recheck:
            ok, msg, run, table = recheck_from_snapshot(args.tax, args.rate, manual, log=print)
            if not ok:
                print(msg)
                return 1
        else:
            if not user or not password:
                print("需要账号与口令：--user/--password 或环境变量 "
                      "KINGDEE_USERNAME / KINGDEE_PASSWORD")
                return 2
            try:
                if args.month:
                    date_from, date_to = month_range(args.month)
                elif args.date_from and args.date_to:
                    date_from, date_to = normalize_range(args.date_from, args.date_to)
                else:
                    print("请用 --month 2026-09 或 --from/--to 指定统计区间")
                    return 2
            except CostingError as exc:
                print(f"[参数错误] {exc}")
                return 2
            ok, msg, run, table = scan_once(user, password, date_from, date_to, args.tax,
                                           args.rate, limit=args.limit, manual_path=manual,
                                           log=print)
            if not ok:
                print(msg)
                return 1

        if run is not None and not run.complete:
            print(f"\n⚠ 还有 {len(run.missing)} 个子件缺采购价，料号已预填进维护表：")
            print(f"   {table.path if table else ''}")
            for m in run.missing[:20]:
                print(f"   {m['子件编码']:<22}{str(m['子件名称'])[:16]:<18}{m['说明']}")
            if not args.allow_missing:
                print("\n请在维护表里填好单价后重跑（或加 --recheck 用上次快照重算）。")
                return 2
            print("\n[--allow-missing] 按 0 计并标注后继续导出。")

        ok, msg, _path = export_run_once(run, args.out or None, log=print)
        print(msg)
        return 0 if ok else 1

    if args.smoke_dialog:
        if _TK_ERROR is not None:
            print(f"界面库 tkinter 不可用：{_TK_ERROR}")
            return 2
        return _smoke_dialog()

    if _TK_ERROR is not None:
        print(f"界面库 tkinter 不可用：{_TK_ERROR}")
        print("可改用命令行：程序.exe --check 或 程序.exe --costing --month 2026-09")
        return 2

    root = tk.Tk()
    ToolApp(root)
    if args.smoke_gui:
        root.update_idletasks()
        root.update()
        root.destroy()
        print("GUI 构建成功（--smoke-gui）")
        return 0
    root.mainloop()
    return 0


def _smoke_dialog():
    """用假数据构建一次「缺价补全」对话框（打包前验证界面能否正常创建）"""
    import tempfile
    from kingdee_sdk.manual_prices import ManualPriceTable as Table

    fake = type("FakeRun", (), {})()
    fake.missing = [
        {"子件编码": "TEST.CHILD.0001", "子件名称": "示例子件（缺价）", "单位": "Pcs",
         "出现次数": 3, "涉及产品数": 2,
         "说明": "金蝶没有该子件的已审核采购价，请在维护表里填单价"},
        {"子件编码": "TEST.CHILD.0002", "子件名称": "示例子件（维护表有行但没填价）", "单位": "Pcs",
         "出现次数": 1, "涉及产品数": 1, "说明": "维护表有该行，但「未税单价」还没填"},
    ]
    fake.children = [
        {"子件编码": "TEST.CHILD.0001", "子件名称": "示例子件（缺价）", "单位": "Pcs",
         "价格来源": "缺价", "采购价-未税(原币)": 0.0, "单价(人民币)": 0.0,
         "出现次数": 3, "涉及产品数": 2},
        {"子件编码": "TEST.CHILD.0003", "子件名称": "示例子件（金蝶已有价）", "单位": "Pcs",
         "价格来源": "金蝶", "采购价-未税(原币)": 12.5, "单价(人民币)": 12.5,
         "出现次数": 8, "涉及产品数": 4},
        {"子件编码": "TEST.CHILD.0002", "子件名称": "示例子件（维护表有行但没填价）", "单位": "Pcs",
         "价格来源": "缺价", "采购价-未税(原币)": 0.0, "单价(人民币)": 0.0,
         "出现次数": 1, "涉及产品数": 1},
    ]
    fake.meta = {"计价方式": "未税"}

    class FakeApp:
        current_run = fake

        def recheck_job(self, _dialog):
            print("      （假数据不真的重算）")

        def export_job(self, _run, forced=False, dialog=None):
            print(f"      （假数据不真的导出，forced={forced}）")

    path = os.path.join(tempfile.mkdtemp(prefix="smoke_dialog_"), "采购价维护表.csv")
    table = Table(path).load()
    table.add_missing(fake.missing)
    table.save()

    root = tk.Tk()
    root.withdraw()
    dlg = MissingPriceDialog(root, FakeApp(), fake, table)
    root.update_idletasks()
    root.update()
    rows = len(dlg.tree.get_children())
    # 勾上「显示全部子件」应能切换成总览
    dlg.var_all.set(True)
    dlg.refresh(fake)
    root.update_idletasks()
    rows_all = len(dlg.tree.get_children())
    heading = dlg.tree.heading("说明")["text"]
    dlg.destroy()
    root.destroy()
    print(f"缺价补全对话框构建成功（--smoke-dialog）：缺价 {rows} 行，"
          f"全部子件 {rows_all} 行，说明列标题「{heading}」")
    return 0 if (rows == 2 and rows_all == 3 and heading == "价格来源") else 1


if __name__ == "__main__":
    sys.exit(main())
