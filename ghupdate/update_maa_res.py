# -*- coding: utf-8 -*-
"""
MAA 资源更新器（关卡数据 / 模板图）

流程：读配置 -> 定位安装目录（手动指定）-> 进程检查 -> 读本机 resource/version.json
-> 查 mirrorchyan 远端版本 -> 比对 -> 镜像下载 archive/main.zip -> 包内版本语义校验
-> CRC32 逐文件比对 -> 备份 -> 只覆盖变化的文件 -> 版本复核

与「本体更新」的两点关键差别：

  1. **版本来源不同**：走 mirrorchyan 的资源接口（无需 CDK，实测 44 ms），
     本机版本在 resource/version.json 的 last_updated —— 两者是同一个字符串，
     直接比对即可，不需要 norm_ver。

  2. **没有官方 SHA256**：GitHub 的 archive 包不提供 digest，而它的 ETag 经实测
     **证伪**（不是内容哈希），所以校验改成两级：
       ① 语义：包内 resource/version.json 必须严格等于远端版本 —— 挡空包、
          错分支、截断的 zip、镜像返回的错误页、被换成的旧版本；
       ② 传输：zipfile 自带的 CRC32（testzip + 逐条解压校验）。

写入策略：**只写变化的文件**（size + CRC32 逐文件比对），不整目录覆盖。
实测 5311 个文件零误判，日常更新写入量通常在个位数 MB。
包内**不含** custom_infrast/ config/ copilot/ onnx/ PaddleOCR/ 等目录，
因此不会碰到用户数据；也正因如此**不做 prune**（包内没有 removelist，
无法判断哪些本地文件该删），保守只增改、不删。

不装证书、不改 hosts、不写程序配置（只读 version.json 用于探测版本）。
"""

import argparse
import json
import os
import shutil
import sys
import time
import zipfile
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402
from core import events as _events  # noqa: E402

#: 资源就在 MAA 安装目录下，所以与本体共用同一个 install.maa.path
KIND = "maa"
MARKER = "MAA.exe"
RES_DIR = "resource"

#: 远端版本来源：mirrorchyan 资源接口（无需 CDK）
MIRRORCHYAN_RES_ID = "MaaResource"
MIRRORCHYAN_URL = "https://mirrorchyan.com/api/resources/%s/latest" % MIRRORCHYAN_RES_ID

#: 下载源：GitHub archive（302 到 codeload），可被镜像前缀代理
ARCHIVE_ORIGIN = ("https://github.com/MaaAssistantArknights/MaaResource"
                  "/archive/refs/heads/main.zip")

#: 包内只认这一层；顶层目录名（MaaResource-main/）刻意忽略，
#: 这样 GitHub 改命名规则也不会崩。
PACK_INNER = "resource/"

#: 这几个条目不落地（本机 resource\ 本来就没有 .gitignore）
SKIP_RELS = {"resource/.gitignore"}

CRC_CHUNK = 1 << 20


# ---------------------------------------------------------------------------
# 版本
# ---------------------------------------------------------------------------

def read_local_version(install_dir):
    """读 <install>/resource/version.json 的 last_updated。失败返回 ''。

    刻意不打印任何东西 —— 它同时被 GUI 的只读扫描（无控制台）当作
    ``version_of`` 回调调用，安静失败比在界面上弹一堆日志更合适。
    """
    path = os.path.join(install_dir, RES_DIR, "version.json")
    if not install_dir or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except Exception:  # noqa: BLE001
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("last_updated") or data.get("version") or "").strip()


def remote_version(timeout=None, proxy=None):
    """查 mirrorchyan 的远端资源版本。返回 (version_name, info_dict)。

    失败一律抛 UpdateError（致命）—— 没有远端版本就无法校验包，不能放行。
    """
    data = C.http_get_json(MIRRORCHYAN_URL, timeout=timeout or C.DEFAULT_TIMEOUT, proxy=proxy)
    code = data.get("code")
    if code != 0:
        C.die("mirrorchyan 接口返回错误（code=%s）：%s" % (code, data.get("msg") or "未知错误"))
    info = data.get("data") or {}
    ver = str(info.get("version_name") or "").strip()
    if not ver:
        C.die("mirrorchyan 未返回 version_name，无法确定远端资源版本")
    return ver, info


# ---------------------------------------------------------------------------
# 压缩包解析
# ---------------------------------------------------------------------------

def inner_rel(name):
    """zip 内条目名 -> 安装目录相对路径；不属于资源文件则返回 ''。

    只认 ``…（最多一层）/resource/xxx``：
        MaaResource-main/resource/stages.json  ->  resource/stages.json
        resource/stages.json                   ->  resource/stages.json
        MaaResource-main/cache/x.json          ->  ''
        a/b/resource/x.json                    ->  ''
    """
    name = str(name or "").replace("\\", "/")
    idx = name.find(PACK_INNER)
    if idx < 0:
        return ""
    if name[:idx].count("/") > 1:
        return ""
    rel = name[idx:]
    if rel == PACK_INNER or rel.endswith("/"):
        return ""
    return rel


