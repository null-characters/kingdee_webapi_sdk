# -*- coding: utf-8 -*-
"""打包前冒烟验证（开发者自查用，正式打包时可以不带上这个文件）

依次做三件事：
    1. 语法编译检查 app.py / selfcheck.py
    2. 构建一次界面后立刻销毁（等价于 --smoke-gui）
    3. 若提供了口令，顺带跑一次真实登录 + 三表单自检（只读查询）

用法：
    PYTHONDONTWRITEBYTECODE=1 KINGDEE_PASSWORD=xxx python3 _smoke_check.py
"""

import os
import py_compile
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def check_compile():
    for name in ("app.py", "selfcheck.py"):
        py_compile.compile(os.path.join(HERE, name), doraise=True)
    print("[1/3] 语法检查通过：app.py, selfcheck.py")


def check_gui():
    import app
    rc = app.main(["--smoke-gui"])
    print(f"[2/3] 界面构建返回码：{rc}")
    return rc


def check_login():
    pwd = os.getenv("KINGDEE_PASSWORD", "")
    if not pwd:
        print("[3/3] 跳过登录自检（未提供 KINGDEE_PASSWORD）")
        return 0
    import selfcheck
    ok, msg = selfcheck.run_selfcheck(os.getenv("KINGDEE_USERNAME", ""), pwd)
    print(f"[3/3] 登录自检：{'通过' if ok else '未通过'} {msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    check_compile()
    rc_gui = check_gui()
    rc_login = check_login()
    sys.exit(0 if rc_gui == 0 and rc_login == 0 else 1)
