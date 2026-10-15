# -*- coding: utf-8 -*-
"""ghupdate 配置模块 —— 零第三方依赖（只用标准库）。

优先级（高 -> 低）：CLI 参数 > 环境变量 > config.json > 内置默认值。
每个生效值都记录来源，供 --show-config 排查。

配置文件位置（按序探测，先命中先用）：
  1. --config PATH
  2. 环境变量 GHUPDATE_CONFIG
  3. 脚本目录 ghupdate\\config.json（默认，便携）
  4. 都没有 -> 用内置默认值；写入时在该位置创建
"""

from __future__ import annotations

import copy
import json
import os

CONFIG_FILENAME = "config.json"
ENV_CONFIG = "GHUPDATE_CONFIG"

SOURCE_DEFAULT = "默认"
SOURCE_FILE = "config.json"
SOURCE_ENV = "环境变量"
SOURCE_CLI = "CLI"

#: 内置默认配置。用户配置文件与它做深合并（用户优先）。
DEFAULTS = {
    "version": 1,
    "mirror": {
        # 总开关；关闭则一律直连 GitHub
        "enabled": True,
        # 按顺序尝试。两种写法：
        #   前缀式 "https://ghfast.top/"  -> <前缀><完整 github url>
        #   模板式 "https://x.com/{url}"  -> {url} 替换为完整 github url
        "prefixes": ["https://ghfast.top/"],
        # 镜像全失败后是否再试 GitHub 直连（慢但能通）
        "fallback_direct": True,
    },
    "install": {
        # 空 = 未指定，运行时会询问；填上后永久生效（手动指定，不做自动定位）
        "maa": {"path": ""},
        "maaend": {"path": ""},
    },
    "locate": {
        # 指定目录里没有主程序时，是否只在它的“直接子目录”里探一层并征求确认
        "parent_probe": True,
    },
    "network": {"proxy": "", "timeout": 30, "retries": 3},
    "behavior": {
        "prune": False,
        "restart": False,
        "backup": True,
        "verify": True,
        "keep_residue": False,
    },
    "ui": {"language": "zh-CN"},
}

#: 环境变量 -> (点分路径, 值类型)
ENV_SPECS = (
    ("GHUPDATE_MIRROR", "mirror.prefixes", "list"),
    ("GHUPDATE_PROXY", "network.proxy", "str"),
    ("GHUPDATE_INSTALL_MAA", "install.maa.path", "str"),
    ("GHUPDATE_INSTALL_MAAEND", "install.maaend.path", "str"),
)


class ConfigError(Exception):
    """配置文件无法读取或格式非法。"""


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

