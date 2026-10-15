# -*- coding: utf-8 -*-
"""镜像 URL 构造 —— 零第三方依赖。

**默认关闭**。这些「加速站」是第三方反向代理：它能看到你请求的完整 URL，
也有能力替换返回给你的内容。

不同链路的兜底能力不一样，这一点很重要：

  · MAA / MaaEnd 程序本体 —— 有 GitHub 官方 SHA256 摘要，篡改会在校验阶段
    被发现并拒绝写入
  · MAA 资源（update_maa_res）—— 走的是分支归档 `archive/main.zip`，
    **没有官方摘要**。只能做语义校验（包内 version.json 的 last_updated 必须
    等于 mirrorchyan 的版本号）+ CRC32，挡不住同时改写 version.json 与内容的
    镜像站

所以「要不要走镜像」本质上是一个信任判断，本模块不替使用者做这个决定 ——
由 config.json 的 mirror.enabled 控制，默认 false。详见根目录
《安全提醒与免责声明.md》。

2026-10-15 实测：13 个常见 GitHub 加速镜像中只有 ghfast.top 可用；
官方 MAA 元数据里的 67 个 mirrors 全是空数组，三个官方 CDN 均已失效。

注意：这类镜像只能代理 github.com 的下载直链，
**代理不了 api.github.com**（实测 ghfast.top 返回 403）。
所以查版本、取 SHA256 摘要仍然走直连，本模块只管 release 资产下载。
"""

from __future__ import annotations

#: 曾被实测确认可用的镜像（现仅作候选保留；是否启用由 config 决定）
DEFAULT_PREFIXES = ["https://ghfast.top/"]

#: 实测不可用、仅作参考的镜像（需要时可手动加进 config.json）
KNOWN_DEAD_PREFIXES = [
    "https://gh-proxy.com/",          # 403
    "https://ghproxy.net/",           # 超时
    "https://hub.gitmirror.com/",     # DNS 失败
]

#: 社区常见的其他候选。本项目**未实测**，列在这里只是省得你到处找 ——
#: 不代表推荐，也不代表现在仍然可用。用之前请自行判断。
OTHER_CANDIDATES = [
    "https://ghproxy.homeboyc.cn/",
    "https://mirror.ghproxy.com/",
    "https://github.moeyy.xyz/",
    "https://gh.h233.eu.org/",
    "https://githubfast.com/",
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
