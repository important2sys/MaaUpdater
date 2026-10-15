# ghupdate 可配置化（镜像可换 + 手动指定安装目录）+ GUI 路线规划

> 版本：**v2**（2026-10-15 14:35 修订）
> 涉及代码：`D:\RRL\MaaUpdaterBat\ghupdate\`（`_common.py` / `ghupdate.py` / `update_maa.py` / `update_maaend.py`）
> v1 → v2 变更：**取消「安装目录自动探测」，改为「手动指定 EXE 所在目录」**。
> 连带删除 `search_roots` / `glob` / `scan_drives` / `state.json`，并把原 P1、P2 合并为单阶段。
> 状态：**P1 已实施并实机验证通过（22 项用例全绿）**；P2 结构重构起待启动。
> 实施记录见文末「八、P1 实施记录」。

---

## 一、现状：三处硬编码

| # | 位置 | 内容 | 影响 |
|---|---|---|---|
| 1 | `_common.py:32` | `MIRROR_PREFIX = "https://ghfast.top/"` | 镜像写死；`ghfast.top` 一旦限速/下线，只能改源码 |
| 2 | `update_maa.py:23` / `update_maaend.py:22` | `DEFAULT_ROOT = r"D:\RL"` | 换盘、换目录就找不到 |
| 3 | `update_maa.py:24` / `update_maaend.py:23` | `DEFAULT_GLOB = "MAA*"` / `"MaaEnd*"` | 目录名匹配 |

**唯一的解析点（两条链路完全同构）**

```python
# update_maa.py:103
install = args.install or C.autodetect_dir(DEFAULT_ROOT, DEFAULT_GLOB, MARKER)
if not install or not os.path.isfile(os.path.join(install, MARKER)):
    C.die("找不到 MAA 安装目录（可在 --install 指定）")

# update_maaend.py：同位置、同写法
```

`install` 一旦确定，后面 100% 的逻辑都基于它 → **只要改这一个解析点，就能完成目录改造**。

镜像拼接点（两处，逻辑相同）：

```python
# update_maa.py:196 / update_maaend.py:144
urls = [C.MIRROR_PREFIX + origin, origin]   # 镜像优先，直连兜底
```

---

## 二、设计 A：可配置的镜像

### A1. 配置文件 `ghupdate\config.json`

首次运行自动生成；同时入库一份 `config.example.json`，`config.json` 进 `.gitignore`（本地配置不入库）。

```jsonc
{
  "version": 1,

  "mirror": {
    "enabled": true,
    // 按顺序尝试，命中即用；支持两种写法：
    //   前缀式 "https://ghfast.top/"     -> 拼成 <prefix><完整 github url>
    //   模板式 "https://x.com/{url}"     -> {url} 替换为完整 github url
    "prefixes": ["https://ghfast.top/"],
    // 镜像全挂后是否再试 GitHub 直连（26–63 KB/s，慢但能通）
    "fallback_direct": true
  },

  "install": {
    // 空 = 未指定，运行时会询问你；填上后永久生效
    "maa":    { "path": "" },
    "maaend": { "path": "" }
  },

  "locate": {
    // 指定目录里没有主程序时，只在它的“直接子目录”里探一层并征求确认
    "parent_probe": true
  },

  "network": { "proxy": "", "timeout": 30, "retries": 3 },
  "behavior": { "prune": false, "restart": false, "backup": true,
                "verify": true, "keep_residue": false },
  "ui": { "language": "zh-CN" }
}
```

> 相对 v1 删掉了整个 `search` 段（`extra_roots` / `scan_drives` / `max_depth`）和 `install.*.glob`，
> 也删掉了 `state.json` —— 路径直接存 `config.json`，语义是「**用户设定**」而不是「自动探测结果」。

### A2. 配置位置与优先级

**位置（按序探测，先命中先用）**
1. `--config PATH`
2. 环境变量 `GHUPDATE_CONFIG`
3. 脚本目录 `ghupdate\config.json`（**默认，便携**）
4. 都没有 → 用内置默认值并写出 `config.json`

**优先级**：`CLI 参数` > `环境变量` > `config.json` > `内置默认`

环境变量：`GHUPDATE_CONFIG`、`GHUPDATE_MIRROR`、`GHUPDATE_PROXY`、`GHUPDATE_INSTALL_MAA`、`GHUPDATE_INSTALL_MAAEND`

### A3. 新增 CLI 参数

| 参数 | 说明 |
|---|---|
| `--mirror URL` | 覆盖镜像前缀（可重复传多次，形成候选列表） |
| `--no-mirror` | 本次禁用镜像，直接用 GitHub |
| `--config PATH` | 指定配置文件 |
| `--show-config` | 打印当前生效配置（含来源），排查用 |
| `--install DIR` | 指定安装目录；校验通过后写回配置 |
| `--no-save` | 配合 `--install`：只本次生效 |
| `--inspect [DIR]` | 检查目录并列出子目录候选 |
| `--forget-install [maa\|maaend\|all]` | 清除已保存的安装路径 |

### A4. 代码改动（最小侵入）

```python
def build_urls(origin, prefixes=None, enabled=True, fallback_direct=True):
    urls = []
    if enabled:
        for p in (prefixes or []):
            urls.append(p.replace("{url}", origin) if "{url}" in p
                        else p.rstrip("/") + "/" + origin)
    if fallback_direct or not urls:
        urls.append(origin)
    return urls
