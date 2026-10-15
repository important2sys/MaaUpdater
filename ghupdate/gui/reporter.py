# -*- coding: utf-8 -*-
"""GUI 侧 Reporter —— 把逻辑事件转成队列消息。

**铁律**：本模块运行在工作线程里，只往 queue 丢数据，绝不触碰任何 widget。
Tkinter 不是线程安全的，所有界面更新一律由主线程轮询队列后执行。
"""

from __future__ import annotations

import threading

from core import events


class GuiReporter(events.Reporter):
    """事件 -> 队列。

    队列元素统一是 ``(kind, event, *args)`` 的元组，kind 用于区分是哪个程序
    卡片发出的事件（同一时刻只跑一个任务，但带上更省心）。
    """

    #: confirm 无响应的等待上限（秒），超时按「取消」处理
    CONFIRM_TIMEOUT = 120.0

    def __init__(self, queue, kind=""):
        self.q = queue
        self.kind = kind

    # -- 内部 ---------------------------------------------------------------

    def _put(self, event, *args):
        self.q.put((self.kind, event) + args)

    # -- 常规 ---------------------------------------------------------------

    def log(self, msg=""):
        self._put("log", str(msg))

    def warn(self, msg):
        self._put("log", "[!] " + str(msg))

    def ok(self, msg):
        self._put("log", "[v] " + str(msg))

    def stage(self, idx, total, name):
        self._put("stage", idx, total, str(name))

    # -- 进度 ---------------------------------------------------------------

    def progress(self, done, total, speed):
        self._put("progress", done, total, speed)

    def progress_end(self):
        self._put("progress_end")

    # -- 交互 ---------------------------------------------------------------

    def confirm(self, prompt, assume_yes=False):
        """把询问交给主线程弹窗，本线程阻塞等待结果。

        Python 的 ``Event.wait`` 走的是原生条件变量，不占 GIL，因此不会
        卡住主线程；主线程照常在 ``after`` 循环里跑。
        """
        if assume_yes:
            return True
        box = {}
        done = threading.Event()
        self._put("confirm", str(prompt), box, done)
        if not done.wait(self.CONFIRM_TIMEOUT):
            self._put("log", "[!] 确认超时（%.0f 秒无响应），按取消处理"
                      % self.CONFIRM_TIMEOUT)
            return False
        return bool(box.get("value"))

    # -- 失败 ---------------------------------------------------------------

    def fail(self, msg, code=1):
        self._put("log", "[x] " + str(msg))
        raise events.UpdateError(str(msg), code)
