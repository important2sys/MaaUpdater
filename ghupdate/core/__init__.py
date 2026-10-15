# -*- coding: utf-8 -*-
"""ghupdate 核心模块 —— 与界面无关、不依赖任何第三方库。

- config.py  配置加载 / 深合并 / 字段级来源追踪 / 原子保存
- locate.py  安装目录解析与校验（手动指定，绝不自动探测）
- mirror.py  镜像候选构造（前缀式 / 模板式 / 直连兜底）
- events.py  事件契约（Reporter），CLI 与 GUI 的公共出口

关于范围：P2 只做了**事件解耦** —— 把 log / die / confirm / 进度输出
从硬编码 stdout 改为可注入的 Reporter，使 GUI 能接管输出与交互。

网络、校验、解压、备份等逻辑仍留在上一层的 ``_common.py``：它们已经被
同一套 Reporter 覆盖，再搬进 core 只是形式上的整齐，收益低于改动风险。
真正的分层界线是「是否依赖界面」，而不是「文件放在哪个目录」。
"""