```

调用点由 `urls = [C.MIRROR_PREFIX + origin, origin]` 改为 `C.download_asset(cfg, origin, dest, ...)`
（内部先 `C.build_download_urls(cfg, origin)`，再把候选顺序打进日志）。
**`download()` 本身已支持「多 URL 依次尝试 + `.part` 断点续传 + 重试」，无需改动。**

---

## 三、设计 B：手动指定安装目录（v2 重写）

### B0. 设计契约

> **要么用你指的目录，要么明确报错 —— 绝不静默回退到别的目录。**

这是砍掉自动定位后最重要的行为变化。自动定位的风险是「猜错了静默更新错副本」；
手动指定把决策权交给你，代价是**错了必须说清楚错在哪**。

### B1. 目录解析优先级（4 级，命中即用）

| 级别 | 来源 | 说明 |
|---|---|---|
| 1 | `--install PATH` | CLI，最高优先级，本次生效 |
| 2 | `GHUPDATE_INSTALL_MAA` / `GHUPDATE_INSTALL_MAAEND` | 环境变量，脚本/CI 用 |
| 3 | `config.json` → `install.maa.path` / `install.maaend.path` | **持久生效**（填一次，以后免输） |
| 4 | 交互式询问 | 控制台提示你输入目录；输入合法则**写回 config.json** |

- 第 4 级在 `-y` / 非交互（无 stdin）下**不询问**，直接报错退出，错误信息里给出可复制的示例命令。
- 交互输入做**规范化清理**（cmd 拖拽/资源管理器复制地址栏会带各种杂质）：

```python
def normalize_dir(s):
    s = s.strip().strip('"').strip("'").strip()   # 拖拽来的引号
    s = os.path.expandvars(os.path.expanduser(s)) # %USERPROFILE% / ~
    s = s.replace("/", os.sep)                    # 正斜杠
    s = s.rstrip("\\/")                           # 尾部反斜杠
    if os.path.isfile(s):                         # 直接填了 xxx\MAA.exe 也认
        s = os.path.dirname(s)
    return os.path.abspath(s)