def pack_entries(zf):
    """包内需要落地的条目：[(rel, ZipInfo)]（跳过 SKIP_RELS）。"""
    out = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        rel = inner_rel(info.filename)
        if rel and rel not in SKIP_RELS:
            out.append((rel, info))
    return out


def read_pack_version(zf):
    """读包内 resource/version.json 的 last_updated。"""
    for info in zf.infolist():
        if inner_rel(info.filename) == RES_DIR + "/version.json":
            try:
                data = json.loads(zf.read(info).decode("utf-8-sig"))
            except Exception:  # noqa: BLE001
                return ""
            if isinstance(data, dict):
                return str(data.get("last_updated") or data.get("version") or "").strip()
    return ""


# ---------------------------------------------------------------------------
# 差异比对与写入
# ---------------------------------------------------------------------------

def file_crc32(path, chunk=CRC_CHUNK):
    crc = 0
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            crc = zlib.crc32(block, crc)
    return crc & 0xFFFFFFFF


def plan_writes(entries, install_dir):
    """逐文件按 size + CRC32 比对。返回 (todo, same)。

    todo 里是 [(rel, ZipInfo)]，且 ``resource/version.json`` 被排到最后 ——
    万一中途写入失败，版本号仍停在旧值，下次运行会重新补写，不会误判成「已更新」。
    """
    todo, same = [], 0
    for rel, info in entries:
        dst = os.path.join(install_dir, rel.replace("/", os.sep))
        if not os.path.isfile(dst) or os.path.getsize(dst) != info.file_size:
            todo.append((rel, info))
            continue
        try:
            if file_crc32(dst) == (info.CRC & 0xFFFFFFFF):
                same += 1
                continue
        except OSError:
            pass
        todo.append((rel, info))

    ver_rel = RES_DIR + "/version.json"
    head = [x for x in todo if x[0] != ver_rel]
    tail = [x for x in todo if x[0] == ver_rel]
    return head + tail, same


