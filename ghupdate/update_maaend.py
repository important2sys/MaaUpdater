# -*- coding: utf-8 -*-
"""
MaaEnd 本体更新器（方案 B）

流程：读配置 -> 定位安装目录（手动指定）-> 进程检查 -> 读 interface.json 版本 ->
查 GitHub 最新 -> 清理 .downloading 残骸 -> 镜像下载 -> SHA256 校验 -> 备份 ->
解压覆盖 -> 版本复核

不装证书、不改 hosts、不写程序配置（只读 interface.json 用于探测版本）。
配置项与目录指定见 ../docs/ghupdate-可配置化与GUI规划.md。
"""

import argparse
import glob
import json
import os
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

KIND = "maaend"
MARKER = "MaaEnd.exe"
REPO = "MaaEnd/MaaEnd"

def read_interface_version(install_dir):
    p = os.path.join(install_dir, "interface.json")
    if not os.path.isfile(p):
        return ""
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d.get("version") or ""
    except Exception as e:  # noqa: BLE001
        C.warn("读取 interface.json 失败：%s" % e)
        return ""


def pick_asset(assets, tag):
    exact = "MaaEnd-win-x86_64-%s.zip" % tag
    for a in assets:
        if a.get("name") == exact:
            return a
    for a in assets:
        n = a.get("name") or ""
        if "win-x86_64" in n and n.endswith(".zip"):
            return a
    return None


def find_residue(install_dir):
    pat = os.path.join(install_dir, "cache", "*.downloading")
    return sorted(glob.glob(pat))


