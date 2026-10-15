# ghupdate 可视化界面（GUI）开发规划

> 版本：**v3**（2026-10-15 15:20）
> 前置：P1（镜像可配置化 + 安装目录手动指定）**已交付**（`e2307d1`）
> P2（事件解耦）**已交付**（`79a3768`）；P2 后修复了 `locate.resolve()` 静默回退
> 缺陷（附录 B.4）。
> 涉及代码：`D:\RRL\MaaUpdaterBat\ghupdate\`
> 状态：**P3 已完成**（界面可用，附录 C 为实施记录）；剩余 P4 打磨。
> 用户拍板的四项：单页卡片式 / 启动器按能力探测解释器 / 设置项全部搬进界面 /
> 一次做到能更新。

---

## 0. 一句话摘要

现有 `ghupdate` 是一套**线性脚本**：靠 `print` 输出、靠 `input()` 确认、靠 `sys.exit()` 报错。
GUI 无法直接把 `print` 塞进窗口 —— 所以界面开发必须**先做一次事件解耦（P2）**，
再在其上叠界面（P3）。好消息是：**业务逻辑零改动即可复用**（已实测，见 §1.3）。

---

## 1. 技术前提（已实测，非推测）

### 1.1 解释器与 tkinter

| 解释器 | 版本 | tkinter | `pythonw.exe` | 结论 |
|---|---|---|---|---|
| managed（CLI 现用） | 3.13.12 | **✗ 无**（无 `tcl/` 目录） | ✓ | **不能跑 GUI** |
| **系统 Python** | 3.14.6 | **✓ Tk 8.6** | ✓ | **GUI 首选** |
| uv 安装的 Python | 3.12.15 | ✓ Tk 8.6 | — | 备用候选 |

> managed 3.13 只装了纯运行库，没有 Tcl/Tk，`import tkinter` 直接 `ModuleNotFoundError`。
> 系统 Python 位于 `C:\Users\33974\AppData\Local\Programs\Python\Python314\`，含完整 `tcl\tk8.6`。

### 1.2 中文字体

实测可用：`Microsoft YaHei UI` ✓、`Segoe UI` ✓（共 388 个字族）。
`SimSun` / `SimHei` 缺失 —— **界面字体统一用 `Microsoft YaHei UI`**，日志区用等宽（`Consolas`）。

### 1.3 core 逻辑的跨解释器兼容性（关键结论）

用系统 Python 3.14 实跑现有代码，**全部通过**：

```
3.14 COMPILE_OK          # 8 个模块全部编译通过
3.12 COMPILE_OK          # uv 的 3.12 也通过
--show-config            # 配置读取 + 来源追踪，输出正常
update_maa.py --check    # 读出版本 v6.19.0，"已是最新"，全链路正常
update_maaend.py --check # 读出版本 v2.32.0，"已是最新"，全链路正常
```

**结论：`core/` 与两个更新器的业务逻辑，可以零改动跑在带 tkinter 的 3.14 上。**
GUI 不需要复制一份逻辑，也不需要迁就解释器差异。

### 1.4 硬约束

- **PyPI 不可达**（沙箱代理拦截）→ 不能装 PyQt / PySide / 任何第三方 GUI 库
- → **Tkinter 是唯一可选框架**，且"零第三方依赖"必须保持
- **不能打包单 exe**（PyInstaller 装不上）→ 交付形态只能是「`.bat` 启动脚本 + 源码」

---

## 2. 为什么必须先做 P2 解耦

现有代码里，有 **4 类副作用**把逻辑死死绑在终端上：

| 位置 | 现状 | GUI 下会怎样 |
|---|---|---|
| `_common.py:68-79` `log/warn/ok` | 直接 `sys.stdout.write` | 输出进黑洞（pythonw 无控制台） |
| `_common.py:81-83` `die` | 直接 `sys.exit(code)` | 主线程被 `SystemExit` 打死 |
| `_common.py:199-205` `download` 进度 | `\r` 覆盖式写 stdout | 进度条无法渲染 |
| `_common.py:598-606` `confirm` | `input()` | pythonw 下无 stdin，直接崩 |

另一个隐性阻塞：`update_maa.py:97` 的 `ap.parse_args()` **读的是全局 `sys.argv`** ——
GUI 调用 `main()` 时无法注入参数。

> **P2 的目标：把「说什么」和「怎么说」分开。**
> 逻辑只负责产生事件，具体是画到终端还是画到窗口，由注入的 Reporter 决定。

---

## 3. P2 设计：事件解耦

### 3.1 新增 `core/events.py`

```python
class Reporter:
    """逻辑侧唯一出口。CLI 与 GUI 各实现一份。"""
    def log(self, msg=""): ...                 # 普通信息
    def warn(self, msg): ...                   # [!] 警告
    def ok(self, msg): ...                     # [v] 成功
    def stage(self, idx, total, name): ...     # [3/6] 阶段推进
    def progress(self, done, total, speed): ...# 下载进度（高频）
    def progress_end(self): ...                # 清掉进度行
    def confirm(self, prompt) -> bool: ...     # 询问
    def fail(self, msg) -> NoReturn: ...       # 致命——抛 UpdateError

