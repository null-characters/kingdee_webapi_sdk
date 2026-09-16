# -*- coding: utf-8 -*-
"""
金蝶成本核算工具（内部小工具）—— 图形界面

给财务同事用：双击 exe → 输入自己的金蝶账号和密码 → 点「登录并自检」确认能取数，
再填月份后点「开始核算并导出 Excel」，就能得到「每条销售记录的售价 / 料本 / 毛利」。

说明：
    - 服务器地址、账套 ID 已固定写在 selfcheck.py 的 FIXED_CONFIG 里，界面上不可修改
    - 密码只保存在内存，不落盘、不写入日志
    - 所有对金蝶的操作都是只读查询（不新增、不修改、不删除任何单据）

核算口径（与财务确认）：
    - 按月结算，每月内每条销售记录单独计算
    - 采购价取该物料「最近一次成交价」（最新一条已审核采购行，不限时点）
    - 外币按汇率折人民币（默认用单据自带汇率，可手工指定覆盖）
    - 含税 / 未税 可切换（默认未税）

附属命令行参数（排查问题用）：
    --check        无界面自检（等价于 selfcheck.py --check）
    --costing      无界面核算：--costing --month 2026-09 [--tax 未税|含税] [--rate 6.7809] [--limit 50]
    --smoke-gui    只构建一次窗口后退出（验证界面能否启动）
"""

import argparse
import datetime
import os
import queue
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
    from kingdee_sdk.costing import (
        TAX_EXCLUDED,
        TAX_INCLUDED,
        CostingCalculator,
        CostingError,
        export_xlsx,
        month_range,
    )
    _COSTING_ERROR = None
except Exception as _exc:  # pragma: no cover
    CostingCalculator = export_xlsx = month_range = None
    TAX_EXCLUDED, TAX_INCLUDED = "未税", "含税"
    CostingError = RuntimeError
    _COSTING_ERROR = _exc

LOG_PATH = os.path.join(tempfile.gettempdir(), "kingdee_tool.log")


def desktop_dir() -> str:
    """Excel 默认导出到桌面（找不到桌面就用用户主目录）"""
    home = os.path.expanduser("~")
    for name in ("Desktop", "桌面"):
        path = os.path.join(home, name)
        if os.path.isdir(path):
            return path
    return home


def log_to_file(text):
    """把关键信息追加到临时目录日志（不含密码）"""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
    except Exception:
        pass


