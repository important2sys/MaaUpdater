# -*- coding: utf-8 -*-
"""
ghupdate 共享工具库 —— 零第三方依赖（只用 Python 标准库）。

用途：为 MAA / MaaEnd 提供「查版本 -> 选包 -> 镜像下载 -> SHA256 校验 ->
解压覆盖 -> 备份回滚」的能力，完全不改动系统（不装证书、不改 hosts、
不写任何程序配置文件，只“读”配置用于版本探测）。

设计基线见 D:\\RRL\\MAA-MaaEnd更新方案B细化.md
"""

import ctypes
import glob
import hashlib
import json
import os
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

# ----------------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------------

#: GitHub 加速镜像前缀（路径式代理：<前缀><完整 github url>）。
#: 2026-10-15 实测 13 个镜像中唯一可用者；官方 mirrors 已全部下线。
MIRROR_PREFIX = "https://ghfast.top/"

UA = "Mozilla/5.0 (compatible; ghupdate/1.0)"
DEFAULT_TIMEOUT = 30
IS_WINDOWS = (os.name == "nt")

#: 这些顶层目录属于“用户数据”，任何情况下都不允许被删除（--prune 也要避开）
PROTECTED_TOP_DIRS = {
    "config", "cache", "debug", "data", "_maaresource", "logs", "log",
    "newversionextract", "_backup", "_cache",
}

# ----------------------------------------------------------------------------
# 输出
# ----------------------------------------------------------------------------

def _init_console():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_init_console()


def log(msg=""):
    sys.stdout.write(str(msg) + "\n")
    sys.stdout.flush()


def warn(msg):
    log("[!] " + str(msg))


def ok(msg):
    log("[v] " + str(msg))


def die(msg, code=1):
    log("[x] " + str(msg))
    sys.exit(code)


def human(n):
    try:
        n = float(n)
    except Exception:
        return str(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return ("%d %s" % (int(n), u)) if u == "B" else ("%.2f %s" % (n, u))
        n /= 1024.0


def short(url, n=88):
    return url if len(url) <= n else url[: n - 3] + "..."


# ----------------------------------------------------------------------------
# HTTP（显式忽略环境变量代理，行为可预测；需要时可显式传 proxy）
# ----------------------------------------------------------------------------

def _opener(proxy=None):
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))  # 空字典 = 不使用任何代理
    try:
        ctx = ssl.create_default_context()
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
    except Exception:
        handlers.append(urllib.request.HTTPSHandler())
    return urllib.request.build_opener(*handlers)


def http_get(url, timeout=DEFAULT_TIMEOUT, proxy=None, headers=None):
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with _opener(proxy).open(req, timeout=timeout) as r:
        return r.read()


def http_get_json(url, timeout=DEFAULT_TIMEOUT, proxy=None):
    return json.loads(http_get(url, timeout=timeout, proxy=proxy).decode("utf-8"))


def _open_stream(url, offset, timeout, proxy):
    h = {"User-Agent": UA, "Accept": "*/*"}
    if offset > 0:
        h["Range"] = "bytes=%d-" % offset
    req = urllib.request.Request(url, headers=h)
    return _opener(proxy).open(req, timeout=timeout)


# ----------------------------------------------------------------------------
# 下载（断点续传 + 多候选通道 + 重试）
# ----------------------------------------------------------------------------

