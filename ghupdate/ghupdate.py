# -*- coding: utf-8 -*-
"""
ghupdate 入口：中文菜单 + 分发。

.bat 保持纯 ASCII 只负责「切到 UTF-8 代码页 + 找到 Python + 调用本脚本」，
所有中文（含菜单）都由 Python 打印，从根上避免 cmd 代码页错位导致的乱码。
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

TARGETS = {
    "maa": ("update_maa.py", "MAA"),
    "maaend": ("update_maaend.py", "MaaEnd"),
}

MENU = """
============================================================
   MAA / MaaEnd 本体更新器          镜像：ghfast.top
   零系统改动：不装证书 · 不改 hosts · 不写程序配置
============================================================

   1. 仅检查更新（干跑，不下载任何文件）
   2. 更新 MAA          （当前有 19.6 MB 增量包可用）
   3. 更新 MaaEnd
   4. 更新全部（MAA + MaaEnd）
   5. 查看用法 / 高级选项
   0. 退出
"""

USAGE = """
------------------------------------------------------------
 命令行用法（也可直接在 cmd 里执行）

   update-all.bat                        打开本菜单
   update-all.bat maa      [选项]        更新 MAA
   update-all.bat maaend   [选项]        更新 MaaEnd
   update-all.bat all      [选项]        先 MAA 再 MaaEnd
   update-all.bat check                  两个都干跑

 常用选项：
   --check        只检查不下载（干跑）
   --prune        （仅 MAA）按新 filelist 清理废弃程序文件
   --restart      更新完成后启动程序
   -y             不再交互确认
   --no-backup    跳过备份（不建议）
   --proxy URL    显式使用代理，如 http://127.0.0.1:7890

 回滚：每次更新前的备份在 _backup\\<程序>-<时间戳>\\ ，
       整个目录内容复制回安装目录即可。
------------------------------------------------------------
"""


def run_script(script, extra):
    path = os.path.join(HERE, script)
    if not os.path.isfile(path):
        C.die("找不到 %s" % path)
    cmd = [sys.executable, path] + list(extra)
    return subprocess.call(cmd)


def run_targets(keys, extra):
    rc = 0
    for i, k in enumerate(keys):
        script, label = TARGETS[k]
        if i:
            C.log("\n" + "-" * 60 + "\n")
        r = run_script(script, extra)
        if r != 0:
            rc = r
    return rc


def menu():
    while True:
        C.log(MENU)
        try:
            ch = input("请选择 [0-5]: ").strip()
        except (EOFError, KeyboardInterrupt):
            C.log("")
            return 0
        if ch == "0":
            return 0
        elif ch == "5":
            C.log(USAGE)
            input("按回车返回菜单…")
        elif ch == "1":
            run_script("update_maa.py", ["--check"])
            C.log("")
            run_script("update_maaend.py", ["--check"])
            C.log("")
            input("按回车返回菜单…")
        elif ch == "2":
            run_targets(["maa"], [])
            C.log("")
            input("按回车返回菜单…")
        elif ch == "3":
            run_targets(["maaend"], [])
            C.log("")
            input("按回车返回菜单…")
        elif ch == "4":
            run_targets(["maa", "maaend"], [])
            C.log("")
            input("按回车返回菜单…")
        else:
            C.log("  无效输入，请重新选择。")


def main():
    args = sys.argv[1:]
    if not args:
        return menu()
    rc = dispatch(args)
    # 双击运行时让窗口留到最后（管道/重定向下 input() 会立即 EOF，不影响脚本调用）
    try:
        if sys.stdin.isatty():
            input("\n按回车关闭窗口…")
    except Exception:
        pass
    return rc


def dispatch(args):
    t = args[0].lower()
    rest = args[1:]
    if t in TARGETS:
        return run_targets([t], rest)
    if t == "all":
        return run_targets(["maa", "maaend"], rest)
    if t == "check":
        rc = run_script("update_maa.py", ["--check"])
        C.log("\n" + "-" * 60 + "\n")
        rc2 = run_script("update_maaend.py", ["--check"])
        return rc or rc2
    if t in ("help", "-h", "--help", "/?"):
        C.log(USAGE)
        return 0
    C.log("[x] 未知参数：%s" % t)
    C.log(USAGE)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        C.log("\n已中断。")
        sys.exit(130)