class ConsoleReporter(Reporter):   # 逐字符复刻现有输出，CLI 行为不变
class UpdateError(Exception): ...  # 替代 die()
class UpdateCancelled(Exception): ... # 用户取消（不再当错误）
```

### 3.2 转发层（保证 CLI 输出零变化）

`_common.py` 里既有函数变成薄壳：

```python
_REPORTER = ConsoleReporter()

def set_reporter(r):  global _REPORTER; _REPORTER = r; return _REPORTER

def log(msg=""):  _REPORTER.log(msg)
def warn(msg):    _REPORTER.warn(msg)
def ok(msg):      _REPORTER.ok(msg)
def die(msg, code=1): _REPORTER.fail(msg, code)     # 抛 UpdateError
def confirm(prompt, assume_yes=False): return _REPORTER.confirm(prompt, assume_yes)
```

**验收硬指标**：改造后跑一遍 `update-all.bat check`，
用 `diff` 对比改造前后的 stdout —— **必须逐字节一致**。这是防止"重构把 CLI 改坏"的唯一可靠手段。

### 3.3 参数注入

`main()` 加一个默认参数，不破坏现有调用：

```python
def main(argv=None):
    args = ap.parse_args(argv)   # 原来是无参调用
```

上层 `if __name__ == "__main__": sys.exit(main())` **保持不变**。

> 更彻底的 `JobSpec` dataclass 重构**不在 P2 范围**。理由：`argv` 注入已够 GUI 用，
> 而 dataclass 化会波及两个更新器的全部参数读取点，收益与风险不成比例。若有需要，P4 再说。

### 3.4 `download()` 的进度改走 Reporter

原实现把进度内联写在下载循环里：

```python
sys.stdout.write("\r  %5.1f%%  %s / %s  %s/s      " % (...))
sys.stdout.flush()
```

**实施时改为统一走 Reporter**，而不是额外加一个 `progress_cb` 参数：

```python
_events.get_reporter().progress(done, expected_size, spd)   # 每 1 MiB 一次的节流不变
```

理由：进度本来就是一类事件，走同一条通道即可 —— CLI 落到终端、GUI 落到队列，
不需要第二套机制。`download()` 的**公开签名因此完全没变**，调用方零改动。

---

## 4. GUI 架构

### 4.1 线程模型（Tkinter 不是线程安全的）

```
主线程（Tk mainloop）
  ├── 渲染窗口、响应点击
  └── after(50ms) 轮询 event_queue → 更新进度条 / 追加日志
          ▲
          │ queue.Queue（唯一跨线程通道）
          │
工作线程（daemon）
  └── GuiReporter + 调用 update_maa.main(argv) / update_maaend.main(argv)