def run_costing_once(username, password, month, tax_mode, override_rate, limit=5000,
                     out_path=None, log=None):
    """登录 → 按核算口径算出结果 → 导出 Excel（供界面与命令行共用）

    Returns: (ok, 消息, 导出路径 或 "", 汇总行)
    """
    log = log or print
    if month_range is None:
        return False, f"核算模块加载失败：{_COSTING_ERROR}", "", []

    date_from, date_to = month_range(month)
    client = build_client(username, password)
    try:
        log(f"正在登录（{username}）……")
        client.login()
        log(f"登录成功，开始核算 {month}（{date_from} ~ {date_to}，计价：{tax_mode}"
            f"{'，覆盖汇率 ' + str(override_rate) if override_rate else ''}）")

        calc = CostingCalculator(
            client, tax_mode=tax_mode, override_rate=override_rate, log=log
        )
        summary, details = calc.run(date_from, date_to, limit=limit)
        log(f"核算完成：{len(summary)} 条销售记录，{len(details)} 行子件明细")
    finally:
        try:
            client.logout()
        except Exception:
            pass

    if not summary:
        return False, f"{month} 没有已审核的销售记录（或该账号查不到数据）", "", []

    if out_path is None:
        stamp = f"成本核算_{month}_{tax_mode}"
        out_path = os.path.join(desktop_dir(), stamp + ".xlsx")
    export_xlsx(out_path, summary, details, meta={
        "结算月份": month,
        "期间": f"{date_from} ~ {date_to}",
        "计价方式": tax_mode,
        "汇率处理": "单据自带汇率" if not override_rate else f"整批按 {override_rate} 折算",
        "采购取价": "该物料最近一次已审核采购行的单价（不限时点）",
        "成本口径": "BOM 展开到无 BOM 的叶子件，按最近采购价 × 累计用量汇总",
        "说明": "「备注」列有内容的记录建议人工核对（缺采购价 / 未取到子件）",
        "数据来源": "金蝶云星空 WebAPI（只读查询）",
        "生成时间": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    log(f"已导出 Excel：{out_path}")
    return True, f"已导出 {len(summary)} 条记录到 {out_path}", out_path, summary


class ToolApp:
    """主窗口"""

    def __init__(self, root):
        self.root = root
        self.queue = queue.Queue()
        self.running = False

        root.title(f"{APP_TITLE} v{APP_VERSION}")
        root.geometry("880x680")
        root.minsize(760, 560)

        self._build_fixed_info()
        self._build_login_area()
        self._build_costing_area()
        self._build_log_area()
        self._build_status_bar()

        self.root.after(100, self._poll_queue)
        self._log(f"{APP_TITLE} v{APP_VERSION}")
        self._log("第 1 步：填账号密码 → 点「登录并自检」，确认账号能取数。")
        self._log("第 2 步：填结算月份 → 点「开始核算并导出 Excel」，结果会存到桌面。")
        self._log("说明：本工具只做只读查询（不新增、不修改、不删除任何单据）。")

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
        self.entry_user = ttk.Entry(frame, width=26)
        self.entry_user.grid(row=0, column=1, sticky="w", pady=6)

        ttk.Label(frame, text="密码：").grid(row=0, column=2, sticky="e", padx=(16, 4), pady=6)
        self.entry_pwd = ttk.Entry(frame, width=26, show="*")
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

        ttk.Label(frame, text="结算月份：").grid(row=0, column=0, sticky="e", padx=(10, 4), pady=6)
        self.entry_month = ttk.Entry(frame, width=12)
        self.entry_month.insert(0, datetime.date.today().strftime("%Y-%m"))
        self.entry_month.grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(frame, text="格式 2026-09", foreground="#888").grid(
            row=0, column=2, sticky="w", padx=(6, 20)
        )

        ttk.Label(frame, text="计价方式：").grid(row=0, column=3, sticky="e", padx=(10, 4), pady=6)
        self.var_tax = tk.StringVar(value=TAX_EXCLUDED)
        ttk.Radiobutton(frame, text="未税", value=TAX_EXCLUDED, variable=self.var_tax).grid(
            row=0, column=4, sticky="w"
        )
        ttk.Radiobutton(frame, text="含税", value=TAX_INCLUDED, variable=self.var_tax).grid(
            row=0, column=5, sticky="w", padx=(4, 10)
        )

        ttk.Label(frame, text="覆盖汇率：").grid(row=1, column=0, sticky="e", padx=(10, 4), pady=6)
        self.entry_rate = ttk.Entry(frame, width=12)
        self.entry_rate.grid(row=1, column=1, sticky="w", pady=6)
        ttk.Label(
            frame, text="留空 = 用单据自带汇率（外币整批折算时才需要填）", foreground="#888"
        ).grid(row=1, column=2, columnspan=4, sticky="w", padx=(6, 10), pady=6)

        self.btn_costing = ttk.Button(
            frame, text="开始核算并导出 Excel", command=self.on_run_costing
        )
        self.btn_costing.grid(row=2, column=1, sticky="w", pady=(2, 10))
        ttk.Label(
            frame, text="结果会导出到桌面（Excel：逐条核算 + 子件明细 + 说明）", foreground="#888"
        ).grid(row=2, column=2, columnspan=4, sticky="w", pady=(2, 10))
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

    # ---------------- 交互 ----------------

    def _toggle_pwd(self):
        self.entry_pwd.config(show="" if self.var_show_pwd.get() else "*")

    def on_clear(self):
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.config(state="disabled")

    def on_open_log_dir(self):
        folder = os.path.dirname(LOG_PATH)
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # noqa: S606 - Windows
            elif sys.platform == "darwin":
                os.system(f'open "{folder}"')
            else:
                os.system(f'xdg-open "{folder}"')
        except Exception as exc:
            self._log(f"打开日志文件夹失败：{exc}")

    def _read_credentials(self):
        user = self.entry_user.get().strip()
        pwd = self.entry_pwd.get()
        if not user or not pwd:
            messagebox.showwarning("提示", "请先填写金蝶账号和密码。")
            return None, None
        return user, pwd

    def _start_job(self, target, args, status_text, file_log):
        if self.running:
            return
        self.running = True
        self.btn_run.config(state="disabled")
        self.btn_costing.config(state="disabled")
        self.var_status.set(status_text)
        self.on_clear()
        log_to_file(file_log)
        threading.Thread(target=target, args=args, daemon=True).start()

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

        month = self.entry_month.get().strip()
        try:
            datetime.datetime.strptime(month, "%Y-%m")
        except ValueError:
            messagebox.showwarning("提示", "结算月份格式不对，请填成 2026-09 这样。")
            return

        rate_text = self.entry_rate.get().strip()
        rate = None
        if rate_text:
            try:
                rate = float(rate_text)
                if rate <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("提示", "覆盖汇率要填正数，比如 6.7809；留空表示用单据自带汇率。")
                return

        tax_mode = self.var_tax.get()
        self._start_job(
            self._worker_costing, (user, pwd, month, tax_mode, rate),
            f"正在核算 {month}（{tax_mode}）……", f"开始核算 {month} {tax_mode}，账号={user}",
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
        self.queue.put(("__done__", "selfcheck", ok, msg))

    def _worker_costing(self, user, pwd, month, tax_mode, rate):
        def log(text):
            self.queue.put(str(text))

        try:
            ok, msg, _path, _rows = run_costing_once(
                user, pwd, month, tax_mode, rate, log=log
            )
        except CostingError as exc:
            log(f"核算失败：{exc}")
            ok, msg = False, str(exc)
        except Exception:
            detail = traceback.format_exc()
            log_to_file("核算未预期异常：\n" + detail)
            log("发生未预期异常：")
            log(detail)
            ok, msg = False, "程序内部错误，请把本窗口内容发给管理员"
        self.queue.put(("__done__", "costing", ok, msg))

    def _poll_queue(self):
        """主线程消费后台消息，更新界面"""
        try:
            while True:
                item = self.queue.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "__done__":
                    _, kind, ok, msg = item
                    self._log("")
                    if kind == "costing":
                        self._log("=== 核算完成 ===" if ok else "=== 核算未完成 ===")
                        self.var_status.set("核算完成 ✅" if ok else "核算未完成 ❌")
                        title = "核算完成" if ok else "核算未完成"
                        body = msg
                    else:
                        self._log("=== 自检完成 ===" if ok else "=== 自检未通过 ===")
                        self.var_status.set("自检通过 ✅" if ok else "自检未通过 ❌")
                        title = "自检通过" if ok else "自检未通过"
                        body = (
                            "账号可以正常读取销售订单、采购订单、物料清单。"
                            if ok else
                            "部分表单未能取数，请把「运行结果」里的内容截图或复制发给管理员。"
                        )
                    self.running = False
                    self.btn_run.config(state="normal")
                    self.btn_costing.config(state="normal")
                    log_to_file(f"{kind} 结果：" + ("成功" if ok else "失败"))
                    if ok:
                        messagebox.showinfo(title, body)
                    else:
                        messagebox.showwarning(title, body or "请把运行结果发给管理员。")
                else:
                    self._log(item)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _log(self, text):
        self.txt.config(state="normal")
        self.txt.insert("end", str(text) + "\n")
        self.txt.see("end")
        self.txt.config(state="disabled")


def main(argv=None):
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--check", action="store_true", help="无界面自检")
    parser.add_argument("--costing", action="store_true", help="无界面核算（配合 --month 使用）")
    parser.add_argument("--month", default="", help="结算月份，如 2026-09（--costing 用）")
    parser.add_argument("--tax", default=TAX_EXCLUDED, choices=[TAX_EXCLUDED, TAX_INCLUDED],
                        help="计价方式（--costing 用，默认未税）")
    parser.add_argument("--rate", type=float, default=None, help="覆盖汇率（--costing 用）")
    parser.add_argument("--out", default="", help="导出 xlsx 路径（--costing 用）")
    parser.add_argument("--limit", type=int, default=5000,
                        help="最多核算多少条销售记录（--costing 用，默认 5000）")
    parser.add_argument("--smoke-gui", action="store_true", help="只构建窗口后退出（验证界面）")
    parser.add_argument("-u", "--user", default="", help="金蝶账号（命令行用，建议用环境变量）")
    parser.add_argument("-p", "--password", default="", help="密码（命令行用，建议用环境变量）")
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
        if not user or not password:
            print("需要账号与口令：--user/--password 或环境变量 KINGDEE_USERNAME / KINGDEE_PASSWORD")
            return 2
        if not args.month:
            print("请用 --month 指定结算月份，例如 --month 2026-09")
            return 2
        ok, msg, _path, _rows = run_costing_once(
            user, password, args.month, args.tax, args.rate,
            limit=args.limit, out_path=args.out or None, log=print,
        )
        print(msg)
        return 0 if ok else 1

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


if __name__ == "__main__":
    sys.exit(main())
