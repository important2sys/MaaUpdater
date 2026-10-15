# -*- coding: utf-8 -*-
"""事件契约 —— 把「说什么」与「怎么说」分开。

业务逻辑（update_maa / update_maaend）只通过全局 Reporter 产生事件；
具体落到终端还是窗口，由注入的实现决定。CLI 与 GUI 因此可以共用
同一份逻辑代码，输出格式各自负责。
"""

import sys

# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class UpdateError(Exception):
    """致命错误。

    取代原先直接 ``sys.exit()`` 的 ``die()``：改为抛出，由调用方
    （``__main__`` 或 GUI 线程）决定如何上报与退出，便于 GUI 接管。
    """

    def __init__(self, msg, code=1):
        super().__init__(msg)
        self.msg = msg
        self.code = code


class UpdateCancelled(Exception):
    """用户主动取消。不是错误，调用方给单独的退出码。"""


# ---------------------------------------------------------------------------
# 格式化助手
# ---------------------------------------------------------------------------

def human(n):
    """把字节数格式化成人类可读形式（原 _common.human，为避免循环导入移入）。"""
    try:
        n = float(n)
    except Exception:  # noqa: BLE001
        return str(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return ("%d %s" % (int(n), u)) if u == "B" else ("%.2f %s" % (n, u))
        n /= 1024.0


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------

class Reporter:
    """逻辑侧的唯一出口。

    GUI 实现见 ``gui/reporter.py``；只想看事件流的测试替身可直接继承本类
    并只覆盖关心的方法。
    """

    def log(self, msg=""):
        """普通信息。"""
        raise NotImplementedError

    def warn(self, msg):
        """警告（原 ``[!]`` 前缀）。"""
        raise NotImplementedError

    def ok(self, msg):
        """成功（原 ``[v]`` 前缀）。"""
        raise NotImplementedError

    def stage(self, idx, total, name):
        """阶段推进。

        P2 阶段刻意未改动调用点（现有代码把阶段号写死在 log 文本里，
        改动会带来输出差异风险）；此方法供 P3 的 GUI 显示阶段文字用。
        """
        raise NotImplementedError

    def progress(self, done, total, speed):
        """下载进度。高频调用，GUI 侧需做合并渲染。"""
        raise NotImplementedError

    def progress_end(self):
        """清除进度行（终端下是回车覆盖）。"""
        raise NotImplementedError

    def confirm(self, prompt, assume_yes=False):
        """交互确认。assume_yes=True 时必须直接返回 True 而不触碰输入流。"""
        raise NotImplementedError

    def fail(self, msg, code=1):
        """致命错误：统一抛 UpdateError，绝不自己退出进程。"""
        raise UpdateError(msg, code)


class ConsoleReporter(Reporter):
    """终端实现 —— 输出格式与 P1 及以前**逐字符一致**。"""

    #: 进度行清屏宽度（原实现里写死的 72 个空格）
    CLEAR_WIDTH = 72

    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stdout

    # -- 底层 ---------------------------------------------------------------

    def _write(self, s):
        # pythonw 启动时 sys.stdout 可能是 None（无控制台），写进去会抛
        # AttributeError；界面侧的只读扫描偶尔会走到默认 Reporter，必须兜住。
        if self.stream is None:
            return
        self.stream.write(s)

    def _flush(self):
        try:
            self.stream.flush()
        except Exception:  # noqa: BLE001
            pass

    # -- 常规 ---------------------------------------------------------------

    def log(self, msg=""):
        self._write(str(msg) + "\n")
        self._flush()

    def warn(self, msg):
        self.log("[!] " + str(msg))

    def ok(self, msg):
        self.log("[v] " + str(msg))

    def stage(self, idx, total, name):
        self.log("\n[%d/%d] %s…" % (idx, total, name))

    # -- 进度 ---------------------------------------------------------------

    def progress(self, done, total, speed):
        self._write("\r  %5.1f%%  %s / %s  %s/s      " % (
            done * 100.0 / total, human(done), human(total), human(speed)))
        self._flush()

    def progress_end(self):
        self._write("\r" + " " * self.CLEAR_WIDTH + "\r")
        self._flush()

    # -- 交互 ---------------------------------------------------------------

    def confirm(self, prompt, assume_yes=False):
        if assume_yes:
            return True
        self._write("%s [y/N] " % prompt)
        self._flush()
        try:
            return input().strip().lower() in ("y", "yes")
        except EOFError:
            return False

    # -- 失败 ---------------------------------------------------------------

    def fail(self, msg, code=1):
        self.log("[x] " + str(msg))
        raise UpdateError(msg, code)


class SilentReporter(Reporter):
    """什么都不输出，并把 confirm 一律当作“否”。

    用于 ``--check`` 之类的探测场景，或 GUI 里只想拿结果、不要日志的调用。
    """

    def log(self, msg=""):
        pass

    def warn(self, msg):
        pass

    def ok(self, msg):
        pass

    def stage(self, idx, total, name):
        pass

    def progress(self, done, total, speed):
        pass

    def progress_end(self):
        pass

    def confirm(self, prompt, assume_yes=False):
        return bool(assume_yes)


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_DEFAULT = None
_CURRENT = None


def get_reporter():
    """取当前生效的 Reporter（默认 ConsoleReporter）。"""
    global _DEFAULT, _CURRENT
    if _CURRENT is None:
        if _DEFAULT is None:
            _DEFAULT = ConsoleReporter()
        _CURRENT = _DEFAULT
    return _CURRENT


def set_reporter(reporter):
    """替换全局 Reporter，返回被替换掉的那个（便于用完还原）。"""
    global _CURRENT
    old = get_reporter()
    _CURRENT = reporter
    return old