```

**铁律**：工作线程**只往队列丢事件**，绝不碰任何 widget。

### 4.2 跨线程的模态确认

`die` 好办（抛异常），`confirm` 难 —— 工作线程需要弹窗，但弹窗必须在主线程。
解法：工作线程投递 `("confirm", prompt, result_box, done_event)` 后 `done_event.wait()` 阻塞；
主线程收到后弹 `messagebox.askyesno`，写回 `result_box`，再 `done_event.set()`。
超时（如 120s 无响应）按"取消"处理。

### 4.3 目录结构

```
ghupdate/
  core/
    events.py        # P2 新增：Reporter 契约 + ConsoleReporter + 异常
    config.py        # 已有
    locate.py        # 已有
    mirror.py        # 已有
  gui/
    __init__.py
    app.py           # 主窗口
    reporter.py      # GuiReporter（队列桥接）
    settings.py      # 设置面板
    theme.py         # 字体 / DPI / 配色
  ghupdate-gui.bat   # 启动器（挑解释器 + pythonw）
```

---

## 5. 界面设计

### 5.1 主窗口（单页卡片式，约 760 × 620）

- **顶部**：标题 + 当前镜像 + 配置路径（一行灰字）
- **中部**：两张程序卡片（MAA / MaaEnd），每张含

  | 元素 | 说明 |
  |---|---|
  | 名称 + 状态徽章 | 未检查 / 已是最新 / 可更新 / 更新中 / 失败 |
  | 安装目录 | 路径过长时中间省略，悬停显示全文 |
  | 版本行 | `当前 v6.19.0  →  最新 v6.19.0` |
  | 按钮 | `[检查]` `[更新]`（更新中禁用，变成 `[取消]`） |

- **进度区**：进度条 + `45.2%  132.5 MB / 293.1 MB  3.27 MB/s` + 阶段文字
- **日志区**：可折叠只读文本框，等宽字体，上限 5000 行（超出裁头部）
- **底部**：`[设置]` `[打开安装目录]` `[退出]`

**交互流程**：点`[检查]` → 后台跑 `--check` → 徽章翻成「可更新」→ 点`[更新]` → 进度条走 → 完成弹提示。

### 5.2 设置面板（独立 Toplevel）

| 分组 | 控件 |
|---|---|
| 镜像 | 多行文本框，每行一个地址（支持 `{url}` 模板）；`启用镜像` / `直连兜底` 开关 |
| 安装目录 | 两行（MAA / MaaEnd），各带 `[浏览…]`，用 `filedialog.askdirectory` |
| 网络 | 代理输入框、超时、重试次数 |
| 行为 | 备份 / 校验 / 更新后重启 / 清理废弃文件 四个开关 |

保存走现有 `core/config.py` 的原子写，**不做第二条保存路径**。

---

## 6. 启动器与解释器策略

`ghupdate-gui.bat` 按序探测，**谁带 tkinter 用谁**（能力探测，不写死版本）：

```
1. %MAAUPD_PYTHON%                        ← 环境变量（用户强制指定）
2. py -3.14  /  py -3                     ← launcher
3. %LOCALAPPDATA%\Programs\Python\Python3*\pythonw.exe
4. %APPDATA%\uv\python\cpython-*\pythonw.exe
            ↓ 逐个试 `-c "import tkinter"`