def main():
    ap = argparse.ArgumentParser(
        description="MaaEnd 本体更新器（镜像可配置、安装目录手动指定）")
    C.add_config_args(ap, MARKER)
    ap.add_argument("--check", action="store_true", help="只检查不下载（干跑）")
    ap.add_argument("--keep-residue", action="store_true", help="保留 cache\\*.downloading 残骸")
    ap.add_argument("--restart", action="store_true", help="更新完成后启动 MaaEnd")
    ap.add_argument("-y", "--yes", action="store_true", help="不再交互确认")
    ap.add_argument("--no-backup", action="store_true", help="跳过备份（不建议）")
    ap.add_argument("--no-verify", action="store_true", help="无官方摘要时仍继续（不建议）")
    ap.add_argument("--proxy", default="", help="可选：显式代理")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(here, "_cache")
    os.makedirs(cache_dir, exist_ok=True)

    # ---- 0. 读配置 + 定位安装目录 ----
    cfg, install = C.setup(args, KIND, title="MaaEnd 本体更新",
                           version_of=read_interface_version)
    proxy = cfg.proxy or None

    # ---- 1. 进程检查 ----
    if C.process_running(MARKER):
        C.die("MaaEnd.exe 正在运行，请先完全退出 MaaEnd 再执行更新")
    C.ok("MaaEnd 未在运行")

    # ---- 2. 当前版本 ----
    cur = C.norm_ver(read_interface_version(install))
    C.log("  interface.json 版本 : %s" % (cur or "(读不到)"))

    # ---- 3. 最新版本 ----
    C.log("\n[1/5] 查询 GitHub 最新 Release…")
    rel = C.github_release(REPO, proxy=proxy)
    tag = C.norm_ver(rel.get("tag_name") or "")
    if not tag:
        C.die("GitHub 未返回 tag_name")
    assets = rel.get("assets") or []
    C.ok("当前 %s  ->  最新 %s" % (cur or "?", tag))

    if cur and cur.lower() == tag.lower():
        C.ok("已是最新版本，无需更新。")
        return 0

    # ---- 4. 选包 ----
    C.log("\n[2/5] 选择更新包…")
    asset = pick_asset(assets, tag)
    if not asset:
        C.die("Release %s 中没有 win-x86_64 的 .zip 资产" % tag)
    name = asset["name"]
    size = asset.get("size") or 0
    origin = asset["browser_download_url"]
    digest = asset.get("digest")
    C.ok("命中：%s（%s）" % (name, C.human(size)))
    if digest:
        C.ok("官方摘要 %s" % digest)
    else:
        C.warn("该资产未提供官方摘要")
        if cfg.get("behavior.verify", True):
            C.die("无摘要可校验，为安全起见中止（如确认要继续，加 --no-verify）")

    residue = [] if cfg.get("behavior.keep_residue", False) else find_residue(install)

    dest = os.path.join(cache_dir, name)

    # ---- 干跑 ----
    if args.check:
        C.log("\n[--check] 干跑结束，未下载、未改动任何文件。")
        C.log("  计划：下载 %s（%s） -> SHA256 校验 -> 备份 -> 解压覆盖" % (name, C.human(size)))
        for r in residue:
            C.log("  计划：清理残骸 %s（%s）" % (os.path.basename(r), C.human(os.path.getsize(r))))
        return 0

    # ---- 确认 ----
    extra = ""
    if residue:
        tot = sum(os.path.getsize(r) for r in residue)
        extra = "，并清理 %d 个下载残骸（%s）" % (len(residue), C.human(tot))
    if not C.confirm("\n即将更新 MaaEnd：%s -> %s%s。开始？" % (cur or "?", tag, extra), args.yes):
        C.log("已取消。")
        return 0

    # ---- 5. 下载 ----
    C.log("\n[3/5] 下载更新包…")
    C.download_asset(cfg, origin, dest, expected_size=size, proxy=proxy)

    # ---- 6. 校验 ----
    C.log("\n[4/5] SHA256 校验…")
    if digest:
        good, actual = C.verify_sha256(dest, digest)
        if not good:
            C.die("SHA256 不符！已中止，未覆盖任何文件。\n  期望 %s\n  实得 %s" % (digest, actual))
        C.ok("SHA256 一致：%s" % actual)
    else:
        C.warn("已按配置跳过校验（behavior.verify = false）")

    # ---- 清理残骸 ----
    if residue:
        C.log("\n[清理] 删除下载残骸…")
        for r in residue:
            try:
                sz = os.path.getsize(r)
            except OSError:
                sz = 0
            try:
                os.remove(r)
                C.ok("已删除 %s（%s）" % (os.path.basename(r), C.human(sz)))
            except Exception as e:  # noqa: BLE001
                C.warn("删除失败 %s：%s" % (r, e))

    # ---- 备份 + 解压 ----
    with zipfile.ZipFile(dest) as zf:
        entries = [n for n in zf.namelist() if not n.endswith("/")]
        removelist = []
        if "removelist.txt" in zf.namelist():
            raw = zf.read("removelist.txt").decode("utf-8-sig", "replace")
            removelist = [l.strip() for l in raw.splitlines() if l.strip()]
        C.log("\n  包内文件 %d 个，removelist %d 条" % (len(entries), len(removelist)))

        if cfg.get("behavior.backup", True):
            stamp = time.strftime("%Y%m%d-%H%M%S")
            bdir = os.path.join(here, "_backup", "MaaEnd-%s" % stamp)
            est = C.backup_size_estimate(entries + removelist, install)
            C.log("[备份] 目标 %s（约 %s）" % (bdir, C.human(est)))
            n, total = C.backup_paths(entries + removelist, install, bdir)
            C.ok("已备份 %d 个文件，%s" % (n, C.human(total)))
            C.log("       回滚：把该目录内容复制回 %s 即可" % install)

        C.log("\n[5/5] 解压覆盖…")
        cnt = C.safe_extractall(zf, install)
        C.ok("已写入 %d 个条目" % cnt)

    # removelist（MaaEnd 通常没有）
    rl_path = os.path.join(install, "removelist.txt")
    if os.path.isfile(rl_path):
        with open(rl_path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = [l.strip() for l in f if l.strip()]
        for rel in lines:
            t = os.path.join(install, rel.replace("/", os.sep))
            if os.path.isfile(t):
                try:
                    os.remove(t)
                except Exception:
                    pass
        try:
            os.remove(rl_path)
        except Exception:
            pass

    # ---- 版本复核 ----
    new_ver = C.norm_ver(read_interface_version(install))
    C.log("")
    if new_ver.strip("v") == tag.strip("v"):
        C.ok("更新完成，interface.json 版本已确认为 %s" % new_ver)
    else:
        C.warn("更新已写入，但版本读回为 %s（目标 %s），请手动确认" % (new_ver or "?", tag))

    if cfg.get("behavior.restart", False):
        exe = os.path.join(install, MARKER)
        C.log("启动 %s …" % exe)
        os.startfile(exe)  # noqa: S606
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        C.log("\n已中断。")
        sys.exit(130)