```

### B2. 校验（失败即报错，不猜）

```python
REQUIRED = {
    "maa":    ("MAA.exe",    ["MAA.exe"]),                 # 目录内必须有 MAA.exe
    "maaend": ("MaaEnd.exe", ["MaaEnd.exe", "interface.json"]),
}
```

报错信息要**可操作**，例如：

```
[×] 你指定的目录不是 MAA 安装目录：
      D:\RL
    目录里没有 MAA.exe（现有内容：AC6/、MaaUpdaterBat/、.workbuddy/）
    你会不会想指定：D:\RL\MAA-v6.9.5-win-x64 ？
    用法：update-all.bat --install "D:\RL\MAA-v6.9.5-win-x64"
```

### B3. 父目录容错（一层，**默认开启，可关**）

指定目录里没有 marker，但它的**直接子目录**里有：

- 恰好 1 个命中 → 交互式确认「要不要用 `D:\RL\MAA-v6.9.5-win-x64`？」，答 y 则采用并记录；
- 多个命中 → 列表让用户选（附各自**真实版本号**，不是目录名）；
- `-y` / 非交互 → 直接报错，把候选列出来让用户显式指定。

> 注意：这是**一层浅查找**（`<dir>\*\MAA.exe`），不是 v1 那种带全盘扫描的自动定位。
> 成本极低但能挡住「顺手把 `D:\RL` 填进去」这种最常见的输入错误。
> 若你觉得这也太多余，`config` 里给个 `"parent_probe": false` 一键关掉。

### B4. 持久化与撤销

- `--install PATH` 校验通过后**自动写回** `config.json`（加 `--no-save` 可只本次生效）；
- `--forget-install maa|maaend|all` 清空配置里的路径；
- 写入时**保留文件里其他字段与注释以外的结构**（用 `json` 读改写，缩进 2，末尾换行）。

### B5. 新增 / 变更 CLI 参数

| 参数 | 说明 |
|---|---|
| `--install PATH` | 已有；语义变更为「指定安装目录（含 EXE）」，**并持久化** |
| `--no-save` | 配合 `--install`：只本次生效，不写入配置 |
| `--inspect [PATH]` | 列出 PATH（或其直接子目录）中的候选安装及其**真实版本**，不做任何改动 |
| `--forget-install X` | 清除已保存的安装路径 |
| ~~`--list-installs`~~ | v1 计划项，由 `--inspect` 取代 |
| ~~`--scan-drives`~~ | **取消**（不再有全盘扫描） |

### B6. 连带变化：v1 里那个「必须一起修」的缺陷，现在自动消失了

v1 发现 `autodetect_dir()`（`_common.py:354`）用 `hits.sort(); hits[-1]` **按目录名排序取最大**，
而本机目录名是误导的（`MAA-v6.9.5-win-x64` 里实际跑 **v6.19.0**）。

- 手动指定后**不存在「多候选自动排序」**这个环节，该缺陷的触发路径被整个移除；
- `autodetect_dir()` 函数**保留但不再默认调用**，只服务于 B3 的一层容错（并改为返回全部候选，由用户决定）；
- 「按真实版本排序」降级为**纯展示用途**（`--inspect` 输出里同时打目录名与真实版本，便于你判断该指哪个）。

**版本探测逻辑必须保留**（与定位无关）：判断「是否已是最新」仍要读
MAA → `MAA.exe` 的 PE FileVersion（`C.pe_file_version()`）、MaaEnd → `interface.json` 的 `version`。

### B7. 实测计划（改完后逐条验证）

| # | 操作 | 期望 |
|---|---|---|
| 1 | 清空 `config.json` 路径，交互运行 | 提示输入目录；输入合法 → 保存并正常更新 |
| 2 | 同上，输入 `"D:\RL" `（带引号+空格） | 被规范化；触发 B3 一层容错并确认 |
| 3 | `--install "D:\RL\MaaUpdaterBat"` | 报错并指出该目录没有 `MAA.exe` |
| 4 | 把 MAA 目录复制到 `D:\Other\MAA-新家`，`--install` 指过去 | 正常识别版本并更新（验证完全不依赖目录名与位置） |
| 5 | 无参数 + `-y` 且无配置 | **明确报错退出**，不猜目录 |
| 6 | `--show-config` | 打印生效镜像与两个安装目录及来源 |
| 7 | 改 `config.json` 镜像为无效域名 | 自动回落直连（或按配置失败报错），日志可见尝试顺序 |

---

## 四、设计 C：GUI 路线（随 v2 同步调整）

### C1. 当前代码为什么不能直接套 GUI

| 现状 | 位置 | GUI 下的问题 |
|---|---|---|
| `die()` 调 `sys.exit` | `_common.py:72` | 会退掉整个进程，GUI 需要「弹窗 + 保持界面」 |
| `log/warn/ok` 直接 print | `_common.py:59-70` | GUI 要进文本框 |
| `confirm()` 读 stdin | `_common.py:459` | GUI 要弹对话框 |
| 下载进度写 `\r` 到 stdout | `_common.py:190` | GUI 要进度条 |
| `main()` 里 argparse+流程+IO 混在一起 | `update_*.py` | 无法复用 |

### C2. 目标架构：核心逻辑与界面分离

```
ghupdate\
├── core\                    ← 纯逻辑，零 IO 依赖，CLI 与 GUI 共用
│   ├── errors.py            异常体系（替代 sys.exit）
│   ├── config.py            配置加载·合并·校验·保存
│   ├── locate.py            安装目录解析（4 级优先级 + 规范化 + 校验 + 一层容错）
│   ├── mirror.py            镜像 URL 构造 + 可用性/测速
│   ├── net.py               HTTP / 断点续传（进度回调）
│   ├── verify.py            SHA256
│   ├── pack.py              ZIP 安全解压 / removelist / prune
│   ├── backup.py            备份
│   ├── version.py           MAA(PE) / MaaEnd(interface.json) 版本探测
│   ├── maa.py / maaend.py   两条更新流程（纯逻辑）
├── events.py                事件模型
├── cli.py                   命令行 + 中文菜单
├── gui.py                   Tkinter 界面
├── update_maa.py            ← 兼容薄壳（保持现有命令行行为不变）
├── update_maaend.py         ← 兼容薄壳
├── update-all.bat           入口（CLI，支持拖拽目录/exe 进来）
└── update-all-gui.bat       入口（GUI）
```

**硬约束**：重构后现有 CLI 的输出要「几乎逐字不变」（用 `--check` 输出做回归比对）。

### C3. 事件模型（CLI / GUI 唯一接口）

```python
class Reporter:
    def log(self, level, msg): ...            # 普通日志
    def stage(self, name, index, total): ...  # 阶段标题
    def progress(self, done, total, speed): ...  # 返回 False 表示取消
    def confirm(self, prompt) -> bool: ...
    def choose_dir(self, candidates) -> str:  # 多候选/未指定时让用户选