5. 全都不行 → 弹窗提示"未找到带 tkinter 的 Python"，并打印探测过的路径
```

用 `pythonw.exe` 启动 → **无黑色控制台窗口**。另外配一个 `ghupdate-gui-debug.bat`
用 `python.exe` 启动（保留控制台看 traceback），排障用。

**为什么写死 `Python3*` 通配而不写死 3.14**：将来 managed 运行时若补上 tkinter，
或用户换 Python 版本，启动器都能自适应，不用改脚本。

---

## 7. 分阶段计划

| 阶段 | 内容 | 规模 | 出口条件 |
|---|---|---|---|
| **P2 解耦** ✅ **已完成** | `core/events.py` + 转发层 + `main(argv)` + 进度走 Reporter | 中 | **已满足**，实施记录见附录 B |
| **P2.1 缺陷修复** ✅ **已完成** | `locate.resolve()` 显式来源不再静默回退；新增 `_rescue_by_child()` / `_explicit_error_text()` | 小 | **已满足**，21/21 契约用例 + 4/5 组 CLI 逐字节一致，见附录 B.4 |
| **P3a 骨架** ✅ **已完成** | `ghupdate-gui.bat` + `gui/app.py` 起窗口；两张卡片显示当前版本 | 中 | **已满足**，见附录 C |
| **P3b 功能** ✅ **已完成** | 检查更新 + 执行更新 + 实时进度 + 日志流 + 确认弹窗 | 大 | **已满足**（16/16 端到端）；真实下载留待下次有更新时验证 |
| **P3c 设置** ✅ **已完成** | 设置面板读写 `config.json`；目录浏览 | 中 | **已满足** |
| **P4 打磨** ⬜ 待做 | 图标、深色适配、取消按钮、完成通知 | 小 | 高 DPI 屏不模糊；取消能中断下载 |

> P3a / P3b / P3c **一次性交付**（用户选择「直接做到能更新」）。骨架单独交付没有实用价值，
> 而 P2 已把解耦做完，一次做完的风险并不更高。P4 的 DPI 适配已顺带实现（见附录 C）。

**P1 / P2 / P2.1 / P3 均已交付，剩余只有 P4 打磨。**

---

## 8. 已知风险

| 风险 | 影响 | 对策 |
|---|---|---|
| **解释器分叉** | CLI 跑 3.13、GUI 跑 3.14，行为若出现差异会被当成 bug | 已完成 §1.3 兼容性实测；P3 起 CI 手动跑两遍 |
| **Tk 高 DPI 模糊** | 高分屏下界面发虚 | 启动时 `ctypes` 调 `SetProcessDpiAwareness(2)`，失败则忽略 |
| **下载进度高频刷新卡 UI** | 队列积压 | 主线程 `after` 合并渲染：只取队列**最新**一条进度，中间的直接丢弃 |
| **pythonw 下异常无痕** | 崩了看不到原因 | 顶层 `try/except` 写 `ghupdate\_cache\gui-error.log`；另留 debug 版 bat |
| **managed Python 无可控性** | .workbuddy 升级可能改变解释器布局 | 启动器按能力探测；核心不依赖 managed 路径 |

---

## 9. 待决策项

1. **界面形态**：单页卡片式（§5.1，推荐）／多标签页
2. **解释器策略**：只认系统 3.14（简单）／启动器自动探测（§6，推荐）
3. **CLI 开关在 GUI 里的暴露度**：全暴露到设置页（推荐）／只暴露常用几个
4. **P2 是否现在开工**

> 说明：打包单 exe 与第三方 GUI 框架均**不可行**（PyPI 不通），不列为选项。

---

# 附录 A：开发完成后的项目形态

## A.1 文件树（★ = 待新增）

```
D:\RRL\MaaUpdaterBat\                  git 仓库，可整体拷贝到别的机器
├── README.md                          项目总览
├── .gitignore  .gitattributes
│
├── update-all.bat              ★入口①  命令行总入口（菜单 / 子命令）
├── ghupdate-gui.bat            ★入口②  图形界面（双击即用，无黑窗）
├── ghupdate-gui-debug.bat      ★入口③  排障版（保留控制台看 traceback）
│
├── ghupdate\                           工具本体（零第三方依赖）
│   ├── README.md
│   ├── _common.py                      共享库；P2 后 log/die/confirm 变薄转发层
│   ├── ghupdate.py                     CLI 分发与交互菜单
│   ├── update_maa.py                   MAA 更新流程
│   ├── update_maaend.py                MaaEnd 更新流程
│   ├── update-all.bat                  入口①的实际实现（相对路径版）
│   ├── config.example.json             配置模板（入库）
│   │
│   ├── core\                           无 UI 依赖的纯逻辑
│   │   ├── config.py                   配置加载 / 深合并 / 来源追踪 / 原子保存
│   │   ├── locate.py                   安装目录解析与校验
│   │   ├── mirror.py                   镜像候选构造（前缀式 / 模板式 / 直连兜底）
│   │   └── events.py            ★P2    Reporter 契约 + ConsoleReporter + 异常
│   │
│   └── gui\                     ★P3    Tkinter 界面
│       ├── app.py                      主窗口（卡片 / 进度 / 日志）
│       ├── reporter.py                 GuiReporter，队列桥接
│       ├── settings.py                 设置面板
│       └── theme.py                    字体 / DPI / 配色
│
├── ghproxy\                            方案 A（MITM 代理，已完成，不动）
└── docs\                               设计与分析文档
```

## A.2 运行时产物（不入库）

| 路径 | 内容 | 谁生成 |
|---|---|---|
| `ghupdate\config.json` | 安装目录、镜像列表、行为开关 | GUI / CLI 写入，**两者共享同一份** |
| `ghupdate\_cache\` | 下载包与 `.part` 断点残片 | 下载器 |
| `ghupdate\_backup\<程序>-<时间戳>\` | 更新前备份，回滚用 | 更新流程 |
| `ghupdate\_cache\gui-error.log` | GUI 未捕获异常（pythonw 无控制台时的唯一线索） | GUI 顶层兜底 |

## A.3 解释器：两套并存（已实测确认，无法避免）

| 入口 | 探测条件 | 本机命中 | tkinter |
|---|---|---|---|
| `update-all.bat` | `sys.version_info >= (3,8)` | `envs\default`（3.13.14，base = managed 3.13.12） | **✗ 无** |
| `ghupdate-gui.bat` | `>= (3,8)` **且** `import tkinter` | 系统 Python 3.14.6 | ✓ Tk 8.6 |

> **为什么不能统一**：managed 系（3.13.12 及其 venv）根本没装 Tcl/Tk，这是运行时分发的形态问题，
> 不是配置问题 —— 给它 `pip install tkinter` 也装不上（tkinter 随解释器编译）。
> 所以 CLI 继续用 managed（启动快），GUI 用系统 3.14。
> 两者跑**同一份源码、同一个 `config.json`**，行为差异已用 3.14 实测排除（见 §1.3）。

## A.4 规模变化

| | 现状 | 完成后（预估） |
|---|---|---|
| `ghupdate\` 下 py + bat + json | 2209 行 / 13 个文件 | **约 3400 行 / 20 个文件** |
| 其中 P2 + P3 新增 | — | `events.py` + `gui\` 4 文件 + 2 个 bat，约 1200 行 |
| 第三方依赖 | 0 | **0**（保持不变） |

## A.5 明确不变的东西

- **零第三方依赖** —— PyPI 不通是硬约束，也是这套工具的优点：拷到任何有 Python 的机器就能跑
- **不装证书、不改 hosts、不写程序自身配置** —— 只读 `gui.json` / `interface.json` 用于探测版本
- **安全链不变** —— 每次更新仍是 `SHA256 官方校验 → 备份 → 解压覆盖 → 版本复核`
- **CLI 完全兼容** —— P2 之后 `update-all.bat` 的所有子命令与输出逐字节不变，老用法不受影响
- **`ghproxy\` 不动** —— 方案 A 作为独立可选项保留，与 `ghupdate` 无耦合

## A.6 三种使用形态（用户视角）

| 场景 | 操作 | 走哪条路 |
|---|---|---|
| 日常更新 | 双击 `ghupdate-gui.bat` → 点「检查」→「更新」 | GUI |
| 想看细节 / 批处理 | 双击 `update-all.bat` → 菜单选 | CLI |
| 自动化 / 定时 | `update-all.bat check` 或 `maa -y` | CLI |

---

# 附录 B：P2 实施记录（已完成）

## B.1 实际改动

| 文件 | 改动 |
|---|---|
| `core/events.py` | **新增**。`Reporter` 契约 / `ConsoleReporter`（复刻原输出格式）/ `SilentReporter` / `UpdateError` / `UpdateCancelled` / `human()` / `get_reporter()` / `set_reporter()` |
| `_common.py` | `log/warn/ok/die/confirm` 改为转发给全局 Reporter；`human()` 转发；`download()` 的进度输出改走 `reporter.progress() / progress_end()`；新增 `get_reporter() / set_reporter()` 导出 |
| `update_maa.py` | `main(argv=None)`；`parse_args(argv)`；`__main__` 捕获 `UpdateError` 并转退出码 |
| `update_maaend.py` | 同上 |
| `ghupdate.py` | `main(argv=None)`；`__main__` 捕获 `UpdateError` |

`die()` 的语义从「打印后 `sys.exit()`」变为「打印后抛 `UpdateError`」，由顶层
`__main__` 统一转成退出码 —— 对 CLI 完全等价（输出与退出码都不变），但对 GUI
从此可拦可捕。

## B.2 验收结果

| 用例 | 方法 | 结果 |
|---|---|---|
| 5 组 CLI 基线 | 改造前后逐字节 `diff` | **一致** ✓ |
| `die` 路径 | 非交互 + 无可用配置，比对输出与退出码 | 输出一致、退出码同为 `1` ✓ |
| 下载进度 | 本地 HTTP 服务 + 3 MiB 文件，归一化速度/耗时后比对 | 一致 ✓ |
| 跨解释器 | 3.13.14（CLI 用）与 3.14.6（GUI 用） | 均编译通过 ✓ |

> 进度刷新点（1 / 2 / 3 MiB → 33.3% / 66.7% / 100.0%）与清屏宽度（72 空格）
> 都逐项核对过，不只是"跑通"。

## B.3 与规划的两处偏离

1. **进度不走 `progress_cb` 参数，改为统一走 Reporter**（原 §3.4 的设计）。
   进度本来就是一种事件，没必要开第二条通道；`download()` 签名因此零变动。
2. **没有把网络 / 校验 / 解压 / 备份搬进 `core/`**。原计划称「P2 结构重构」，
   实施时判断这些逻辑已被同一套 Reporter 覆盖，搬家只是形式整齐，收益低于
   改动风险。真正的分层界线是「是否依赖界面」，而不是文件放在哪个目录。

## B.4 已修缺陷：`locate.resolve()` 静默回退（P2 后发现并修复）

**症状**：显式来源（`--install` / 环境变量）校验失败时不报错，继续往下试，
最终被 `config.json` 里的另一个目录「兜住」。

```python
# 修复前 core/locate.py
sources = [--install, 环境变量, config.json]   # 三个来源拼成一个列表
for raw, source in sources:
    path = normalize(raw)
    good, why = validate(kind, path)
    if good:
        return path, source          # 第一个通过就返回 —— 于是 config 兜住了
