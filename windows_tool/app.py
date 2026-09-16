# -*- coding: utf-8 -*-
"""
金蝶成本核算工具（内部小工具）—— 图形界面

给财务同事用：双击 exe → 输入自己的金蝶账号和密码 → 点「登录并自检」，
就能确认账号能否正常读取销售订单、采购订单、物料清单，为后续成本核算取数做准备。

说明：
    - 服务器地址、账套 ID 已固定写在 selfcheck.py 的 FIXED_CONFIG 里，界面上不可修改
    - 密码只保存在内存，不落盘、不写入日志
    - 所有对金蝶的操作都是只读查询

附属命令行参数（排查问题用）：
    --check        无界面自检（等价于 selfcheck.py --check）
    --smoke-gui    只构建一次窗口后退出（验证界面能否启动）
"""

import argparse
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

# GUI 依赖延迟判断：万一环境缺 tkinter，--check 仍然可用
try:
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk
    _TK_ERROR = None
except Exception as _exc:  # pragma: no cover
    tk = ttk = scrolledtext = messagebox = None
    _TK_ERROR = _exc

from selfcheck import APP_TITLE, APP_VERSION, FIXED_CONFIG, run_selfcheck  # noqa: E402

LOG_PATH = os.path.join(tempfile.gettempdir(), "kingdee_tool.log")


def log_to_file(text):
    """把关键信息追加到临时目录日志（不含密码）"""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
    except Exception:
        pass


class ToolApp:
    """主窗口"""

    def __init__(self, root):
        self.root = root
        self.queue = queue.Queue()
        self.running = False

        root.title(f"{APP_TITLE} v{APP_VERSION}")
        root.geometry("820x580")
        root.minsize(720, 480)

        self._build_fixed_info()
        self._build_login_area()
        self._build_log_area()
        self._build_status_bar()

        self.root.after(100, self._poll_queue)
        self._log(f"{APP_TITLE} v{APP_VERSION}")
        self._log("请填写自己的金蝶账号和密码，然后点「登录并自检」。")
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
        frame = ttk.LabelFrame(self.root, text="登录")
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

        # 回车即开始
        for w in (self.entry_user, self.entry_pwd):
            w.bind("<Return>", lambda _e: self.on_run())
        self.entry_user.focus_set()
        return frame

    def _build_log_area(self):
        frame = ttk.LabelFrame(self.root, text="运行结果")
        frame.pack(fill="both", expand=True, padx=12, pady=6)
        self.txt = scrolledtext.ScrolledText(frame, height=18, wrap="word", state="disabled")
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

    def on_run(self):
        if self.running:
            return
        user = self.entry_user.get().strip()
        pwd = self.entry_pwd.get()
        if not user or not pwd:
            messagebox.showwarning("提示", "请先填写金蝶账号和密码。")
            return

        self.running = True
        self.btn_run.config(state="disabled")
        self.var_status.set("正在登录并自检……")
        self.on_clear()
        log_to_file(f"开始自检，账号={user}")

        threading.Thread(target=self._worker, args=(user, pwd), daemon=True).start()

    def _worker(self, user, pwd):
        """后台线程执行：界面不会卡死"""
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
        self.queue.put(("__done__", ok, msg))

    def _poll_queue(self):
        """主线程消费后台消息，更新界面"""
        try:
            while True:
                item = self.queue.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "__done__":
                    ok = item[1]
                    self._log("")
                    self._log("=== 自检完成 ===" if ok else "=== 自检未通过 ===")
                    self.var_status.set("自检通过 ✅" if ok else "自检未通过 ❌")
                    self.running = False
                    self.btn_run.config(state="normal")
                    log_to_file("自检结果：" + ("通过" if ok else "未通过"))
                    if not ok:
                        messagebox.showwarning(
                            "自检未通过",
                            "部分表单未能取数，请把「运行结果」里的内容截图或复制发给管理员。",
                        )
                    else:
                        messagebox.showinfo("自检通过", "账号可以正常读取销售订单、采购订单、物料清单。")
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
    parser.add_argument("--smoke-gui", action="store_true", help="只构建窗口后退出（验证界面）")
    parser.add_argument("-u", "--user", default="", help="金蝶账号（仅 --check 用）")
    parser.add_argument("-p", "--password", default="", help="密码（仅 --check 用，建议用环境变量）")
    args = parser.parse_args(argv)

    if args.check:
        if args.user and args.password:
            ok, _msg = run_selfcheck(args.user, args.password)
            return 0 if ok else 1
        import selfcheck
        return selfcheck.cli_main([])

    if _TK_ERROR is not None:
        print(f"界面库 tkinter 不可用：{_TK_ERROR}")
        print("可改用命令行自检：程序.exe --check")
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