def download(urls, dest, expected_size=None, timeout=90, proxy=None,
             retries=3, retry_wait=None):
    """把 urls 按顺序尝试下载到 dest；支持 .part 断点续传。

    只有成功且大小与 expected_size 一致时才把 .part 改名为 dest。
    全部失败则 die()。
    """
    if isinstance(urls, str):
        urls = [urls]
    part = dest + ".part"
    d = os.path.dirname(os.path.abspath(dest))
    if d:
        os.makedirs(d, exist_ok=True)

    if expected_size and os.path.exists(dest) and os.path.getsize(dest) == expected_size:
        ok("已存在完整缓存：%s" % human(expected_size))
        return dest

    last_err = None
    for idx, u in enumerate(urls):
        tag = "镜像" if idx == 0 and len(urls) > 1 else ("直连" if len(urls) > 1 else "下载")
        for attempt in range(1, retries + 1):
            try:
                have = os.path.getsize(part) if os.path.exists(part) else 0
                if expected_size and have > expected_size:
                    os.remove(part)
                    have = 0
                if expected_size and have == expected_size:
                    break
                log("  [%s %d/%d] %s" % (tag, attempt, retries, short(u)))
                if have:
                    log("  续传自 %s / %s" % (human(have), human(expected_size) if expected_size else "?"))
                r = _open_stream(u, have, timeout, proxy)
                code = getattr(r, "status", 200) or 200
                if have and code != 206:
                    # 服务器不支持断点续传 -> 从头来
                    r.close()
                    r = _open_stream(u, 0, timeout, proxy)
                    code = getattr(r, "status", 200) or 200
                    have = 0
                mode = "ab" if have else "wb"
                t0 = time.time()
                done = have
                shown = 0
                with open(part, mode) as f:
                    while True:
                        b = r.read(262144)
                        if not b:
                            break
                        f.write(b)
                        done += len(b)
                        if expected_size and done - shown >= (1 << 20):
                            shown = done
                            el = max(time.time() - t0, 1e-3)
                            spd = (done - have) / el
                            sys.stdout.write("\r  %5.1f%%  %s / %s  %s/s      " % (
                                done * 100.0 / expected_size, human(done),
                                human(expected_size), human(spd)))
                            sys.stdout.flush()
                r.close()
                sys.stdout.write("\r" + " " * 72 + "\r")
                sys.stdout.flush()
                got = os.path.getsize(part)
                if expected_size and got != expected_size:
                    raise IOError("大小不符：实收 %d，应为 %d" % (got, expected_size))
                os.replace(part, dest)
                ok("下载完成：%s（%.1fs）" % (human(got), time.time() - t0))
                return dest
            except Exception as e:  # noqa: BLE001
                last_err = e
                sys.stdout.write("\r" + " " * 72 + "\r")
                warn("失败：%s" % e)
                if attempt < retries:
                    time.sleep(retry_wait if retry_wait is not None else min(2 ** attempt, 8))
        warn("该通道不可用，切换下一个…")
    die("下载失败（已尝试 %d 个通道）：%s" % (len(urls), last_err))


# ----------------------------------------------------------------------------
# 校验
# ----------------------------------------------------------------------------

def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def verify_sha256(path, digest):
    """digest 形如 'sha256:xxxx' 或纯 hex。返回 (ok, actual)。"""
    expected = (digest or "").split(":", 1)[-1].strip().lower()
    if not expected:
        return None, None
    actual = sha256_file(path).lower()
    return actual == expected, actual


# ----------------------------------------------------------------------------
# GitHub / MAA 版本接口
# ----------------------------------------------------------------------------

def github_release(repo, tag=None, timeout=DEFAULT_TIMEOUT, proxy=None):
    """repo 形如 'MaaEnd/MaaEnd'。tag 为空则取 latest。"""
    if tag:
        url = "https://api.github.com/repos/%s/releases/tags/%s" % (repo, tag)
    else:
        url = "https://api.github.com/repos/%s/releases/latest" % repo
    return http_get_json(url, timeout=timeout, proxy=proxy)


def release_digests(release):
    """{asset_name: 'sha256:hex'}"""
    out = {}
    for a in release.get("assets", []) or []:
        if a.get("name") and a.get("digest"):
            out[a["name"]] = a["digest"]
    return out


MAA_SUMMARY_URL = "https://api.maa.plus/MaaAssistantArknights/api/version/summary.json"


def maa_latest(channel="stable", timeout=DEFAULT_TIMEOUT, proxy=None):
    """返回 (version, detail_json)。stable.json 的 details.assets 是资产列表。"""
    summary = http_get_json(MAA_SUMMARY_URL, timeout=timeout, proxy=proxy)
    ch = summary.get(channel)
    if not ch:
        die("MAA 版本接口未返回 %s 频道" % channel)
    detail = http_get_json(ch["detail"], timeout=timeout, proxy=proxy)
    return ch.get("version") or detail.get("version"), detail


def norm_ver(v):
    """统一加 v 前缀，去空白。"""
    v = (v or "").strip()
    if v and not v.startswith("v"):
        v = "v" + v
    return v


# ----------------------------------------------------------------------------
# ZIP 安全解压
# ----------------------------------------------------------------------------

def safe_extractall(zf, dest):
    base = os.path.abspath(dest)
    members = zf.namelist()
    for name in members:
        tgt = os.path.abspath(os.path.join(base, name.replace("\\", "/")))
        if not (tgt == base or tgt.startswith(base + os.sep)):
            raise RuntimeError("压缩包内含越界路径，已中止：%s" % name)
    zf.extractall(base)
    return len(members)


