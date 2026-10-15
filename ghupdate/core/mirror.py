# -*- coding: utf-8 -*-
"""镜像 URL 构造 —— 零第三方依赖。

2026-10-15 实测：13 个常见 GitHub 加速镜像中只有 ghfast.top 可用；
官方 MAA 元数据里的 67 个 mirrors 全是空数组，三个官方 CDN 均已失效。

注意：这类镜像只能代理 github.com 的下载直链，
**代理不了 api.github.com**（实测 ghfast.top 返回 403）。
所以查版本、取 SHA256 摘要仍然走直连，本模块只管 release 资产下载。
"""

from __future__ import annotations

#: 可用性经实测确认的默认镜像（按优先级）
DEFAULT_PREFIXES = ["https://ghfast.top/"]

#: 实测不可用、仅作参考的镜像（默认不启用，需要时可手动加进 config.json）
KNOWN_DEAD_PREFIXES = [
    "https://gh-proxy.com/",          # 403
    "https://ghproxy.net/",           # 超时
    "https://hub.gitmirror.com/",     # DNS 失败
]


def build_urls(origin, prefixes=None, enabled=True, fallback_direct=True):
    """把单个 GitHub 直链展开成按序尝试的候选列表。

    前缀式（不含 {url}）拼成 <prefix><origin>；
    模板式（含 {url}）把 {url} 替换为 origin。
    最后一并追加直连（fallback_direct 为真，或镜像一个都没给出时）。
    """
    urls = []
    if enabled:
        for raw in (prefixes or []):
            prefix = str(raw or "").strip()
            if not prefix:
                continue
            if "{url}" in prefix:
                url = prefix.replace("{url}", origin)
            else:
                url = prefix.rstrip("/") + "/" + origin
            if url not in urls:
                urls.append(url)
    if (fallback_direct or not urls) and origin not in urls:
        urls.append(origin)
    return urls


def describe(urls):
    """给日志用的一句话说明。"""
    if len(urls) <= 1:
        return "直连 GitHub"
    return "镜像优先（%d 个候选），直连兜底" % (len(urls) - 1)
