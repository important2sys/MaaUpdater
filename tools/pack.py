#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把整个项目打成一个「用户视角」的干净 zip。

为什么要有这个脚本
==================
仓库结构是给开发者看的：根目录并列着 ghupdate / ghproxy / docs 三个目录，
还有 .gitattributes / .gitignore / tools\\ 这些与使用无关的东西。直接把仓库
压成 zip，用户打开会一脸茫然 —— 到底点哪个文件？

所以**发布包的结构与仓库结构故意不一样**：

    MaaUpdaterBat\\
    ├── 启动更新器.bat        <- 唯一入口，双击就完事
    ├── 使用说明.txt
    ├── README.md
    ├── ghupdate\\              <- 主程序（界面 + 命令行）
    └── 可选\\                  <- 平时用不到，删了也不影响使用
        ├── ghproxy\\               备用方案（需往系统信任库装本地 CA）
        └── docs\\                  排查记录与设计文档

排除规则与 .gitignore 对齐（运行期产物、私钥、本机缓存），再额外排除 VCS
元数据与打包产物自身。

ghupdate/config.json 默认**打进包里**：自用或换机时省得重新指定安装目录。
想发给别人时加 --no-config，改用 config.example.json 作模板。

用法
====
    python tools\\pack.py                 打出 dist\\MaaUpdaterBat-YYYYMMDD.zip
    python tools\\pack.py --list           只列出会打包什么，不写文件
    python tools\\pack.py --no-config      发给别人时用（不含本机安装路径）
    python tools\\pack.py --out D:\\x.zip    自定义输出位置
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 解压后最外层的文件夹名
TOP = "MaaUpdaterBat"

# ---------------------------------------------------------------------------
# 包内布局：(类型, 仓库内相对路径, 包内相对路径)
#   file -> 单个文件搬到包根
#   dir  -> 整个目录搬到包内指定位置
# 没列在这里的东西一律不进包（.git / tools / .gitattributes / .gitignore 等）
# ---------------------------------------------------------------------------
LAYOUT = [
    ("file", "启动更新器.bat", "启动更新器.bat"),
    ("file", "使用说明.txt", "使用说明.txt"),
    ("file", "README.md", "README.md"),
    ("dir", "ghupdate", "ghupdate"),
    ("dir", "ghproxy", "可选/ghproxy"),
    ("dir", "docs", "可选/docs"),
]

# 目录名黑名单：任意层级命中即整棵剪掉
SKIP_DIRS = {
    "__pycache__",
    "_cache", "_backup",          # 下载缓存与更新前备份
    "certs",                      # ghproxy 的 CA 与叶证书（含私钥！）
    ".git", ".github",
    "dist", "build", "tools",     # 打包产物与打包脚本自身
    ".venv", "venv", "ENV", "env",
    ".vscode", ".idea",
    ".pytest_cache", ".mypy_cache",
}

# 后缀黑名单（小写比较）
SKIP_EXT = (
    ".pyc", ".pyo", ".pyd",
    ".log", ".pid", ".tmp", ".temp", ".bak", ".orig", ".rej",
    ".key", ".crt", ".csr", ".srl",   # 私钥与证书，绝不进包
)

# 文件名黑名单
SKIP_NAMES = {
    "ca_installed.flag", "config.json.tmp",
    "Thumbs.db", "desktop.ini", "Desktop.ini", ".DS_Store",
}

# 打包时强制转成 CRLF 的后缀。
#   .bat/.cmd —— cmd.exe 的原生行尾，LF-only 会导致解析错位（见 _add_one）
#   .txt/.md/.json —— 用户会用记事本打开，CRLF 在 Windows 上最稳，
#                     且这三类内容在任何解析器下都不区分 CRLF 与 LF
CRLF_EXT = (".bat", ".cmd", ".txt", ".md", ".json")

# 打包后自检：这些东西出现任何一个都说明排除规则漏了
FORBIDDEN_IN_ZIP = (
    "__pycache__", "_cache/", "_backup/", ".git/",
    "certs/", ".key", ".log", ".pid", "dist/", "tools/",
)

# 摘要里给顶层条目加的说明（键是包内顶层条目名）
TOP_NOTES = {
    "启动更新器.bat": "<-- 双击这个就行",
    "ghupdate": "主程序（界面 + 命令行）",
    "可选": "平时用不到，删了也不影响使用",
}