def script_dir():
    """ghupdate 目录（本文件位于其 core 子目录下）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_path(explicit=""):
    """返回 (配置文件绝对路径, 是否存在)。explicit 为 --config 的值。"""
    cand = explicit or os.environ.get(ENV_CONFIG, "")
    if cand:
        p = os.path.abspath(os.path.expandvars(os.path.expanduser(cand.strip())))
        return p, os.path.isfile(p)
    p = os.path.join(script_dir(), CONFIG_FILENAME)
    return p, os.path.isfile(p)


# ---------------------------------------------------------------------------
# 合并
# ---------------------------------------------------------------------------

def _mark_defaults(node, sources, prefix=""):
    for key, val in node.items():
        dotted = prefix + key
        if isinstance(val, dict):
            _mark_defaults(val, sources, dotted + ".")
        else:
            sources[dotted] = SOURCE_DEFAULT


def _deep_merge(dst, src, source, sources, prefix=""):
    for key, val in src.items():
        dotted = prefix + key
        if isinstance(val, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], val, source, sources, dotted + ".")
        else:
            dst[key] = copy.deepcopy(val)
            sources[dotted] = source


def leaf_paths(node, prefix=""):
    """展平出所有叶子字段的点分路径。"""
    for key, val in node.items():
        dotted = prefix + key
        if isinstance(val, dict):
            for item in leaf_paths(val, dotted + "."):
                yield item
        else:
            yield dotted


def _coerce(value, kind):
    if kind == "list":
        if isinstance(value, (list, tuple)):
            return [str(x).strip() for x in value if str(x).strip()]
        text = str(value or "")
        for sep in (";", ",", "|"):
            text = text.replace(sep, "\n")
        return [x.strip() for x in text.splitlines() if x.strip()]
    if kind == "bool":
        return str(value).strip().lower() in ("1", "true", "yes", "on", "y")
    return "" if value is None else str(value)


def _apply_env(raw, sources):
    used = []
    for env_name, dotted, kind in ENV_SPECS:
        if env_name not in os.environ:
            continue
        val = _coerce(os.environ.get(env_name), kind)
        if isinstance(val, list) and not val:
            continue
        if not isinstance(val, list) and not val:
            continue
        parts = dotted.split(".")
        node = raw
        for part in parts[:-1]:
            if not isinstance(node.get(part), dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = val
        sources[dotted] = SOURCE_ENV
        used.append(env_name)
    return used


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None
    except (ValueError, OSError) as exc:
        raise ConfigError("配置文件无法解析：%s\n  %s" % (path, exc)) from exc
    if not isinstance(data, dict):
        raise ConfigError("配置文件顶层必须是 JSON 对象：%s" % path)
    bad = [k for k in data if k not in DEFAULTS]
    if bad:
        # 未知字段不致命，保留原样并在 --show-config 里可见
        pass
    return data


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class Config:
    """生效配置。raw 是深合并后的普通 dict，sources 记录每项来源。"""

    def __init__(self, raw, path="", sources=None, exists=False):
        self.raw = raw
        self.path = path
        self.sources = sources or {}
        self.exists = exists

    # ---- 读取 ----
    def get(self, dotted, default=None):
        node = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def source_of(self, dotted):
        return self.sources.get(dotted, SOURCE_DEFAULT)

    # ---- 写入 ----
    def set(self, dotted, value, source=SOURCE_CLI):
        parts = dotted.split(".")
        node = self.raw
        for part in parts[:-1]:
            if not isinstance(node.get(part), dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value
        self.sources[dotted] = source

    def set_install_path(self, kind, path, source=SOURCE_FILE):
        self.set("install.%s.path" % kind, path, source)

    # ---- 便捷属性 ----
    @property
    def mirror_enabled(self):
        return bool(self.get("mirror.enabled", True))

    @property
    def mirror_prefixes(self):
        return [p for p in (self.get("mirror.prefixes") or []) if str(p).strip()]

    @property
    def fallback_direct(self):
        return bool(self.get("mirror.fallback_direct", True))

    @property
    def parent_probe(self):
        return bool(self.get("locate.parent_probe", True))

    @property
    def proxy(self):
        return (self.get("network.proxy") or "").strip()

    def install_path(self, kind):
        return (self.get("install.%s.path" % kind) or "").strip()

    # ---- 持久化 ----
    def save(self):
        """原子写回配置文件。返回是否真的写了。"""
        if not self.path:
            return False
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.raw, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, self.path)
        self.exists = True
        return True


# ---------------------------------------------------------------------------
# 载入 / 展示
# ---------------------------------------------------------------------------

def load(explicit_path=""):
    """载入配置：内置默认 <- config.json <- 环境变量。CLI 覆盖由调用方追加。"""
    path, exists = resolve_path(explicit_path)
    raw = copy.deepcopy(DEFAULTS)
    sources = {}
    _mark_defaults(raw, sources)

    if exists:
        data = _read_json(path)
        if data:
            _deep_merge(raw, data, SOURCE_FILE, sources)

    _apply_env(raw, sources)
    return Config(raw, path, sources, exists)


def _fmt(value):
    if isinstance(value, (list, tuple)):
        return ", ".join(str(x) for x in value) if value else "(空)"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = "" if value is None else str(value)
    return text if text else "(空)"


def format_config(cfg):
    """生成 --show-config 的可读文本。"""
    lines = []
    lines.append("配置文件：%s" % cfg.path)
    lines.append("  状态  ：%s" % ("已读取" if cfg.exists else "不存在（全部使用内置默认值）"))
    lines.append("")
    lines.append("生效项（值  [来源]）：")
    for dotted in leaf_paths(cfg.raw):
        lines.append("  %-26s = %s  [%s]" % (dotted, _fmt(cfg.get(dotted)), cfg.source_of(dotted)))
    lines.append("")
    lines.append("优先级：CLI 参数 > 环境变量 > config.json > 内置默认")
    return "\n".join(lines)


def write_example(path=None):
    """写出 config.json（首次运行自动生成）。返回写入路径。"""
    path = path or os.path.join(script_dir(), CONFIG_FILENAME)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(DEFAULTS, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return path