```

实测（修复前）：

```
$ update_maa.py --install "D:/no-such-dir-xyz" --check
（不报错，实际更新的是 D:\RL\MAA-v6.9.5-win-x64，来自 config.json）  exit=0
```

用户明明用 `--install` 指定了目录，程序发现它不对却**不报错**，默默拿
`config.json` 里另一个目录顶替。违反 P1 的核心契约（「要么用你指的目录，
要么明确报错 —— 绝不静默回退」），风险是用户以为在更新 A 副本、实际动了 B 副本。

**修复**：把来源拆成「显式」与「隐式」两类。

| 来源 | 类别 | 校验失败时的行为 |
|---|---|---|
| `--install` | 显式 | **立即抛 `LocateError`**，不再往下试 |
| `GHUPDATE_INSTALL_*` | 显式 | 同上 |
| `config.json` | 隐式默认值 | 记入 `tried`，继续走一层子目录容错 → 交互询问 |

显式来源唯一的「救回」机会是**经用户确认**的一层子目录容错（`_rescue_by_child`）：
交互模式下问一句「用下面那个吗」，非交互模式一律不采用。

修复后（同一命令）：

```
[x] 你指定的 MAA 安装目录不可用：
      D:\RRL\MaaUpdaterBat   （来自 --install）
    —— 目录里没有 MAA.exe

    该目录内容：.git\、docs\、ghproxy\、ghupdate\、.gitattributes、.gitignore、README.md

    --install 不会改用 config.json 里保存的目录。
    要改用已保存的目录，请去掉 --install 后重新运行。