```

- **CLI 版**：`print` + `input`（= 现在的表现）
- **GUI 版**：写 `queue.Queue`，Tk 主循环 `after(50, ...)` 取用；更新在**工作线程**跑，界面不卡

### C4. 框架选型

| 方案 | 依赖 | 结论 |
|---|---|---|
| **Tkinter** | 自带 | ✅ **推荐 v1**（`ttk.Progressbar` / `filedialog` / `Treeview` 够用） |
| pywebview | 需 pip | 备选（本机 PyPI 不通） |
| 本地 Web | 需 pip | 不推荐 |

> 本机 **PyPI 不可达** → 「零第三方依赖」是**硬约束**，不是偏好。

### C5. 界面草案（v2：目录改为手动指定）

**主界面**
```
┌─ MAA / MaaEnd 更新器 ───────────────────────────[设置]─┐
│  镜像：ghfast.top                                       │
│  MAA 位置：D:\RL\MAA-v6.9.5-win-x64  (v6.19.0) [更改]   │
│  ────────────────────────────────────────────────────── │
│  ┌ MAA ─────────────────────────────────────────────┐   │
│  │ 当前 v6.19.0   →   最新 v6.19.0     [已是最新]    │   │
│  │            [检查]  [更新]  [打开目录]             │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌ MaaEnd ──────────────────────────────────────────┐   │
│  │ 未指定目录                       [选择目录…]      │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌ 进度 ────────────────────────────────────────────┐   │
│  │ ████████████░░░░░░  62%   1.30 MB/s   剩余 43s    │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌ 日志 ────────────────────────────────────────────┐   │
│  │ [4/6] 下载更新包（镜像优先，直连兜底）…            │   │
│  │   SHA256 一致：f335b1c2…                          │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**设置页**（GUI 下「手动指定」体验最佳）
- 镜像列表：可增删 / 拖动排序 / **[测速]**（并发 HEAD，按速度排序，最快置顶）
- 安装目录：两个程序各一行 —— 显示当前路径 + 校验状态（`✓ MAA v6.19.0` / `✗ 目录里没有 MAA.exe`）
  + `[浏览…]`（`filedialog.askdirectory`）/ `[打开目录]` / `[清除]`