# 摘要里要展开一层的目录（其余目录只显示文件数，细节留给各自的 README）
EXPAND_DIRS = ("可选",)

# 摘要里包根条目的排列顺序：入口永远排第一，用户扫一眼就知道点哪个。
# 没列在这里的按名字排在后面。
ROOT_ORDER = ["启动更新器.bat", "使用说明.txt", "README.md", "ghupdate", "可选"]


# ---------------------------------------------------------------------------
# 收集
# ---------------------------------------------------------------------------
def _walk(src_root, include_config):
    """遍历一个目录，产出 (绝对路径, 相对该目录的 posix 路径)。"""
    for dirpath, dirnames, filenames in os.walk(src_root):
        # 原地剪枝：跳过黑名单目录，顺带排序保证输出稳定
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS and not d.endswith(".egg-info")
        )
        for fn in sorted(filenames):
            if fn in SKIP_NAMES:
                continue
            if fn.lower().endswith(SKIP_EXT):
                continue
            abs_p = os.path.join(dirpath, fn)
            rel_p = os.path.relpath(abs_p, src_root).replace(os.sep, "/")
            # ghupdate/config.json 是本机配置（含个人安装路径），
            # 只有明确要求不带时才排除
            if not include_config and rel_p == "config.json":
                continue
            yield abs_p, rel_p


def collect(include_config=True):
    """返回 ([(绝对路径, 包内相对路径)], [缺失的源路径])。"""
    files = []
    missing = []
    for kind, src_rel, dst_rel in LAYOUT:
        src_abs = os.path.join(ROOT, src_rel)
        if not os.path.exists(src_abs):
            missing.append(src_rel)
            continue
        if kind == "file":
            files.append((src_abs, dst_rel))
        else:
            for abs_p, rel_p in _walk(src_abs, include_config):
                files.append((abs_p, dst_rel + "/" + rel_p))
    return files, missing


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def build_zip(zip_path, files):
    out_dir = os.path.dirname(zip_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=9) as zf:
        for src, rel in files:
            # arcname 用 posix 分隔符；非 ASCII 名字 zipfile 会自动置
            # UTF-8 标志位（general purpose bit 11），Windows 自带解压
            # 与 7-Zip 都能正确还原中文文件名
            _add_one(zf, src, TOP + "/" + rel)
    return zip_path


def _add_one(zf, src, arcname):
    """写入单个文件；对换行敏感的类型强制转成 CRLF。

    仓库里的 .bat 应当已经是 CRLF（.gitattributes 声明了 eol=crlf），
    但"应当"不等于"一定" —— 从 GitHub 的 Download ZIP 取到的、或有人在
    别的平台编辑过的副本都可能是 LF。而 LF-only 的 .bat 会让 cmd.exe 的
    行边界解析错位，症状是满屏「不是内部或外部命令」，可脚本又"看起来
    能跑" —— 极难排查。打包时统一兜一次底，代价为零。
    """
    if arcname.lower().endswith(CRLF_EXT):
        data = open(src, "rb").read()
        norm = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        # from_file 保留原文件的修改时间与权限位
        zi = zipfile.ZipInfo.from_file(src, arcname)
        zi.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(zi, norm, compresslevel=9)
    else:
        zf.write(src, arcname)


def selfcheck(zip_path):
    """回读 zip，检查三类"出错后极难排查"的问题。返回问题描述列表。

    1. 换行敏感的 .bat/.cmd/.txt 必须是 CRLF
    2. 中文文件名必须带 UTF-8 标志位，否则别人解压会乱码
    3. .gitignore 该拦住的运行期产物 / 私钥一个都不许进包
    """
    problems = []
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad:
            problems.append("CRC 校验失败：%s" % bad)

        for info in zf.infolist():
            name = info.filename

            if name.lower().endswith(CRLF_EXT):
                data = zf.read(name)
                if data.count(b"\r\n") != data.count(b"\n"):
                    problems.append("换行符应为 CRLF：%s" % name)

            if any(ord(c) > 127 for c in name) and not (info.flag_bits & 0x800):
                problems.append("中文文件名缺 UTF-8 标志位：%s" % name)

            for f in FORBIDDEN_IN_ZIP:
                if f in name:
                    problems.append("不该出现的文件：%s" % name)
                    break
    return problems


