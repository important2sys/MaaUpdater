# -*- coding: utf-8 -*-
"""设置面板（独立 Toplevel）。

保存**复用 `core/config.py` 的原子写**，不另开一条保存路径 —— 否则界面存的
和命令行读的迟早会不一致。

四个分组对应命令行能配的全部开关：镜像 / 安装目录 / 网络 / 行为。
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_GH = os.path.dirname(_HERE)
if _GH not in sys.path:
    sys.path.insert(0, _GH)

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core import config as cfgmod
from gui import theme

CHANNELS = ("stable", "beta", "alpha")


class SettingsDialog(tk.Toplevel):

    def __init__(self, master, cfg, fonts, on_saved=None):
        super().__init__(master)
        self.cfg = cfg
        self.fonts = fonts
        self.on_saved = on_saved
        self.saved = False

        self.title("设置")
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.transient(master)

        self._make_vars()
        self._build()
        self._load()

        self.grab_set()
        self.focus_set()
        self.bind("<Escape>", lambda _e: self.destroy())

    # -- 变量 ---------------------------------------------------------------

    def _make_vars(self):
        g = self.cfg.get
        b = tk.BooleanVar
        self.var_mirror = b(value=bool(g("mirror.enabled", True)))
        self.var_fallback = b(value=bool(g("mirror.fallback_direct", True)))
        self.var_maa = tk.StringVar(value=self.cfg.install_path("maa"))
        self.var_maaend = tk.StringVar(value=self.cfg.install_path("maaend"))
        self.var_proxy = tk.StringVar(value=str(g("network.proxy") or ""))
        self.var_timeout = tk.StringVar(value=str(g("network.timeout", 30)))
        self.var_retries = tk.StringVar(value=str(g("network.retries", 3)))
        self.var_channel = tk.StringVar(value=str(g("channel", "stable") or "stable"))
        self.var_backup = b(value=bool(g("behavior.backup", True)))
        self.var_verify = b(value=bool(g("behavior.verify", True)))
        self.var_restart = b(value=bool(g("behavior.restart", False)))
        self.var_prune = b(value=bool(g("behavior.prune", False)))
        self.var_residue = b(value=bool(g("behavior.keep_residue", False)))
        self.var_probe = b(value=bool(g("locate.parent_probe", True)))

    # -- 构建 ---------------------------------------------------------------

    def _build(self):
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)

        row = 0
        row = self._group_mirror(body, row)
        row = self._group_dirs(body, row)
        row = self._group_network(body, row)
        row = self._group_behavior(body, row)

        self.lbl_foot = ttk.Label(body, text="配置将写入：%s" % self.cfg.path,
                                  style="PageMuted.TLabel")
        self.lbl_foot.grid(row=row, column=0, sticky="w", pady=(10, 0))
        row += 1

        bar = ttk.Frame(body)
        bar.grid(row=row, column=0, sticky="we", pady=(8, 0))
        bar.columnconfigure(0, weight=1)
        ttk.Button(bar, text="恢复默认值", command=self._reset).grid(row=0, column=0, sticky="w")
        ttk.Button(bar, text="取消", command=self.destroy).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(bar, text="保存", style="Accent.TButton",
                   command=self._save).grid(row=0, column=2)

    def _group_mirror(self, parent, row):
        box = ttk.LabelFrame(parent, text=" 镜像 ", padding=10)
        box.grid(row=row, column=0, sticky="we", pady=(0, 10))
        box.columnconfigure(0, weight=1)

        ttk.Checkbutton(box, text="启用镜像加速（关闭则一律直连 GitHub）",
                        variable=self.var_mirror).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(box, text="镜像全部失败后，回退到 GitHub 直连（很慢，但能兜住）",
                        variable=self.var_fallback).grid(row=1, column=0, sticky="w", pady=(2, 6))

        ttk.Label(box, text="镜像地址（每行一个，按顺序尝试）：",
                  style="PageMuted.TLabel").grid(row=2, column=0, sticky="w")
        self.txt_mirror = tk.Text(box, height=4, width=72, font=self.fonts.mono_body,
                                  bg=theme.LOG_BG, fg=theme.TEXT, relief="flat",
                                  highlightthickness=1, highlightbackground=theme.BORDER,
                                  padx=6, pady=4, wrap="none")
        self.txt_mirror.grid(row=3, column=0, sticky="we", pady=(3, 4))

        ttk.Label(box,
                  text="前缀式：https://ghfast.top/            （地址 = 前缀 + 完整 GitHub 地址）\n"
                       "模板式：https://例子.com/{url}         （{url} 会被替换成完整 GitHub 地址）",
                  style="PageMuted.TLabel", justify="left").grid(row=4, column=0, sticky="w")
        return row + 1

    def _group_dirs(self, parent, row):
        box = ttk.LabelFrame(parent, text=" 安装目录 ", padding=10)
        box.grid(row=row, column=0, sticky="we", pady=(0, 10))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="MAA").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(box, textvariable=self.var_maa, width=62).grid(row=0, column=1, sticky="we")
        ttk.Button(box, text="浏览…", style="Tiny.TButton",
                   command=lambda: self._browse(self.var_maa)).grid(row=0, column=2, padx=(6, 0))

        ttk.Label(box, text="MaaEnd").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        ttk.Entry(box, textvariable=self.var_maaend, width=62).grid(row=1, column=1, sticky="we",
                                                                    pady=(6, 0))
        ttk.Button(box, text="浏览…", style="Tiny.TButton",
                   command=lambda: self._browse(self.var_maaend)).grid(row=1, column=2,
                                                                       padx=(6, 0), pady=(6, 0))
        ttk.Label(box, text="填包含 MAA.exe / MaaEnd.exe 的那个文件夹；也可以直接填 exe 路径。",
                  style="PageMuted.TLabel").grid(row=2, column=0, columnspan=3, sticky="w",
                                                 pady=(6, 0))
        return row + 1

    def _group_network(self, parent, row):
        box = ttk.LabelFrame(parent, text=" 网络 ", padding=10)
        box.grid(row=row, column=0, sticky="we", pady=(0, 10))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="代理").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(box, textvariable=self.var_proxy).grid(row=0, column=1, columnspan=3, sticky="we")
        ttk.Label(box, text="留空 = 直连；形如 http://127.0.0.1:7890",
                  style="PageMuted.TLabel").grid(row=1, column=1, columnspan=3, sticky="w")

        ttk.Label(box, text="超时").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        ttk.Spinbox(box, from_=5, to=600, width=6, textvariable=self.var_timeout).grid(
            row=2, column=1, sticky="w", pady=(6, 0))
        ttk.Label(box, text="秒").grid(row=2, column=2, sticky="w", padx=(4, 16), pady=(6, 0))
        ttk.Label(box, text="重试").grid(row=2, column=3, sticky="e", padx=(0, 8), pady=(6, 0))
        ttk.Spinbox(box, from_=0, to=10, width=6, textvariable=self.var_retries).grid(
            row=2, column=4, sticky="w", pady=(6, 0))
        ttk.Label(box, text="次").grid(row=2, column=5, sticky="w", padx=(4, 0), pady=(6, 0))

        ttk.Label(box, text="更新通道").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        ttk.Combobox(box, values=CHANNELS, state="readonly", width=10,
                     textvariable=self.var_channel).grid(row=3, column=1, sticky="w", pady=(6, 0))
        ttk.Label(box, text="仅对 MAA 生效（stable / beta / alpha）",
                  style="PageMuted.TLabel").grid(row=3, column=2, columnspan=4, sticky="w",
                                                 padx=(8, 0), pady=(6, 0))
        return row + 1

    def _group_behavior(self, parent, row):
        box = ttk.LabelFrame(parent, text=" 行为 ", padding=10)
        box.grid(row=row, column=0, sticky="we")
        box.columnconfigure(0, weight=1)
        box.columnconfigure(1, weight=1)

        items = (
            (0, 0, "更新前自动备份（可回滚）", self.var_backup),
            (0, 1, "校验 SHA256（无官方摘要时中止）", self.var_verify),
            (1, 0, "更新完成后自动启动程序", self.var_restart),
            (1, 1, "按 filelist 清理废弃程序文件", self.var_prune),
            (2, 0, "保留 cache\\*.downloading 残骸", self.var_residue),
            (2, 1, "目录填错时，在直接子目录里找一层", self.var_probe),
        )
        for r, c, text, var in items:
            ttk.Checkbutton(box, text=text, variable=var).grid(
                row=r, column=c, sticky="w", pady=(0 if r == 0 else 3, 0), padx=(0, 20))
        return row + 1

    # -- 载入 / 保存 ---------------------------------------------------------

    def _load(self):
        prefixes = self.cfg.mirror_prefixes or cfgmod.DEFAULTS["mirror"]["prefixes"]
        self.txt_mirror.delete("1.0", "end")
        self.txt_mirror.insert("1.0", "\n".join(prefixes))

    def _browse(self, var):
        cur = (var.get() or "").strip()
        if not os.path.isdir(cur):
            cur = None
        chosen = filedialog.askdirectory(parent=self, initialdir=cur,
                                         title="选择安装目录", mustexist=False)
        if chosen:
            var.set(os.path.normpath(chosen))

    @staticmethod
    def _int(text, default):
        try:
            return max(0, int(str(text).strip()))
        except (TypeError, ValueError):
            return default

    def _save(self):
        cfg = self.cfg
        src = cfgmod.SOURCE_FILE
        prefixes = [ln.strip() for ln in
                    self.txt_mirror.get("1.0", "end").splitlines() if ln.strip()]

        cfg.set("mirror.enabled", bool(self.var_mirror.get()), src)
        cfg.set("mirror.fallback_direct", bool(self.var_fallback.get()), src)
        cfg.set("mirror.prefixes", prefixes, src)
        cfg.set("install.maa.path", self.var_maa.get().strip(), src)
        cfg.set("install.maaend.path", self.var_maaend.get().strip(), src)
        cfg.set("network.proxy", self.var_proxy.get().strip(), src)
        cfg.set("network.timeout", self._int(self.var_timeout.get(), 30), src)
        cfg.set("network.retries", self._int(self.var_retries.get(), 3), src)
        cfg.set("channel", self.var_channel.get() or "stable", src)
        cfg.set("behavior.backup", bool(self.var_backup.get()), src)
        cfg.set("behavior.verify", bool(self.var_verify.get()), src)
        cfg.set("behavior.restart", bool(self.var_restart.get()), src)
        cfg.set("behavior.prune", bool(self.var_prune.get()), src)
        cfg.set("behavior.keep_residue", bool(self.var_residue.get()), src)
        cfg.set("locate.parent_probe", bool(self.var_probe.get()), src)

        try:
            cfg.save()
        except OSError as exc:
            messagebox.showerror("保存失败", "写入配置失败：\n%s" % exc, parent=self)
            return
        self.saved = True
        if self.on_saved:
            self.on_saved(cfg)
        self.destroy()

    def _reset(self):
        d = cfgmod.DEFAULTS
        self.var_mirror.set(bool(d["mirror"]["enabled"]))
        self.var_fallback.set(bool(d["mirror"]["fallback_direct"]))
        self.txt_mirror.delete("1.0", "end")
        self.txt_mirror.insert("1.0", "\n".join(d["mirror"]["prefixes"]))
        self.var_proxy.set(str(d["network"]["proxy"]))
        self.var_timeout.set(str(d["network"]["timeout"]))
        self.var_retries.set(str(d["network"]["retries"]))
        self.var_channel.set(str(d["channel"]))
        self.var_backup.set(bool(d["behavior"]["backup"]))
        self.var_verify.set(bool(d["behavior"]["verify"]))
        self.var_restart.set(bool(d["behavior"]["restart"]))
        self.var_prune.set(bool(d["behavior"]["prune"]))
        self.var_residue.set(bool(d["behavior"]["keep_residue"]))
        self.var_probe.set(bool(d["locate"]["parent_probe"]))
        # 安装目录不在默认值里（默认是空），不动它，避免误清用户填好的路径
        self.lbl_foot.configure(text="已恢复为内置默认值（安装目录保持不变，尚未保存）")