def zip_file_names(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        return [n for n in zf.namelist() if not n.endswith("/")]


# ----------------------------------------------------------------------------
# 备份
# ----------------------------------------------------------------------------

def backup_paths(rel_paths, install_dir, backup_dir):
    """把 install_dir 中存在的 rel_paths 复制到 backup_dir（保持相对结构）。返回 (数量, 字节数)。"""
    n = 0
    total = 0
    seen = set()
    for rel in rel_paths:
        rel = rel.replace("\\", "/").lstrip("/")
        if not rel or rel in seen:
            continue
        seen.add(rel)
        src = os.path.join(install_dir, rel.replace("/", os.sep))
        if not os.path.isfile(src):
            continue
        dst = os.path.join(backup_dir, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        total += os.path.getsize(src)
        n += 1
    return n, total


def backup_size_estimate(rel_paths, install_dir):
    total = 0
    for rel in rel_paths:
        src = os.path.join(install_dir, rel.replace("/", os.sep))
        if os.path.isfile(src):
            total += os.path.getsize(src)
    return total


# ----------------------------------------------------------------------------
# 进程 / 版本 / 目录探测
# ----------------------------------------------------------------------------

def process_running(exe_name):
    """用 tasklist 判断进程是否在跑。全程按字节比较，避免代码页解码问题。"""
    if not IS_WINDOWS:
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq %s" % exe_name, "/NH", "/FO", "CSV"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=25,
        )
        raw = (out.stdout or b"").lower()
        return exe_name.lower().encode("ascii", "ignore") in raw
    except Exception:
        warn("无法确认 %s 是否在运行（tasklist 调用失败），将按“未运行”继续" % exe_name)
        return False


def autodetect_dir(root, pattern, marker):
    """在 root 下按 glob 找含 marker 文件的目录（取名字最大的一个）。"""
    hits = []
    for d in glob.glob(os.path.join(root, pattern)):
        if os.path.isdir(d) and os.path.isfile(os.path.join(d, marker)):
            hits.append(d)
    if not hits:
        return None
    hits.sort()
    return hits[-1]


def pe_file_version(path):
    """用 Windows API 读取 PE 的 FileVersion（如 '6.19.0'）。失败返回 ''。"""
    if not IS_WINDOWS:
        return ""
    try:
        from ctypes import wintypes
        ver = ctypes.WinDLL("version")
        ver.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        ver.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        ver.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        ver.GetFileVersionInfoW.restype = wintypes.BOOL
        ver.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR,
                                       ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
        ver.VerQueryValueW.restype = wintypes.BOOL

        size = ver.GetFileVersionInfoSizeW(path, None)
        if not size:
            return ""
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(path, 0, size, buf):
            return ""

        def query(sub):
            p = ctypes.c_void_p()
            ln = wintypes.UINT()
            if ver.VerQueryValueW(buf, sub, ctypes.byref(p), ctypes.byref(ln)) and p:
                # 长度单位在文档中有歧义（字符 vs 字节）：限定读取上限，再按首个 NUL 截断
                n = int(ln.value) or 512
                s = ctypes.wstring_at(p, min(n, 1024))
                return s.split("\x00", 1)[0].strip()
            return ""

        class LCP(ctypes.Structure):
            _fields_ = [("language", wintypes.WORD), ("codepage", wintypes.WORD)]

        # 从 Translation 表拿 StringFileInfo\FileVersion
        p = ctypes.c_void_p()
        ln = wintypes.UINT()
        if ver.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(p), ctypes.byref(ln)) and p:
            cnt = int(ln.value) // ctypes.sizeof(LCP)
            arr = ctypes.cast(p, ctypes.POINTER(LCP))
            for i in range(cnt):
                lang, cp = arr[i].language, arr[i].codepage
                sub = "\\StringFileInfo\\%04x%04x\\FileVersion" % (lang, cp)
                val = query(sub)
                if val:
                    return val.strip()
        return ""
    except Exception:
        return ""


# ----------------------------------------------------------------------------
# 剪枝（--prune）：仅清理清单外的“程序文件”，绝不触碰用户目录
# ----------------------------------------------------------------------------

def prune_by_filelist(install_dir, filelist_rel, allowed_roots):
    """按新的 filelist.txt 删除多余文件。范围仅限 allowed_roots 下且不在清单中的文件。

    返回删除数量。allowed_roots 为空则不做任何事（安全默认）。
    """
    fl = os.path.join(install_dir, filelist_rel)
    if not os.path.isfile(fl):
        warn("找不到 %s，跳过 --prune" % filelist_rel)
        return 0
    keep = set()
    with open(fl, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip().replace("\\", "/").lstrip("./")
            if line:
                keep.add(line.lower())
    removed = 0
    for root in allowed_roots:
        base = os.path.join(install_dir, root)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirs, files in os.walk(base):
            for fn in files:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, install_dir).replace("\\", "/")
                if rel.lower() not in keep:
                    try:
                        os.remove(full)
                        removed += 1
                    except Exception:
                        pass
    return removed


# ----------------------------------------------------------------------------
# 交互
# ----------------------------------------------------------------------------

def confirm(prompt, assume_yes=False):
    if assume_yes:
        return True
    sys.stdout.write("%s [y/N] " % prompt)
    sys.stdout.flush()
    try:
        return input().strip().lower() in ("y", "yes")
    except EOFError:
        return False