exit=1
```

新增两个内部函数：`_rescue_by_child()`（父目录容错，显式与隐式路径共用）与
`_explicit_error_text()`（显式来源的报错文案）。

### B.4.1 验证

`core/locate.py` 契约用例 **21/21 通过**：

- 显式来源失败必须报错，且**不回退 config**（`--install` 与环境变量各一组）
- 报错文案含来源、原因、目录内容、改回方式
- 父目录 + 非交互 → 报错并列出候选；+ 交互确认 → 采用子目录；+ 交互否认 → 报错
- `config.json` 隐式路径失效时，交互输入仍可覆盖
- `parent_probe: false` 时无候选段
- 路径规范化（引号 / 正斜杠 / 尾斜杠 / 直接填 exe）

CLI 端到端（与 HEAD 版逐字节对比，脚本目录前缀已归一化）：

| 组 | 命令 | 结果 |
|---|---|---|
| 1 | `update_maa.py --check --no-save` | SAME |
| 2 | `update_maaend.py --check --no-save` | SAME |
| 3 | `update_maa.py --show-config` | SAME |
| 4 | `update_maa.py -y --install <错目录> --check` | **DIFF（预期的行为变更）** |
| 5 | `ghupdate.py`（菜单渲染） | SAME |

第 4 组由 `exit=0`（静默用 config）变为 `exit=1`（报错），正是本次修复目标；
其余四组输出逐字节未变。

---

# 附录 C：P3 实施记录（已完成）

## C.1 实际交付

| 文件 | 规模 | 说明 |
|---|---|---|
| `gui/__init__.py` | 新增 | 包说明；CLI 路径不依赖本包 |
| `gui/app.py` | 新增 | 主窗口（单页卡片式）+ 线程/事件循环 + 卡片状态机 |
| `gui/reporter.py` | 新增 | `GuiReporter`：事件 → 队列；`confirm` 走「投递 + Event.wait(120s)」 |
| `gui/settings.py` | 新增 | 设置面板（镜像 / 目录 / 网络 / 行为四组） |
| `gui/theme.py` | 新增 | DPI 感知、字体挑选、配色、ttk 样式 |
| `ghupdate-gui.bat` | 新增 | 按能力探测解释器 + `pythonw` 启动（全 ASCII） |
| `ghupdate-gui-debug.bat` | 新增 | 两行包装，改用 `python.exe` 并 `pause` |
| `core/config.py` | 修改 | 新增 `channel` 字段（MAA 更新通道） |
| `update_maa.py` | 修改 | `--channel` 默认值改为空，实际取值 `CLI > config.json > stable` |

`gui/` 合计约 900 行（含注释），主窗口 `app.py` 约占一半。

## C.2 线程模型（落地形态）

```
主线程（Tk mainloop）
  ├── _poll()：after(50ms) 轮询 event_queue
  └── 处理事件：log→追加日志 / stage→阶段文字 / progress→进度条
                confirm→messagebox 弹窗后写回 box + done_event.set()
                        ▲
                        │ queue.Queue，元素统一为 (kind, event, *args)
                        │
