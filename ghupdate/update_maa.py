# -*- coding: utf-8 -*-
"""
MAA 本体更新器（方案 B）

流程：读配置 -> 定位安装目录（手动指定）-> 进程检查 -> 探测当前版本 ->
查最新 -> 选包(优先 OTA 增量) -> 镜像下载 -> SHA256 校验 -> 备份 ->
解压覆盖 + 应用 removelist -> 版本复核

不装证书、不改 hosts、不写程序配置（只读配置文件用于探测版本）。
配置项与目录指定见 ../docs/ghupdate-可配置化与GUI规划.md，用法见 update-all.bat / README.md
"""

import argparse
import json
import os
import re
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402
from core import events as _events  # noqa: E402

KIND = "maa"
MARKER = "MAA.exe"

# OTA 包名：MAAComponent-OTA-<from>_<to>-win-x64.zip
OTA_RE = re.compile(r"^MAAComponent-OTA-(.+?)_(.+?)-win-x64\.zip$", re.I)

# --prune 允许清理的顶层目录（用户目录永远排除）
PRUNE_ROOTS = ["resource", "externals", "Res", "Python"]


# ---------------------------------------------------------------------------
# 版本探测
# ---------------------------------------------------------------------------

def find_update_block(node):
    """在 gui 配置树里定位 {Name, UpdatePackage, ...} 这一段。"""
    if isinstance(node, dict):
        if "UpdatePackage" in node and "Name" in node:
            return node
        for v in node.values():
            r = find_update_block(v)
            if r:
                return r
    elif isinstance(node, list):
        for v in node:
            r = find_update_block(v)
            if r:
                return r
    return None


def detect_from_config(install_dir):
    for fn in ("gui.new.json", "gui.json"):
        p = os.path.join(install_dir, "config", fn)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:  # noqa: BLE001
            C.warn("读取 %s 失败：%s" % (fn, e))
            continue
        blk = find_update_block(data)
        if blk:
            return blk.get("UpdatePackage") or "", blk.get("Name") or "", fn
    return "", "", ""


