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
from core import config as cfgmod  # noqa: E402
from core import locate  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

TARGETS = {
    "maa": ("update_maa.py", "MAA"),
    "maaend": ("update_maaend.py", "MaaEnd"),
}

KINDS = (("maa", "MAA"), ("maaend", "MaaEnd"))

USAGE = """
------------------------------------------------------------
 命令行用法（也可直接在 cmd 里执行）

   update-all.bat                          打开本菜单
   update-all.bat maa      [选项]          更新 MAA
   update-all.bat maaend   [选项]          更新 MaaEnd
   update-all.bat all      [选项]          先 MAA 再 MaaEnd
   update-all.bat check                    两个都干跑

 安装目录（手动指定，不做自动探测）：
   --install DIR      指定安装目录（含 MAA.exe / MaaEnd.exe 的文件夹）。
                      校验通过后会写进 config.json，下次免输。
   --no-save          配合 --install：只本次生效，不写配置
   --inspect [DIR]    检查目录是不是安装目录，并列出子目录候选
   --forget-install [maa|maaend|all]
                      清除已保存的安装路径

 镜像与配置：
   --mirror URL       覆盖镜像前缀，可重复传多次形成候选列表
   --no-mirror        本次禁用镜像，改走 GitHub 直连
   --config PATH      指定配置文件（默认 ghupdate\\config.json）
   --show-config      打印当前生效配置（含每项来源）后退出

 其他常用选项：
   --check            只检查不下载（干跑）
   --prune            （仅 MAA）按新 filelist 清理废弃程序文件
   --restart          更新完成后启动程序
   -y                 不再交互确认
   --no-backup        跳过备份（不建议）
   --proxy URL        显式使用代理，如 http://127.0.0.1:7890

 回滚：每次更新前的备份在 _backup\\<程序>-<时间戳>\\ ，
       整个目录内容复制回安装目录即可。
------------------------------------------------------------
"""


# ---------------------------------------------------------------------------
# 菜单
# ---------------------------------------------------------------------------

def short_dir(path):
    path = (path or "").rstrip("\\/")
    return os.path.basename(path) if path else "(未指定)"


def mirror_text(cfg):
    if not cfg.mirror_enabled:
        return "已禁用（直连 GitHub）"
    items = cfg.mirror_prefixes
    if not items:
        return "(未配置，等同直连)"
    text = items[0] + (" 等 %d 个" % len(items) if len(items) > 1 else "")
    return text if len(text) <= 32 else text[:29] + "..."


def render_menu(cfg):
    return """
============================================================
   MAA / MaaEnd 本体更新器        镜像：%s
   零系统改动：不装证书 · 不改 hosts · 不写程序配置
------------------------------------------------------------
   MAA    : %s
   MaaEnd : %s
============================================================

   1. 仅检查更新（干跑，不下载任何文件）
   2. 更新 MAA
   3. 更新 MaaEnd
   4. 更新全部（MAA + MaaEnd）
   5. 更改安装目录 / 查看配置
   6. 查看用法 / 高级选项
   0. 退出
""" % (mirror_text(cfg),
       short_dir(cfg.install_path("maa")),
       short_dir(cfg.install_path("maaend")))


def show_brief(cfg):
    C.log("")
    C.log("  配置文件：%s%s" % (cfg.path, "" if cfg.exists else "   （尚不存在）"))
    C.log("  镜像    ：%s" % ("已禁用（直连）" if not cfg.mirror_enabled
                             else "、".join(cfg.mirror_prefixes) or "(未配置)"))
    for kind, label in KINDS:
        C.log("  %-7s ：%s" % (label, cfg.install_path(kind) or "(未指定)"))


def set_install():
    """菜单里的「更改安装目录」。逐个询问，校验通过才写入配置。"""
    cfg = cfgmod.load()
    show_brief(cfg)
    C.log("")
    C.log("  下面逐个输入安装目录：直接回车 = 保持不变，输入 q = 放弃修改。")
    C.log("  提示：可以直接把文件夹从资源管理器拖进本窗口，再按回车。")

    while True:
        C.log("")
        C.log("   1. 指定 MAA     2. 指定 MaaEnd     3. 查看完整配置     0. 返回")
        try:
            ch = input("  请选择 [0-3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            C.log("")
            return
        if ch == "0":
            return
        if ch == "3":
            C.log("")
            C.log(cfgmod.format_config(cfg))
            continue
        target = {"1": ("maa", "MAA"), "2": ("maaend", "MaaEnd")}.get(ch)
        if not target:
            C.log("  无效输入。")
            continue
        kind, label = target
        C.log("  %s 当前：%s" % (label, cfg.install_path(kind) or "(未指定)"))
        try:
            got = input("  新目录 > ").strip()
        except (EOFError, KeyboardInterrupt):
            C.log("")
            return
        if got.lower() in ("q", "quit", "exit"):
            return
        if not got:
            continue
        path = locate.normalize(got)
        good, why = locate.validate(kind, path)
        if not good:
            C.log("  [x] %s -> %s" % (path or got, why))
            content = locate.describe_dir(path)
            if content:
                C.log("      该目录内容：%s" % content)
            hits = locate.probe_children(kind, path)
            for child, ver in hits:
                C.log("      子目录候选：%s  %s" % (child, ver))
            continue
        cfg.set_install_path(kind, path)
        try:
            cfg.save()
            C.ok("%s -> %s（已写入 %s）" % (label, path, cfg.path))
        except OSError as exc:
            C.warn("校验通过，但写入配置失败：%s" % exc)


def menu():
    while True:
        C.log(render_menu(cfgmod.load()))
        try:
            ch = input("请选择 [0-6]: ").strip()
        except (EOFError, KeyboardInterrupt):
            C.log("")
            return 0
        if ch == "0":
            return 0
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
        elif ch == "5":
            set_install()
            input("按回车返回菜单…")
        elif ch == "6":
            C.log(USAGE)
            input("按回车返回菜单…")
        else:
            C.log("  无效输入，请重新选择。")


# ---------------------------------------------------------------------------
# 分发
# ---------------------------------------------------------------------------

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

    raw = args[0].strip('"')
    if os.path.isdir(raw) or os.path.isfile(raw):
        C.log("[!] 收到一个路径，但没有说明是哪个程序：%s" % raw)
        C.log("")
        C.log("    想把它指定为安装目录的话，请这样写：")
        C.log('      update-all.bat maa    --install "%s"' % raw)
        C.log('      update-all.bat maaend --install "%s"' % raw)
        C.log("")
        C.log("    也可以先打开菜单（直接双击 update-all.bat），选 5 手工指定。")
        return 2

    C.log("[x] 未知参数：%s" % t)
    C.log(USAGE)
    return 2


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


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        C.log("\n已中断。")
        sys.exit(130)
