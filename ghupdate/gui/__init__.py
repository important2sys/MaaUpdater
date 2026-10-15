# -*- coding: utf-8 -*-
"""ghupdate 图形界面包（Tkinter，零第三方依赖）。

只在带 tkinter 的解释器下可用 —— managed Python 3.13 未编译 Tcl/Tk，
所以 GUI 由 `ghupdate-gui.bat` 挑一个带 tkinter 的解释器启动。
CLI 路径（update_maa / update_maaend / ghupdate）完全不依赖本包。

线程模型见 gui/app.py 顶部说明。
"""