- 网络：代理、超时、重试
- 行为：`prune` / `restart` / 备份 / 强制校验 开关

**首次启动**（无配置路径）→ 直接弹出目录选择向导，选完即存，比控制台交互友好得多。

---

## 五、实施阶段（v2：三阶段 + 增强）

| 阶段 | 内容 | 改动面 | 风险 | 验收 |
|---|---|---|---|---|
| **P1 配置化** ✅ | `core/config.py` + `core/locate.py`（4 级解析 + 规范化 + 校验 + 一层容错）；`config.example.json`；`.gitignore`；镜像列表化；新 CLI 参数 | **小** | **低** | B7 七条实测全过；`--show-config` 正确；换镜像能下载并校验通过 |
| **P2 结构重构** | 抽 `core/` + `events.py` + `cli.py`；`die()`→异常；进度→回调；薄壳化 `update_*.py` | 大 | **中**（需回归） | `--check` 输出与重构前逐行一致；`-y` 更新成功 |
| **P3 GUI** | `gui.py`(Tkinter) + `update-all-gui.bat`；主界面/设置页/进度/日志 | 大 | 低（纯新增，不动 CLI） | 图形界面跑通一次完整更新 |
| **P4 增强**（可选） | 镜像测速排行、托盘、定时检查、中英双语 | — | 低 | — |

> v1 里 P1（配置化）与 P2（自动定位）分开，是因为定位逻辑量大（搜索根、全盘扫描、缓存、版本排序）。
> **砍掉自动定位后两者体量都变小，合并为一个 P1，一阶段即可交付「镜像可换 + 目录可指」两个诉求。**

