# -*- coding: utf-8 -*-
"""ghupdate 图形界面主窗口（Tkinter，零第三方依赖）。

线程模型（Tkinter 不是线程安全的）：

    主线程（Tk mainloop）
      ├── 渲染窗口、响应点击
      └── after(50ms) 轮询 event_queue → 刷新进度条 / 追加日志 / 弹确认框
              ▲
              │ queue.Queue —— 唯一跨线程通道
              │
    工作线程（daemon）
      └── GuiReporter + update_maa.main(argv) / update_maaend.main(argv)

**铁律**：工作线程只往队列丢事件，绝不触碰任何 widget。

业务逻辑一行没复制 —— 界面调用的就是 CLI 用的那两个 main()，
所以命令行怎么更新，界面就怎么更新。
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_GH = os.path.dirname(_HERE)
if _GH not in sys.path:
    sys.path.insert(0, _GH)

import tkinter as tk
from tkinter import messagebox, ttk

import _common as C
from core import config as cfgmod
from core import events, locate
from gui import reporter as gui_reporter
from gui import settings as gui_settings
from gui import theme

APP_TITLE = "MAA / MaaEnd 更新器"
CRASH_LOG = os.path.join(_GH, "gui-error.log")

#: 日志区保留的最大行数（超出裁掉头部，防止长跑任务把内存吃光）
LOG_MAX_LINES = 5000
#: 每插入这么多行才检查一次长度，避免逐行统计拖慢界面
LOG_TRIM_INTERVAL = 200
#: 队列轮询间隔（毫秒）
POLL_MS = 50

PROGRAMS = (
    ("maa", "MAA", "MAA.exe"),
    ("maaend", "MaaEnd", "MaaEnd.exe"),
)


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _updater(kind):
    """按需导入更新器（导入本身不联网，也不写文件）。"""
    if kind == "maa":
        import update_maa
        return update_maa
    import update_maaend
    return update_maaend


def elide_path(path, width=62):
    """路径太长时中间省略，保留盘符与末级目录名。"""
    path = str(path or "")
    if len(path) <= width:
        return path
    keep = width - 3
    head = keep // 2 + 8
    tail = keep - head
    return path[:head] + "..." + path[-tail:]


def open_folder(path):
    """在资源管理器里打开目录。"""
    try:
        if os.path.isdir(path):
            os.startfile(path)  # noqa: S606
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def log_crash(exc=None):
    """把异常写进 gui-error.log。

    pythonw 启动时没有控制台，stderr 是黑洞 —— 这是排障时唯一的线索，
    所以必须落盘。
    """
    import datetime
    try:
        with open(CRASH_LOG, "a", encoding="utf-8") as fh:
            fh.write("\n===== %s =====\n" % datetime.datetime.now().isoformat(" ", "seconds"))
            fh.write("python: %s\n" % sys.executable)
            fh.write("cwd: %s\n" % os.getcwd())
            if exc is not None:
                fh.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            else:
                fh.write(traceback.format_exc())
    except Exception:  # noqa: BLE001
        pass


class Tooltip:
    """最简单的悬停提示（路径被省略时看全文用）。"""

    def __init__(self, widget, text=""):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def set_text(self, text):
        self.text = text
        if self.tip is not None:
            self._hide()

    def _show(self, _event=None):
        if self.tip is not None or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry("+%d+%d" % (x, y))
            tk.Label(self.tip, text=self.text, bg="#ffffe0", fg=theme.TEXT,
                     relief="solid", borderwidth=1, justify="left",
                     padx=6, pady=3).pack()
        except Exception:  # noqa: BLE001
            self.tip = None

    def _hide(self, _event=None):
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:  # noqa: BLE001
                pass
            self.tip = None


# ---------------------------------------------------------------------------
# 程序卡片
# ---------------------------------------------------------------------------

class ProgramCard:
    """一张程序卡片：名称 / 状态 / 安装目录 / 版本行 / 检查·更新·打开目录。"""

    def __init__(self, parent, app, kind, label, marker):
        self.app = app
        self.kind = kind
        self.label = label
        self.marker = marker
        self.cur = ""
        self.latest = ""

        fonts = app.fonts
        self.frame = ttk.Frame(parent, style="Card.TFrame", padding=14)
        self.frame.columnconfigure(0, weight=1)

        # ---- 第一行：名称 + 状态徽章 ----
        top = ttk.Frame(self.frame, style="Card.TFrame")
        top.grid(row=0, column=0, sticky="we")
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text=label, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        # 徽章用 tk.Label —— ttk.Label 改背景色要配 style，得不偿失
        self.badge = tk.Label(top, text="", font=fonts.badge, padx=8, pady=1)
        self.badge.grid(row=0, column=1, sticky="e")

        # ---- 第二行：安装目录 ----
        self.lbl_path = ttk.Label(self.frame, text="", style="CardPath.TLabel")
        self.lbl_path.grid(row=1, column=0, sticky="we", pady=(6, 0))
        self.tip = Tooltip(self.lbl_path, "")

        # ---- 第三行：版本 ----
        self.lbl_ver = ttk.Label(self.frame, text="", style="CardVer.TLabel")
        self.lbl_ver.grid(row=2, column=0, sticky="w", pady=(4, 0))

        # ---- 第四行：提示文字 ----
        self.lbl_note = ttk.Label(self.frame, text="", style="CardNote.TLabel")
        self.lbl_note.grid(row=3, column=0, sticky="w", pady=(2, 0))

        # ---- 第五行：按钮 ----
        bar = ttk.Frame(self.frame, style="Card.TFrame")
        bar.grid(row=4, column=0, sticky="we", pady=(10, 0))
        bar.columnconfigure(2, weight=1)
        self.btn_check = ttk.Button(bar, text="检查更新", command=lambda: app.start_task(kind, "check"))
        self.btn_check.grid(row=0, column=0)
        self.btn_update = ttk.Button(bar, text="立即更新", style="Accent.TButton",
                                     command=lambda: app.start_task(kind, "update"))
        self.btn_update.grid(row=0, column=1, padx=(6, 0))
        self.btn_open = ttk.Button(bar, text="打开目录", style="Tiny.TButton",
                                   command=self._open_dir)
        self.btn_open.grid(row=0, column=3, sticky="e")

        self.set_status("unknown")
        self.set_install("")
        self._render_versions()

    # -- 状态 ---------------------------------------------------------------

    def set_status(self, status):
        fg, bg, text = theme.STATUS.get(status, theme.STATUS["unknown"])
        self.badge.configure(text=text, fg=fg, bg=bg)

    def set_install(self, path):
        self.path = str(path or "")
        self.lbl_path.configure(text="安装目录：" + (elide_path(self.path) if self.path else "(未指定)"))
        self.tip.set_text(self.path)

    def set_versions(self, cur=None, latest=None):
        if cur is not None:
            self.cur = cur
        if latest is not None:
            self.latest = latest
        self._render_versions()

    def set_note(self, text):
        self.lbl_note.configure(text=str(text or ""))

    def set_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.btn_check.configure(state=state)
        self.btn_update.configure(state=state)

    def _render_versions(self):
        cur = self.cur or "?"
        latest = self.latest or "?"
        self.lbl_ver.configure(text="当前 %s            最新 %s" % (cur, latest))

    def _open_dir(self):
        if not self.path or not open_folder(self.path):
            messagebox.showinfo(APP_TITLE, "这个目录打不开：\n%s" % (self.path or "(未指定)"),
                                parent=self.app.root)


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class App:

    def __init__(self):
        self.scale = theme.enable_dpi_awareness()

        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.configure(bg=theme.BG)
        self.root.minsize(700, 540)
        self.root.geometry("%dx%d" % (int(theme.BASE_W * self.scale),
                                      int(theme.BASE_H * self.scale)))

        self.fonts = theme.Fonts(self.root)
        theme.apply_ttk_style(self.root, self.fonts)

        self.queue = queue.Queue()
        self.busy = False
        self.busy_kind = ""
        self.cards = {}
        self._log_count = 0
        self._log_hidden = False

        self.cfg = cfgmod.load("")
        self.proxy = self.cfg.proxy or None
        self.channel = str(self.cfg.get("channel", "stable") or "stable")

        self._build()
        self._refresh_header()
        self._initial_scan()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.report_callback_exception = self._on_tk_error
        self._poll()

    # -- 构建 ---------------------------------------------------------------

    def _build(self):
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)      # 日志区吸收多余高度

        # 顶部标题
        head = ttk.Frame(root, padding=(14, 12, 14, 4))
        head.grid(row=0, column=0, sticky="we")
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text=APP_TITLE, font=self.fonts.h1).grid(row=0, column=0, sticky="w")
        self.lbl_sub = ttk.Label(head, text="", style="PageMuted.TLabel")
        self.lbl_sub.grid(row=1, column=0, sticky="w", pady=(3, 0))

        # 卡片区
        cards = ttk.Frame(root, padding=(14, 6, 14, 4))
        cards.grid(row=1, column=0, sticky="we")
        cards.columnconfigure(0, weight=1)
        for idx, (kind, label, marker) in enumerate(PROGRAMS):
            card = ProgramCard(cards, self, kind, label, marker)
            card.frame.grid(row=idx, column=0, sticky="we", pady=(0, 8))
            self.cards[kind] = card

        # 进度区
        prog = ttk.Frame(root, padding=(14, 0, 14, 4))
        prog.grid(row=2, column=0, sticky="we")
        prog.columnconfigure(0, weight=1)
        self.pb = ttk.Progressbar(prog, mode="determinate", maximum=1000)
        self.pb.grid(row=0, column=0, sticky="we")
        self.lbl_prog = ttk.Label(prog, text="", style="PageMuted.TLabel")
        self.lbl_prog.grid(row=1, column=0, sticky="w", pady=(3, 0))

        # 日志区（可折叠）
        logbox = ttk.Frame(root, padding=(14, 0, 14, 4))
        logbox.grid(row=3, column=0, sticky="nsew")
        logbox.columnconfigure(0, weight=1)
        logbox.rowconfigure(1, weight=1)
        self.logbox = logbox

        bar = ttk.Frame(logbox)
        bar.grid(row=0, column=0, sticky="we")
        bar.columnconfigure(0, weight=1)
        self.btn_log = ttk.Button(bar, text="收起日志", style="Tiny.TButton",
                                  command=self.toggle_log)
        self.btn_log.grid(row=0, column=0, sticky="w")
        ttk.Button(bar, text="清空", style="Tiny.TButton",
                   command=self.clear_log).grid(row=0, column=1, sticky="e")

        wrap = ttk.Frame(logbox)
        wrap.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        self.log_wrap = wrap

        self.log = tk.Text(wrap, height=9, wrap="none", font=self.fonts.mono_body,
                           bg=theme.LOG_BG, fg=theme.TEXT, relief="flat",
                           highlightthickness=1, highlightbackground=theme.BORDER,
                           state="disabled", padx=6, pady=4)
        self.log.grid(row=0, column=0, sticky="nsew")
        sbar = ttk.Scrollbar(wrap, orient="vertical", command=self.log.yview)
        sbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=sbar.set)

        # 底部
        foot = ttk.Frame(root, padding=(14, 2, 14, 12))
        foot.grid(row=4, column=0, sticky="we")
        foot.columnconfigure(0, weight=1)
        self.lbl_foot = ttk.Label(foot, text="", style="PageMuted.TLabel")
        self.lbl_foot.grid(row=0, column=0, sticky="w")
        ttk.Button(foot, text="查看配置", command=self.show_config).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(foot, text="设置…", command=self.open_settings).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(foot, text="退出", command=self.on_close).grid(row=0, column=3)

    # -- 顶部 / 底部 ---------------------------------------------------------

    def _refresh_header(self):
        if self.cfg.mirror_enabled:
            prefixes = self.cfg.mirror_prefixes
            mir = "镜像 " + (prefixes[0] if prefixes else "(未配置)")
            if len(prefixes) > 1:
                mir += " 等 %d 个" % len(prefixes)
        else:
            mir = "镜像已禁用（直连 GitHub）"
        self.lbl_sub.configure(text="%s        配置：%s" % (mir, self.cfg.path))

    def foot(self, text):
        self.lbl_foot.configure(text=str(text or ""))

    # -- 启动扫描（只读本地，不联网）------------------------------------------

    def _initial_scan(self):
        for kind, _label, _marker in PROGRAMS:
            self._refresh_card(kind)

    def _refresh_card(self, kind):
        card = self.cards[kind]
        install = self.cfg.install_path(kind)
        card.set_install(install)
        card.set_status("unknown")
        card.set_versions(cur="", latest="")
        if not install:
            card.set_note("还没有指定安装目录 —— 点右下角「设置…」选一个")
            return
        good, why = locate.validate(kind, install)
        if not good:
            card.set_note("目录不可用：%s" % why)
            return
        card.set_note("")
        card.set_versions(cur=self.local_version(kind, install))

    @staticmethod
    def local_version(kind, install):
        """读本地当前版本（MAA 读 PE，MaaEnd 读 interface.json）。"""
        try:
            if kind == "maa":
                return C.norm_ver(C.pe_file_version(os.path.join(install, "MAA.exe")))
            import update_maaend
            return C.norm_ver(update_maaend.read_interface_version(install))
        except Exception:  # noqa: BLE001
            return ""

    # -- 任务 ---------------------------------------------------------------

    def start_task(self, kind, mode):
        if self.busy:
            messagebox.showinfo(APP_TITLE, "已有任务在进行，请等它结束。", parent=self.root)
            return
        card = self.cards[kind]
        install = self.cfg.install_path(kind)
        good, why = locate.validate(kind, install)
        if not good:
            messagebox.showwarning(
                APP_TITLE,
                "还没有可用的 %s 安装目录。\n\n当前值：%s\n原因：%s\n\n"
                "请在「设置…」里指定包含 %s 的那个文件夹。"
                % (card.label, install or "(空)", why, card.marker),
                parent=self.root)
            return
        if C.process_running(card.marker):
            messagebox.showwarning(
                APP_TITLE,
                "%s 正在运行。\n\n运行时文件被占用，替换必然失败 —— 请先完全退出 %s 再试。"
                % (card.label, card.label),
                parent=self.root)
            return

        # 更新器需要的参数在这里一次性取好，避免工作线程再去读 self.cfg
        argv = None
        if mode == "update":
            argv = ["--install", install, "--no-save"]
            if kind == "maa":
                argv += ["--channel", self.channel]
        proxy = self.proxy
        channel = self.channel

        self.busy = True
        self.busy_kind = kind
        self._set_buttons(False)
        card.set_status("running")
        card.set_note("正在进行…")
        self.progress_reset()
        self.foot("%s：%s…" % (card.label, "检查更新" if mode == "check" else "开始更新"))

        rep = gui_reporter.GuiReporter(self.queue, kind)
        events.set_reporter(rep)
        threading.Thread(target=self._work, args=(kind, mode, install, argv, proxy, channel),
                         daemon=True).start()

    def _work(self, kind, mode, install, argv, proxy, channel):
        """工作线程入口 —— 只投队列，不碰 widget。"""
        rc, err = 0, ""
        rep = events.get_reporter()
        try:
            if mode == "check":
                self._check_here(kind, install, proxy, channel)
            else:
                rc = _updater(kind).main(argv) or 0
        except events.UpdateError as exc:
            rc, err = exc.code, str(exc)
        except events.UpdateCancelled:
            rc, err = 0, ""
        except Exception as exc:  # noqa: BLE001
            rc, err = 1, "%s: %s" % (type(exc).__name__, exc)
            rep.log(traceback.format_exc())
        finally:
            self.queue.put((kind, "done", mode, rc, err))

    def _check_here(self, kind, install, proxy, channel):
        """轻量检查：只比版本，不下载、不写文件。

        刻意不调用 main(--check) —— 干跑会多跑一遍选包流程，日志噪音大，
        而且判定结果要另外从文本里解析。这里直接复用 core 的探测函数，
        与更新器用的是同一套 norm_ver / 同一批数据源，结论一致。
        """
        rep = events.get_reporter()
        if kind == "maa":
            cur = C.norm_ver(C.pe_file_version(os.path.join(install, "MAA.exe")))
            rep.log("  当前 MAA.exe 版本：%s" % (cur or "(读不到)"))
            rep.log("[检查] 查询 MAA 最新版本（%s 频道）…" % channel)
            latest, _detail = C.maa_latest(channel, proxy=proxy)
            latest = C.norm_ver(latest)
        else:
            import update_maaend
            cur = C.norm_ver(update_maaend.read_interface_version(install))
            rep.log("  当前 interface.json 版本：%s" % (cur or "(读不到)"))
            rep.log("[检查] 查询 GitHub 最新 Release…")
            rel = C.github_release("MaaEnd/MaaEnd", proxy=proxy)
            latest = C.norm_ver(rel.get("tag_name") or "")
        if not latest:
            rep.fail("没能取到最新版本号（网络或镜像问题，可看下方日志）")
        rep.ok("当前 %s  ->  最新 %s" % (cur or "?", latest))
        if cur and cur.lower() == latest.lower():
            rep.ok("已是最新版本。")
        else:
            rep.warn("发现新版本：%s（当前 %s）" % (latest, cur or "未知"))
        self.queue.put((kind, "version", cur, latest))

    # -- 队列 ---------------------------------------------------------------

    def _poll(self):
        try:
            while True:
                self._handle(self.queue.get_nowait())
        except queue.Empty:
            pass
        except Exception as exc:  # noqa: BLE001
            log_crash(exc)
        self.root.after(POLL_MS, self._poll)

    def _handle(self, item):
        kind, ev = item[0], item[1]
        card = self.cards.get(kind)

        if ev == "log":
            self.append_log(item[2])
        elif ev == "stage":
            self.append_log("")
            self.lbl_prog.configure(text="[%d/%d] %s…" % (item[2], item[3], item[4]))
        elif ev == "progress":
            self.show_progress(item[2], item[3], item[4])
        elif ev == "progress_end":
            pass
        elif ev == "confirm":
            self._ask_confirm(item[2], item[3], item[4])
        elif ev == "version":
            if card:
                cur, latest = item[2], item[3]
                card.set_versions(cur=cur, latest=latest)
                same = bool(cur) and bool(latest) and cur.lower() == latest.lower()
                card.set_status("latest" if same else "update")
                card.set_note("已是最新，无需更新" if same else "有新版本可以更新")
        elif ev == "done":
            self._task_done(kind, item[2], item[3], item[4])

    def _ask_confirm(self, prompt, box, done_event):
        """主线程负责弹窗；工作线程在 confirm() 里等 done_event。"""
        try:
            ans = messagebox.askyesno(APP_TITLE, str(prompt).strip(), parent=self.root)
        except Exception:  # noqa: BLE001
            ans = False
        box["value"] = bool(ans)
        done_event.set()

    def _task_done(self, kind, mode, rc, err):
        self.busy = False
        self.busy_kind = ""
        self._set_buttons(True)
        card = self.cards.get(kind)
        name = card.label if card else kind

        if rc == 0:
            if mode == "update" and card:
                card.set_status("latest")
                card.set_versions(latest=card.cur)
                card.set_note("更新流程结束，请核对上方日志")
                self.foot("%s 更新流程结束。" % name)
                messagebox.showinfo(APP_TITLE, "%s 更新流程已结束，结果请看日志区。" % name,
                                    parent=self.root)
            else:
                self.foot("%s 检查完成。" % name)
        else:
            if card:
                card.set_status("failed")
                card.set_note("失败：" + (err or ("退出码 %d" % rc)))
            self.foot("%s 失败（退出码 %d）" % (name, rc))
            messagebox.showerror(APP_TITLE, "%s 执行失败：\n\n%s"
                                 % (name, err or ("退出码 %d，详情见日志" % rc)),
                                 parent=self.root)

    # -- 进度 / 日志 ---------------------------------------------------------

    def progress_reset(self):
        self.pb.configure(value=0)
        self.lbl_prog.configure(text="")

    def show_progress(self, done, total, speed):
        if not total:
            return
        frac = max(0.0, min(float(done) / float(total), 1.0))
        self.pb.configure(value=frac * 1000)
        self.lbl_prog.configure(text="  %.1f%%   %s / %s   %s/s"
                                     % (frac * 100.0, C.human(done), C.human(total), C.human(speed)))

    def append_log(self, text):
        try:
            self.log.configure(state="normal")
            self.log.insert("end", str(text) + "\n")
            self._log_count += 1
            if self._log_count % LOG_TRIM_INTERVAL == 0:
                self._trim_log()
            self.log.see("end")
            self.log.configure(state="disabled")
        except Exception as exc:  # noqa: BLE001
            log_crash(exc)

    def _trim_log(self):
        try:
            lines = int(self.log.index("end-1c").split(".")[0])
            if lines > LOG_MAX_LINES:
                self.log.delete("1.0", "%d.0" % (lines - LOG_MAX_LINES + 1))
        except Exception:  # noqa: BLE001
            pass

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self._log_count = 0

    def toggle_log(self):
        if self._log_hidden:
            self.log_wrap.grid()
            self.btn_log.configure(text="收起日志")
        else:
            self.log_wrap.grid_remove()
            self.btn_log.configure(text="展开日志")
        self._log_hidden = not self._log_hidden

    # -- 设置 / 杂项 ---------------------------------------------------------

    def open_settings(self):
        gui_settings.SettingsDialog(self.root, self.cfg, self.fonts, on_saved=self.on_settings_saved)

    def on_settings_saved(self, cfg):
        self.cfg = cfg
        self.proxy = cfg.proxy or None
        self.channel = str(cfg.get("channel", "stable") or "stable")
        self._refresh_header()
        for kind, _label, _marker in PROGRAMS:
            self._refresh_card(kind)
        self.foot("设置已保存到 %s" % cfg.path)

    def show_config(self):
        try:
            text = cfgmod.format_config(self.cfg)
        except Exception as exc:  # noqa: BLE001
            text = "读取配置失败：%s" % exc
        win = tk.Toplevel(self.root)
        win.title("当前配置")
        win.configure(bg=theme.BG)
        win.transient(self.root)
        win.geometry("+%d+%d" % (self.root.winfo_rootx() + 60, self.root.winfo_rooty() + 60))
        box = tk.Text(win, width=86, height=26, font=self.fonts.mono_body,
                      bg=theme.LOG_BG, fg=theme.TEXT, relief="flat",
                      highlightthickness=1, highlightbackground=theme.BORDER,
                      padx=8, pady=6)
        box.pack(fill="both", expand=True, padx=10, pady=10)
        box.insert("1.0", text)
        box.configure(state="disabled")
        ttk.Button(win, text="关闭", command=win.destroy).pack(pady=(0, 10))

    def _set_buttons(self, enabled):
        for card in self.cards.values():
            card.set_enabled(enabled)

    def _on_tk_error(self, exc, val, tb):
        log_crash(val)
        try:
            messagebox.showerror(APP_TITLE,
                                 "界面出错了：%s\n\n详细信息已写入：\n%s" % (val, CRASH_LOG),
                                 parent=self.root)
        except Exception:  # noqa: BLE001
            pass

    def on_close(self):
        if self.busy:
            if not messagebox.askyesno(
                    APP_TITLE,
                    "任务正在进行中。\n\n"
                    "强制退出会留下未下载完的 .part 文件（下次会自动续传），"
                    "但如果正在解压覆盖，文件可能处于半更新状态。\n\n确定退出吗？",
                    parent=self.root):
                return
        try:
            self.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    # 先把基础事件挂上：pythonw 没有控制台，崩溃信息必须落盘
    sys.excepthook = lambda t, v, tb: (log_crash(v), sys.__excepthook__(t, v, tb))
    try:
        app = App()
    except Exception as exc:  # noqa: BLE001
        log_crash(exc)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(APP_TITLE, "界面启动失败：%s\n\n详见：%s" % (exc, CRASH_LOG))
            root.destroy()
        except Exception:  # noqa: BLE001
            pass
        return 1
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
