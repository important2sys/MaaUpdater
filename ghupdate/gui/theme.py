# -*- coding: utf-8 -*-
"""界面外观：DPI、字体、配色。

Tkinter 的字体字重只有 normal / bold 两档，所以层次靠字号和颜色区分，
不要照搬 Web 的 400/500 分级。

字体选择有实测依据：本机 `SimSun` / `SimHei` 未必存在，而
`Microsoft YaHei UI` 必定存在，因此它排第一顺位。
"""

from __future__ import annotations

import sys

import tkinter.font as tkfont

# ---------------------------------------------------------------------------
# 配色（浅色）
# ---------------------------------------------------------------------------

BG = "#f4f5f7"
CARD_BG = "#ffffff"
BORDER = "#dcdfe4"
TEXT = "#1f2328"
MUTED = "#6b7280"
LOG_BG = "#fbfbfc"

ACCENT = "#2f6fd0"
ACCENT_DARK = "#255ab0"
ACCENT_FG = "#ffffff"

#: 状态 -> (文字色, 底色, 中文标签)
STATUS = {
    "unknown": ("#5f5e5a", "#f1efe8", "未检查"),
    "latest":  ("#27500a", "#eaf3de", "已是最新"),
    "update":  ("#185fa5", "#e6f1fb", "可更新"),
    "running": ("#854f0b", "#faeeda", "进行中"),
    "failed":  ("#a32d2d", "#fcebeb", "失败"),
}

UI_FAMILIES = ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "SimHei", "SimSun")
MONO_FAMILIES = ("Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Courier New")

#: 计划中的窗口尺寸（会按 DPI 缩放）
BASE_W, BASE_H = 780, 660


# ---------------------------------------------------------------------------
# DPI
# ---------------------------------------------------------------------------

def enable_dpi_awareness():
    """声明进程 DPI 感知，避免高 DPI 下窗口被系统位图拉伸而模糊。

    返回缩放比例（1.0 = 96 DPI）。非 Windows 或调用失败时返回 1.0 —— 界面
    仍可用，只是高 DPI 下会略微发虚，不影响功能。
    """
    if sys.platform != "win32":
        return 1.0
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001  老系统没有 shcore
            ctypes.windll.user32.SetProcessDPIAware()
        try:
            return float(ctypes.windll.shcore.GetScaleFactorForDevice(0)) / 100.0
        except Exception:  # noqa: BLE001
            return 1.0
    except Exception:  # noqa: BLE001
        return 1.0


# ---------------------------------------------------------------------------
# 字体
# ---------------------------------------------------------------------------

def _pick(root, candidates, fallback):
    try:
        families = set(tkfont.families(root))
    except Exception:  # noqa: BLE001
        return fallback
    for name in candidates:
        if name in families:
            return name
    return fallback


class Fonts:
    """集中管理字体元组，避免各处写死家族名。"""

    def __init__(self, root):
        self.ui = _pick(root, UI_FAMILIES, "TkDefaultFont")
        self.mono = _pick(root, MONO_FAMILIES, "TkFixedFont")

        self.h1 = (self.ui, 14, "bold")
        self.h2 = (self.ui, 11, "bold")
        self.body = (self.ui, 10)
        self.body_bold = (self.ui, 10, "bold")
        self.small = (self.ui, 9)
        self.badge = (self.ui, 9, "bold")
        self.version = (self.ui, 11)
        self.path = (self.ui, 9)
        self.mono_body = (self.mono, 9)
        self.mono_small = (self.mono, 8)


def apply_ttk_style(root, fonts):
    """给 ttk 控件上色。失败不致命（主题名在不同 Windows 版本有差异）。"""
    from tkinter import ttk

    st = ttk.Style(root)
    try:
        st.theme_use("vista")
    except Exception:  # noqa: BLE001
        pass

    st.configure("TFrame", background=BG)
    st.configure("Card.TFrame", background=CARD_BG)
    st.configure("TLabel", background=BG, foreground=TEXT, font=fonts.body)
    st.configure("Card.TLabel", background=CARD_BG, foreground=TEXT, font=fonts.body)
    st.configure("CardTitle.TLabel", background=CARD_BG, foreground=TEXT, font=fonts.h1)
    st.configure("CardPath.TLabel", background=CARD_BG, foreground=MUTED, font=fonts.path)
    st.configure("CardVer.TLabel", background=CARD_BG, foreground=TEXT, font=fonts.version)
    st.configure("CardRes.TLabel", background=CARD_BG, foreground=MUTED, font=fonts.body)
    st.configure("CardNote.TLabel", background=CARD_BG, foreground=MUTED, font=fonts.small)
    st.configure("PageMuted.TLabel", background=BG, foreground=MUTED, font=fonts.small)
    st.configure("TLabelframe", background=BG)
    st.configure("TLabelframe.Label", background=BG, foreground=TEXT, font=fonts.h2)
    st.configure("TCheckbutton", background=BG, foreground=TEXT, font=fonts.body)
    st.configure("Card.TCheckbutton", background=CARD_BG, foreground=TEXT, font=fonts.body)

    st.configure("TButton", font=fonts.body, padding=(10, 4))
    st.configure("Accent.TButton", font=fonts.body_bold, padding=(10, 4))
    st.configure("Tiny.TButton", font=fonts.small, padding=(6, 1))

    st.configure("TProgressbar", thickness=14)
    return st