def _human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%.0f %s" % (n, unit)) if unit == "B" else ("%.2f %s" % (n, unit))
        n /= 1024.0


def _build_tree(paths):
    """把 posix 相对路径列表变成嵌套 dict；叶子（文件）用 None 表示。"""
    root = {}
    for p in paths:
        node = root
        parts = p.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = None
    return root


def _count_files(node):
    """递归统计一个目录节点下的文件总数。"""
    n = 0
    for v in node.values():
        n += 1 if v is None else _count_files(v)
    return n


def render_tree(files):
    """渲染包内结构。

    只展开 EXPAND_DIRS 里列出的目录（一层），其余目录仅标注文件数 ——
    把 ghupdate\\core\\gui 全铺开会淹掉真正重要的信息，那些细节
    各自目录下的 README 已经讲清楚了。
    """
    root = _build_tree([rel for _, rel in files])
    lines = ["%s\\" % TOP]

    def emit(node, prefix, depth):
        if depth == 0:
            # 包根按 ROOT_ORDER 排，让入口文件排在第一条
            def sort_key(n):
                try:
                    return (0, ROOT_ORDER.index(n))
                except ValueError:
                    return (1, n)
        else:
            # 下层：目录排在文件前面，同类按名字排序
            def sort_key(n):
                return (node[n] is None, n)

        names = sorted(node, key=sort_key)
        for i, name in enumerate(names):
            last = (i == len(names) - 1)
            child = node[name]
            is_dir = child is not None
            label = name + ("\\" if is_dir else "")
            if is_dir:
                label += "  (%d 个文件)" % _count_files(child)
            if depth == 0:
                note = TOP_NOTES.get(name, "")
                if note:
                    label += "   " + note
            lines.append(prefix + ("└── " if last else "├── ") + label)
            if is_dir and depth == 0 and name in EXPAND_DIRS:
                emit(child, prefix + ("    " if last else "│   "), depth + 1)

    emit(root, "", 0)
    return lines


def print_report(files, zip_path, total_src, zip_size, include_config):
    print()
    print("=" * 66)
    print(" 打包完成")
    print("=" * 66)
    print(" 输出：%s" % zip_path)
    print(" 文件：%d 个" % len(files))
    print(" 体积：%s  ->  %s" % (_human(total_src), _human(zip_size)))
    print(" config.json：%s"
          % ("已包含本机安装路径（换机后路径若不对，在界面「设置…」里改）"
             if include_config else "未包含（对方首次使用时需自行指定安装目录）"))
    print()
    print(" 解压后长这样：")
    for line in render_tree(files):
        print("   " + line)
    print()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="把项目打包成用户视角的发布 zip")
    ap.add_argument("--no-config", action="store_true",
                    help="排除 ghupdate/config.json（发给别人时用）")
    ap.add_argument("--out", metavar="PATH",
                    help="输出 zip 路径（默认 dist\\MaaUpdaterBat-YYYYMMDD.zip）")
    ap.add_argument("--list", action="store_true",
                    help="只列出会打包哪些文件，不写 zip")
    args = ap.parse_args(argv)

    include_config = not args.no_config
    files, missing = collect(include_config=include_config)

    if missing:
        print("[x] 源文件或目录不存在：%s" % "、".join(missing), file=sys.stderr)
        print("    请在仓库根目录下运行本脚本。", file=sys.stderr)
        return 2
    if not files:
        print("[x] 没有收集到任何文件。", file=sys.stderr)
        return 2

    total_src = sum(os.path.getsize(s) for s, _ in files)

    if args.list:
        print("将打包 %d 个文件，合计 %s：" % (len(files), _human(total_src)))
        for _, rel in sorted(files, key=lambda x: x[1]):
            print("  %s/%s" % (TOP, rel))
        return 0

    stamp = _dt.date.today().strftime("%Y%m%d")
    out = args.out or os.path.join(ROOT, "dist",
                                   "MaaUpdaterBat-%s.zip" % stamp)
    out = os.path.abspath(out)

    build_zip(out, files)
    print_report(files, out, total_src, os.path.getsize(out), include_config)

    problems = selfcheck(out)
    if problems:
        print(" 自检未通过（%d 项）：" % len(problems))
        for p in problems:
            print("   - %s" % p)
        print()
        return 3
    print(" 自检：CRLF / 中文文件名编码 / 无敏感文件 —— 全部通过")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