def apply_entries(zf, todo, install_dir):
    """逐条写入（先写 .tmp 再 os.replace，单文件原子）。返回 (写入数, 失败列表)。"""
    written = 0
    fails = []
    ver_rel = RES_DIR + "/version.json"
    for rel, info in todo:
        if fails and rel == ver_rel:
            fails.append((rel, "前序文件写入失败，已跳过版本文件以免被误判为已更新"))
            continue
        dst = os.path.join(install_dir, rel.replace("/", os.sep))
        folder = os.path.dirname(dst)
        tmp = dst + ".ghupdate.tmp"
        try:
            if folder:
                os.makedirs(folder, exist_ok=True)
            with zf.open(info) as src, open(tmp, "wb") as out:
                shutil.copyfileobj(src, out, CRC_CHUNK)
            os.replace(tmp, dst)
            written += 1
        except Exception as exc:  # noqa: BLE001
            try:
                os.remove(tmp)
            except OSError:
                pass
            fails.append((rel, str(exc)))
    return written, fails


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="MAA 资源更新器（关卡数据 / 模板图；镜像可配置、安装目录手动指定）")
    C.add_config_args(ap, MARKER)
    ap.add_argument("--check", action="store_true", help="只检查不下载（干跑）")
    ap.add_argument("--force", action="store_true",
                    help="版本号相同也强制逐文件比对并补齐差异（用于修复残缺的本地资源）")
    ap.add_argument("-y", "--yes", action="store_true", help="不再交互确认")
    ap.add_argument("--no-backup", action="store_true", help="跳过备份（不建议）")
    ap.add_argument("--proxy", default="", help="可选：显式代理，如 http://127.0.0.1:7890")
    args = ap.parse_args(argv)

    here = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(here, "_cache")
    os.makedirs(cache_dir, exist_ok=True)

    # ---- 0. 读配置 + 定位安装目录（与 MAA 本体共用同一个目录）----
    cfg, install = C.setup(args, KIND, title="MAA 资源更新",
                           version_of=read_local_version)
    proxy = cfg.proxy or None
    timeout = int(cfg.get("network.timeout", 30) or 30)

    # ---- 1. 进程检查 ----
    if C.process_running(MARKER):
        C.die("MAA.exe 正在运行，请先完全退出 MAA 再执行更新"
              "（resource 下的文件被占用，覆盖必然失败）")
    C.ok("MAA 未在运行")

    # ---- 2. 本机版本 ----
    local = read_local_version(install)
    if not os.path.isdir(os.path.join(install, RES_DIR)):
        C.warn("安装目录下没有 resource\\ 子目录，将按全新资源处理")
    C.log("  本机资源版本 : %s" % (local or "(无 resource\\version.json)"))

    # ---- 3. 远端版本 ----
    C.log("\n[1/6] 查询资源最新版本（mirrorchyan）…")
    remote, info = remote_version(timeout=timeout, proxy=proxy)
    note = str(info.get("release_note") or "").strip()
    C.ok("本机 %s  ->  最新 %s%s" % (local or "?", remote, ("（%s）" % note) if note else ""))

    if local and local == remote and not args.force:
        C.ok("资源已是最新，无需更新。")
        return 0
    if local and local == remote:
        C.warn("已按 --force：版本号相同，仍做逐文件比对")

    # ---- 干跑 ----
    if args.check:
        C.log("\n[--check] 干跑结束，未下载、未改动任何文件。")
        C.log("  计划：下载资源包 -> 校验包内版本（须 == %s）" % remote)
        C.log("        -> CRC32 逐文件比对 -> 备份变化文件 -> 只写入变化的文件")
        C.log("  下载源：%s" % ARCHIVE_ORIGIN)
        return 0

    if not C.confirm("\n即将更新 MAA 资源：%s -> %s。开始？" % (local or "?", remote), args.yes):
        C.log("已取消。")
        return 0

    # ---- 4. 下载 ----
    # 刻意**不传 expected_size**，从而每次都重新下载：
    # 该 URL 指向分支 main，内容会随时间变化，复用上次缓存的 zip 会拿到旧版本，
    # 然后被下面的「包内版本必须等于远端版本」拦下来 —— 用户将永远卡在失败里。
    # 不传 expected_size 时，download() 会改从响应头读 Content-Length 来显示进度。
    dest = os.path.join(cache_dir, "MaaResource.zip")
    C.log("\n[2/6] 下载资源包（镜像优先，直连兜底）…")
    C.download_asset(cfg, ARCHIVE_ORIGIN, dest, proxy=proxy)

    # ---- 5~8. 校验 / 比对 / 备份 / 写入 ----
    C.log("\n[3/6] 校验资源包…")
    if not zipfile.is_zipfile(dest):
        C.die("下载到的不是合法 ZIP（镜像可能返回了错误页），已中止，未改动任何文件")

    with zipfile.ZipFile(dest) as zf:
        broken = zf.testzip()
        if broken:
            C.die("压缩包内文件 CRC 校验失败（%s），已中止，未改动任何文件" % broken)

        pack_ver = read_pack_version(zf)
        entries = pack_entries(zf)
        if not entries:
            C.die("包内没有 resource/ 下的文件，结构不符，已中止，未改动任何文件")
        C.log("  包内 resource 文件 %d 个，包内版本 %s" % (len(entries), pack_ver or "(无)"))
        if pack_ver != remote:
            C.die("包内版本(%s) 与远端版本(%s) 不一致，已中止，未改动任何文件。\n"
                  "  这通常意味着镜像返回了旧缓存或错误内容。"
                  % (pack_ver or "空", remote))
        C.ok("包内版本与远端一致")

        C.log("\n[4/6] 比对差异（size + CRC32）…")
        todo, same = plan_writes(entries, install)
        write_bytes = sum(info.file_size for _rel, info in todo)
        C.ok("包内 %d 个：本机同内容 %d 个，需写入 %d 个（%s）"
             % (len(entries), same, len(todo), C.human(write_bytes)))
        if not todo:
            C.ok("本机资源与远端逐字节一致，无需写入。")
            return 0

        C.log("\n[5/6] 备份将被覆盖的文件…")
        if cfg.get("behavior.backup", True):
            rels = [rel for rel, _info in todo]
            stamp = time.strftime("%Y%m%d-%H%M%S")
            bdir = os.path.join(here, "_backup", "MaaResource-%s" % stamp)
            est = C.backup_size_estimate(rels, install)
            C.log("  目标 %s（约 %s）" % (bdir, C.human(est)))
            n, total = C.backup_paths(rels, install, bdir)
            C.ok("已备份 %d 个文件，%s" % (n, C.human(total)))
            C.log("       回滚：把该目录内容复制回 %s 即可" % install)
        else:
            C.warn("已按配置跳过备份（behavior.backup = false）")

        C.log("\n[6/6] 写入变化文件…")
        written, fails = apply_entries(zf, todo, install)
        C.ok("已写入 %d 个文件" % written)
        if fails:
            for rel, why in fails[:10]:
                C.warn("未写入 %s：%s" % (rel, why))
            if len(fails) > 10:
                C.warn("……另有 %d 个失败未列出" % (len(fails) - 10))
            C.die("有 %d 个文件写入失败（版本文件已跳过，不会被误判为已更新）。\n"
                  "  可重跑本命令重试，或用 _backup 下的备份回滚。" % len(fails))

    # ---- 版本复核 ----
    new_ver = read_local_version(install)
    C.log("")
    if new_ver == remote:
        C.ok("更新完成，resource\\version.json 已确认为 %s" % new_ver)
    else:
        C.warn("写入已完成，但 version.json 读回为 %s（目标 %s），请手动确认"
               % (new_ver or "?", remote))
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