def pick_asset(assets, name):
    """在同名资产里优先取 MaaRelease 仓库的那一条。"""
    cands = [a for a in assets if a.get("name") == name]
    for a in cands:
        if "/MaaRelease/" in (a.get("browser_download_url") or ""):
            return a
    return cands[0] if cands else None


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="MAA 本体更新器（镜像可配置、安装目录手动指定）")
    C.add_config_args(ap, MARKER)
    ap.add_argument("--check", action="store_true", help="只检查不下载（干跑）")
    ap.add_argument("--prune", action="store_true", help="按新 filelist 清理废弃程序文件（默认关闭）")
    ap.add_argument("--restart", action="store_true", help="更新完成后启动 MAA")
    ap.add_argument("-y", "--yes", action="store_true", help="不再交互确认")
    ap.add_argument("--no-backup", action="store_true", help="跳过备份（不建议）")
    ap.add_argument("--no-verify", action="store_true", help="无官方摘要时仍继续（不建议）")
    ap.add_argument("--proxy", default="", help="可选：显式代理，如 http://127.0.0.1:7890")
    ap.add_argument("--channel", default="stable", choices=["stable", "beta", "alpha"])
    args = ap.parse_args(argv)

    here = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(here, "_cache")
    os.makedirs(cache_dir, exist_ok=True)

    # ---- 0. 读配置 + 定位安装目录 ----
    cfg, install = C.setup(
        args, KIND, title="MAA 本体更新",
        version_of=lambda p: C.pe_file_version(os.path.join(p, MARKER)))
    proxy = cfg.proxy or None

    # ---- 1. 进程检查 ----
    if C.process_running(MARKER):
        C.die("MAA.exe 正在运行，请先完全退出 MAA 再执行更新（运行时文件被占用，替换必然失败）")
    C.ok("MAA 未在运行")

    # ---- 2. 探测当前版本 ----
    pkg_name, cfg_target, cfg_file = detect_from_config(install)
    cur_ver = ""
    m = OTA_RE.match(pkg_name or "")
    if m:
        cur_ver = C.norm_ver(m.group(1))
    exe_ver = C.pe_file_version(os.path.join(install, MARKER))
    exe_norm = C.norm_ver(exe_ver) if exe_ver else ""

    C.log("  安装目录名     : %s" % os.path.basename(install))
    C.log("  目录名不代表版本，以实际程序为准：")
    C.log("  MAA.exe 版本   : %s" % (exe_norm or "(读不到)"))
    C.log("  配置待更包     : %s" % (pkg_name or "(无)"))
    C.log("  配置目标版本   : %s" % (cfg_target or "(无)"))

    if cur_ver and exe_norm and cur_ver != exe_norm:
        C.warn("配置里的起点版本(%s) 与 exe 实际版本(%s) 不一致，将以 exe 版本为准做全量更新" % (cur_ver, exe_norm))
        cur_ver = exe_norm

    # ---- 3. 查最新版本 ----
    C.log("\n[1/6] 查询 MAA 最新版本（%s 频道）…" % args.channel)
    latest, detail = C.maa_latest(args.channel, proxy=proxy)
    latest = C.norm_ver(latest)
    assets = (detail.get("details") or {}).get("assets") or []
    C.ok("当前 %s  ->  最新 %s" % (cur_ver or "?", latest))

    if cur_ver and cur_ver.lower() == latest.lower():
        C.ok("已是最新版本，无需更新。")
        return 0
    if not cur_ver:
        C.warn("无法确定当前版本，将直接使用全量包")

    # ---- 4. 选包 ----
    C.log("\n[2/6] 选择更新包…")
    asset = None
    kind = ""
    if cur_ver:
        ota_name = "MAAComponent-OTA-%s_%s-win-x64.zip" % (cur_ver, latest)
        asset = pick_asset(assets, ota_name)
        if asset:
            kind = "OTA 增量"
    if not asset:
        full_name = "MAA-%s-win-x64.zip" % latest
        asset = pick_asset(assets, full_name)
        kind = "全量" if asset else ""
    if not asset:
        C.die("官方资产列表里既没有 %s 对应的 OTA，也没有 MAA-%s-win-x64.zip" % (cur_ver or "?", latest))
    name = asset["name"]
    size = asset.get("size") or 0
    origin = asset["browser_download_url"]
    C.ok("命中 %s 包：%s（%s）" % (kind, name, C.human(size)))

    # ---- 5. 取官方摘要 ----
    C.log("\n[3/6] 获取官方 SHA256 摘要…")
    digest = None
    try:
        rel = C.github_release("MaaAssistantArknights/MaaRelease", tag=latest, proxy=proxy)
        digest = C.release_digests(rel).get(name)
    except Exception as e:  # noqa: BLE001
        C.warn("从 GitHub API 取摘要失败：%s" % e)
    if digest:
        C.ok("官方摘要 %s" % digest)
    else:
        C.warn("未取到官方摘要")
        if cfg.get("behavior.verify", True):
            C.die("无摘要可校验，为安全起见中止（如确认要继续，可加 --no-verify 或改配置 behavior.verify）")

    dest = os.path.join(cache_dir, name)

    # ---- 干跑 ----
    if args.check:
        C.log("\n[--check] 干跑结束，未下载、未改动任何文件。")
        C.log("  计划：下载 %s（%s） -> SHA256 校验 -> 备份 -> 解压覆盖" % (name, C.human(size)))
        return 0

    if not C.confirm("\n即将更新 MAA：%s -> %s（%s）。开始？" % (cur_ver or "?", latest, kind), args.yes):
        C.log("已取消。")
        return 0

    # ---- 6. 下载 ----
    C.log("\n[4/6] 下载更新包…")
    C.download_asset(cfg, origin, dest, expected_size=size, proxy=proxy)

    # ---- 7. 校验 ----
    C.log("\n[5/6] SHA256 校验…")
    if digest:
        good, actual = C.verify_sha256(dest, digest)
        if not good:
            C.die("SHA256 不符！已中止，未覆盖任何文件。\n  期望 %s\n  实得 %s" % (digest, actual))
        C.ok("SHA256 一致：%s" % actual)
    else:
        C.warn("已按配置跳过校验（behavior.verify = false）")

    # ---- 读包内清单 ----
    with zipfile.ZipFile(dest) as zf:
        entries = [n for n in zf.namelist() if not n.endswith("/")]
        removelist = []
        if "removelist.txt" in zf.namelist():
            raw = zf.read("removelist.txt").decode("utf-8-sig", "replace")
            removelist = [l.strip() for l in raw.splitlines() if l.strip()]
        C.log("  包内文件 %d 个，removelist %d 条" % (len(entries), len(removelist)))

        # ---- 备份 ----
        if cfg.get("behavior.backup", True):
            stamp = time.strftime("%Y%m%d-%H%M%S")
            bdir = os.path.join(here, "_backup", "MAA-%s" % stamp)
            est = C.backup_size_estimate(entries + removelist, install)
            C.log("\n[备份] 目标 %s（约 %s）" % (bdir, C.human(est)))
            n, total = C.backup_paths(entries + removelist, install, bdir)
            C.ok("已备份 %d 个文件，%s" % (n, C.human(total)))
            C.log("       回滚：把该目录内容复制回 %s 即可" % install)

        # ---- 应用 ----
        C.log("\n[6/6] 解压覆盖…")
        cnt = C.safe_extractall(zf, install)
        C.ok("已写入 %d 个条目" % cnt)

    # removelist
    rl_path = os.path.join(install, "removelist.txt")
    removed = 0
    if os.path.isfile(rl_path):
        with open(rl_path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = [l.strip() for l in f if l.strip()]
        for rel in lines:
            t = os.path.join(install, rel.replace("/", os.sep))
            if os.path.isfile(t):
                try:
                    os.remove(t)
                    removed += 1
                except Exception as e:  # noqa: BLE001
                    C.warn("删除失败 %s：%s" % (rel, e))
        try:
            os.remove(rl_path)
        except Exception:
            pass
        C.ok("按 removelist 删除 %d 个旧文件" % removed)

    # prune（可选）
    if cfg.get("behavior.prune", False):
        C.log("\n[--prune] 按新 filelist.txt 清理废弃程序文件（仅限 %s）…" % "/".join(PRUNE_ROOTS))
        rm = C.prune_by_filelist(install, "filelist.txt", PRUNE_ROOTS)
        C.ok("清理 %d 个多余文件" % rm)
    else:
        C.log("  （未启用 --prune，已跳过废弃文件清理）")

    # ---- 版本复核 ----
    new_ver = C.norm_ver(C.pe_file_version(os.path.join(install, MARKER)))
    C.log("")
    if new_ver.strip("v") == latest.strip("v"):
        C.ok("更新完成，MAA.exe 版本已确认为 %s" % new_ver)
    else:
        C.warn("更新已写入，但 exe 版本读回为 %s（目标 %s），请手动确认" % (new_ver or "?", latest))

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
    except _events.UpdateError as exc:
        # die() 已经打印过 [x] 信息，这里只把异常转成退出码
        sys.exit(exc.code)