工作线程（daemon）
  └── GuiReporter + update_maa.main(argv) / update_maaend.main(argv)
```

**`kind` 字段**是实施时补的：规划里没提，但两张卡片共用一个队列，带上它
主线程才不用猜事件属于谁。

**`confirm` 的跨线程往返**按规划实现 —— 工作线程投递后 `Event.wait(120s)`，
主线程弹 `messagebox.askyesno`、写回 `box["value"]`、`done_event.set()`。
超时按「取消」处理并记一条日志。

## C.3 与规划的偏离

1. **「检查更新」不调用 `main(--check)`，改为界面侧的轻量实现。**
   规划里写的是「后台跑 `--check`」。实施时发现：干跑会完整跑一遍选包流程，
   日志噪音大，而且「是否最新」这个结论要从输出文本里正则解析 —— 太脆。
   改为直接复用 `core` 的探测函数（`pe_file_version` / `read_interface_version`
   / `maa_latest` / `github_release` / `norm_ver`），与更新器用同一批数据源和
   同一个版本比较函数，结论一致，代码约 25 行。
   「立即更新」仍然走完整的 `main(argv)`，一行不差。

2. **主窗口不加「打开安装目录」的底部按钮，改为每张卡片各带一个。**
   两个程序各有自己的目录，放底部会歧义。

3. **新增 `channel` 配置项**（规划里漏了）。CLI 的 `--channel` 原本默认写死
   `stable`，与 `config.json` 无关；界面要能配通道就必须让它落盘。顺带把 CLI
   也改成读配置（`CLI > config.json > stable`），否则会出现「界面设了 beta、
   命令行还是 stable」的不一致。这是**唯一一处 CLI 可见的行为变更**：新增配置项
   会让 `--show-config` 多输出一行 `channel = stable [默认]`，其余输出逐字节未变。

4. **进度不额外做节流。** 规划担心 `progress` 高频刷屏。实测 `download()`
   本来就是每 1 MiB 上报一次，3 MiB 的文件只产生 3 个事件，无需再合并。

## C.4 验证

| 项目 | 方法 | 结果 |
|---|---|---|
| 事件桥接 | `GuiReporter` 单测：log/warn/ok/stage/progress/progress_end/confirm/fail | **11/11** |
| 窗口与状态机 | 构建真实 `App`（messagebox 替换为空实现），驱动事件、检查徽章/进度/日志 | **21/21** |
| 设置面板 | 构建 `SettingsDialog`、载入、恢复默认 | **5/5** |
| 缺配置降级 | 空配置下卡片提示去设置 | **2/2** |
| 界面「检查更新」 | 真实联网跑 MAA + MaaEnd | **8/8** |
| `main(argv)` 调用链 | 经 `GuiReporter` 跑 `--check` 干跑 | **8/8** |
| 下载进度事件流 | 本地 HTTP + 3 MiB 文件；进度序列 0.33 / 0.67 / 1.00 | **8/8** |
| **pythonw 无控制台** | 三个标准流**强制设为 `None`** 后构建窗口并跑 mainloop | **通过**，无崩溃日志 |
| 启动器探测 | 提取探测段单独跑：默认选 `pythonw`、`--debug` 选 `python`、错误 `MAAUPD_PYTHON` 会回落 | **通过** |
| CLI 回归 | 与 HEAD 版逐字节对比 5 组命令 | 4 组 SAME；第 3 组仅多 `channel` 一行（见 C.3-3） |
| `channel` 取值链 | 配置 beta 生效、`--channel alpha` 覆盖、非法值被 argparse 拒绝 | **通过** |

合计 **63 项断言**，全部通过。

## C.5 已知限制

- **P4 未做**：没有应用图标、没有深色主题适配、没有「取消」按钮
  （`GuiReporter.confirm` 有 120 秒超时，但下载过程无法中断）。
- **真实更新未跑过**：交付时两个程序都已是官网最新版，所以「立即更新」只验证到
  `main(argv)` 的调用链与事件流为止；下载、校验、备份、覆盖四段的界面表现沿用
  命令行已验证的结果 —— 它们本来就是同一份代码。
- **DPI**：已调用 `SetProcessDpiAwareness(1)` 并据此缩放窗口初始尺寸，但未在
  150% / 200% 缩放的屏幕上人工核对过。
- 界面文字只有中文，`ui.language` 配置项存在但未被使用。