**顺带修的过时引用**（P1 内一并处理）
- `_common.py:9` docstring 指向 `D:\RRL\MAA-MaaEnd更新方案B细化.md` → 实际已移到 `docs\`
- `update_maa.py:86` argparse description 写死「经 ghfast.top 镜像」→ 改为中性描述

---

## 六、需你决定的点（v2：从 5 个减到 3 个）

1. **配置文件放哪？**
   - (a) 脚本目录 `ghupdate\config.json`（便携，推荐）
   - (b) `%APPDATA%\MaaUpdaterBat\config.json`（用户级）
   - (c) 两者都支持，脚本目录优先

2. **B3 的「父目录容错」要不要？**（填了 `D:\RL` 却应该是 `D:\RL\MAA-xxx` 时）
   - (a) 默认开，可关（推荐：成本极低，挡住最常见输入错误）
   - (b) 不要，填错就直接报错（最严格，完全符合「手动」语义）

3. **P1 现在就做吗？**

（GUI 框架默认 **Tkinter**，如无异议不再单列成决策点。）

---

## 附：本次规划用到的关键事实

- 目录解析在两条链路各只有**一处**（`update_maa.py:103` / `update_maaend.py` 同位置），改造面极小
- `download()` 已支持「多 URL 依次尝试 + `.part` 断点续传 + 重试」→ 镜像列表化无需改下载器（`_common.py:135`）
- `pe_file_version()` 已能读 PE FileVersion（`_common.py:366`），MaaEnd 版本读 `interface.json`（`update_maaend.py:28`）
- 镜像只能代理 `github.com`，**代理不了 `api.github.com`（403）** → 查版本/取摘要仍走直连
- 本机 **PyPI 不可达** → 坚持零第三方依赖 → GUI 用 Tkinter
- 三个更新包官方均提供 SHA256 `digest`，校验链路不受本次改动影响
- 本机目录名与实际版本不符：`MAA-v6.9.5-win-x64` → 实际 **v6.19.0**；`MaaEnd-...v2.23.0` → 实际 **v2.32.0**

---

## 八、P1 实施记录（2026-10-15）

**新增文件**

| 文件 | 作用 |
|---|---|
| `ghupdate/core/__init__.py` | 包声明 |
| `ghupdate/core/config.py` | 配置加载·深合并·字段级来源追踪·原子保存 |
| `ghupdate/core/locate.py` | 4 级优先级解析·路径规范化·目录校验·一层容错·`--inspect` |
| `ghupdate/core/mirror.py` | 镜像候选构造（前缀式 / 模板式 / 直连兜底） |
| `ghupdate/config.example.json` | 配置模板 |

**改动文件**

- `ghupdate/_common.py`：新增 `add_config_args()` / `setup()` / `build_download_urls()` / `download_asset()`；
  docstring 指向已迁走的旧文档 → 改为 `docs\`；给 `import core.*` 加 `sys.path` 保险；
  `MIRROR_PREFIX` 与 `autodetect_dir()` 保留为兼容项并注明「不再默认调用」。
- `ghupdate/update_maa.py` / `update_maaend.py`：定位改走 `C.setup()`；
  下载改走 `C.download_asset()`（会把候选顺序打进日志）；
  `backup / verify / prune / restart / keep_residue` 改由 `cfg.get("behavior.*")` 驱动。
- `ghupdate/ghupdate.py`：菜单**动态**显示当前镜像与两个安装目录；新增第 5 项
  「更改安装目录 / 查看配置」（可直接在菜单里指定并保存）；拖入路径时给出明确引导。
- `README.md`（顶层与 `ghupdate\` 各一份）、`.gitignore`（加 `config.json`）。

**验收：22/22 通过**

覆盖：交互输入正确目录 / 带引号与空格 / 直接填 exe / 正斜杠 /
输到父目录确认 / 拒绝后重输 / 错误目录后重输 / 输入 q 放弃 / stdin 耗尽 /
非交互无配置报错 / `--install` 正误 / config 生效与来源标记 / `--install` 优先于 config /
环境变量生效 / `parent_probe` 开关 / MaaEnd 链路 / 交叉填错报错 / 配置往返一致。

**实机端到端**

- `update_maa.py --check`：识别 `D:\RL\MAA-v6.9.5-win-x64` 为 **v6.19.0**，与最新版一致 → 直接退出
- `update_maaend.py --check`：`interface.json` 读到 **v2.32.0**，与最新版一致 → 直接退出
- `--inspect "D:\RL"`：正确判定「不是安装目录」，并列出子目录候选
  `D:\RL\MAA-v6.9.5-win-x64  6.19.0` —— 显示的是**真实 PE 版本**，不是目录名
- 配置已生成 `ghupdate\config.json`，两个安装目录均已记住

**实施中额外做的两处改进（原规划未写）**

1. **交互输入失败时也递候选**：在交互循环里输到父目录，同样会问「用这个吗」；
   原设计只对显式来源（CLI / 环境变量 / 配置）生效，交互路径会漏掉。
2. **日志顺序**：标题框改由 `setup()` 内部打印。否则 `--no-save` 与「已记住安装目录」
   这两条提示会跑到标题框**之前**，看着别扭。
