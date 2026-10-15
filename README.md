# MaaUpdaterBat

MAA / MaaEnd **更新**加速工具集：覆盖 **① MAA 程序本体 ② MAA 资源（关卡数据 / 模板图）
③ MaaEnd 程序本体** 三条链路。

本机到 GitHub 的**文件分发通道**被限速到 26–63 KB/s，且长连接会被中途 RST
（`github.com:443` 直连干脆不可达）。两个程序的「检查更新」因此几乎必然失败 ——
MAA 官方元数据里 **67 个 `mirrors` 数组全为空**，三个官方 CDN 镜像已被移除；
MaaEnd 日志里明写自己是「直连（无代理）」，两次下载分别跑了 6 分 51 秒和 19 分 24 秒后失败。

本仓库提供**两条独立的解决路线**，都绕开程序自带的更新器。

> ### ⚠️ 第三方非官方工具
>
> 本项目与 MAA / MaaEnd 开发组**没有任何隶属关系**，也未获其授权或背书。
> **默认走 GitHub 直连**，不经过任何第三方服务器；启用镜像加速前请先读
> [`安全提醒与免责声明.md`](安全提醒与免责声明.md)。

---

## 安全提醒与免责声明

**这是第三方非官方工具。** 与 MAA / MaaEnd 开发组、Mirror 酱、鹰角网络均无
隶属关系。它只做一件事：下载官方更新包、校验后覆盖到指定目录 —— 不修改游戏、
不注入进程、不读取账号信息、不收集也不上传任何数据。

**默认不使用任何第三方镜像**（`mirror.enabled = false`），一律直连 GitHub。
要提速必须由你自己手动开启。

为什么默认关掉：镜像站是**第三方反向代理**，能看到你请求的地址，也有能力替换
返回给你的内容。而各链路的兜底能力**并不相同**：

| 更新链路 | 官方摘要 | 镜像篡改能否被发现 |
|---|---|---|
| MAA 程序本体 | 有（GitHub `digest`，SHA256） | **能** —— 摘要不符会拒绝写入并报错 |
| MaaEnd 程序本体 | 有（同上） | **能** —— 同上 |
| MAA 资源（关卡数据 / 模板图） | **没有** | **有限** —— 只有语义校验 + CRC32，挡不住精心构造的替换 |

> 资源包由官方仓库以 `archive/refs/heads/main.zip` 发布，GitHub 不提供这类
> 分支归档的官方摘要。工具的兜底是「包内 `version.json` 的 `last_updated` 必须
> 严格等于 mirrorchyan 上的版本号」，能挡住空包 / 截断 / 错分支 / 旧缓存 /
> 镜像错误页，但**挡不住同时改写版本文件与内容的镜像站**。
>
> 一句话：**走镜像更新资源时，安全性完全取决于你是否信任那一个站。**

结论：在意完整性就保持默认（代价是慢，实测 26–63 KB/s 且可能中途断线）；
选择启用镜像，请自行判断该镜像站是否可信。本项目对任何第三方镜像站的可用性、
安全性、稳定性与隐私实践**不作任何担保**，也不为其行为负责。

完整的免责条款、参考镜像地址清单，以及 `ghproxy` 方案（会往系统信任库安装
证书）的风险说明，都在 **[`安全提醒与免责声明.md`](安全提醒与免责声明.md)**。

---

## 目录

```
MaaUpdaterBat\
├── 启动更新器.bat          ★ 唯一入口：双击它就行
├── 使用说明.txt              给最终用户看的极简说明（发布包里会带上）
├── ghupdate\              方案 B：独立更新器（推荐，零系统改动）
│   ├── update-all.bat         命令行入口，双击即用（纯 ASCII）
│   ├── ghupdate-gui.bat       图形界面入口（自动挑带 tkinter 的解释器）
│   ├── ghupdate-gui-debug.bat 同上，保留控制台看报错
│   ├── ghupdate.py            中文菜单 + 分发
│   ├── update_maa.py          MAA 本体更新器
│   ├── update_maa_res.py      MAA 资源更新器（关卡数据 / 模板图）
│   ├── update_maaend.py       MaaEnd 更新器
│   ├── _common.py             共享库（HTTP / 下载 / 校验 / ZIP / 备份 / 版本探测）
│   ├── core\                  纯逻辑模块（config / events / locate / mirror，CLI 与 GUI 共用）
│   ├── gui\                   图形界面（Tkinter：app / reporter / settings / theme）
│   ├── config.example.json    配置模板（config.json 是本机配置，不入库）
│   └── README.md              详细说明
├── tools\
│   └── pack.py                打包脚本：打出「用户视角」的发布 zip（输出到 dist\）
├── ghproxy\               方案 A′：本地拦截代理（需临时装 CA）
│   ├── ghproxy.py             纯标准库 MITM 代理（127.0.0.1:8899）
│   ├── ghproxy-ctl.bat        start / stop / status / install-ca / remove-ca
│   ├── run-maa.bat            一键：装 CA → 起代理 → 启动程序 → 退出自动清理
│   ├── run-maaend.bat         同上（MaaEnd）
│   ├── restore.bat            应急幂等还原
│   ├── gen-certs.bat          重新生成本地 CA 与叶证书
│   └── README.md              详细说明
└── docs\                  排查与设计文档
    ├── MAA-MaaEnd更新加速计划.md      完整诊断 + 方案 A/B/C
    ├── MAA-MaaEnd更新方案B细化.md     更新规则分析 + 方案 B 设计
    ├── ghupdate-可配置化与GUI规划.md  镜像可换 / 手动指定目录 / GUI 路线
    ├── ghupdate-MAA资源更新接入方案.md 资源链路实测 + 校验手段取证 + 9 步设计
    ├── ghupdate-GUI开发规划.md        界面布局 / 线程模型 / 分阶段路线
    ├── 迁移到其他设备评估.md           换机时的障碍清单与操作步骤
    └── MAA-MaaEnd加速-风险说明.md     写入系统信任库的风险评估
```

---

## 两条路线怎么选

| | **ghupdate**（方案 B） | **ghproxy**（方案 A′） |
|---|---|---|
| 原理 | 自己下载 + 校验 + 解压覆盖 | 本地 MITM 代理，把 `github.com` 回源到镜像 |
| 系统改动 | **零**（不装证书、不改 hosts、不写程序配置） | 需临时把本地 CA 装入当前用户信任库 |
| 使用方式 | 双击 `ghupdate-gui.bat`（界面）或 `update-all.bat`（命令行） | 双击 `run-maa.bat` / `run-maaend.bat` |
| 程序内自动更新 | 不支持（需先退出程序） | 支持（程序内点「检查更新」即可） |
| 风险 | 低 | 中（CA 信任范围为整个 Windows 账号） |
| 现状 | ✅ 已实机验证可用 | 已实现并验证，**未安装 CA**（备用） |

**默认推荐 `ghupdate`。** 只有在你想保留「程序内自动更新」体验时，才考虑 `ghproxy`。
`ghproxy` 的风险细节见 [`docs/MAA-MaaEnd加速-风险说明.md`](docs/MAA-MaaEnd加速-风险说明.md)。

---

## 快速开始

**最省事的方式：双击项目根目录下的 `启动更新器.bat`。**

界面直接打开，不用管内部结构。它是个薄转发 —— 真正干活的是
`ghupdate\ghupdate-gui.bat`，后者会自动挑一个能 `import tkinter` 的解释器。

**图形界面**（等价入口，位于 `ghupdate\`）：

```
cd ghupdate
ghupdate-gui.bat            # 窗口里看状态、点「检查更新」/「立即更新」
ghupdate-gui-debug.bat      # 同一个界面，但保留控制台看报错
```

**命令行**（脚本化 / 定时任务）：

```
cd ghupdate
update-all.bat              # 中文菜单
update-all.bat check        # 三个都干跑，不下载任何东西
update-all.bat maa          # 只更新 MAA 程序本体
update-all.bat maares       # 只更新 MAA 资源（关卡数据 / 模板图）
update-all.bat all          # 本体 -> 资源 -> MaaEnd 依次更新
```

两条入口**共用同一份 `config.json` 和同一套更新逻辑**（界面调的就是
`update_maa.main()` / `update_maa_res.main()`），在窗口里改完设置，命令行立刻生效。

⚠️ **更新前必须先完全退出对应程序** —— 脚本检测到目标程序在运行会直接拒绝执行
（运行时文件被占用，替换必然失败）。界面里也会拦下来并提示。

---

## 配置化与安装目录

镜像与安装目录都在 `ghupdate\config.json` 里改，不必动代码。
**界面里点「设置…」也能改全部开关**（镜像地址、安装目录、代理、超时/重试、
更新通道、备份/校验/重启/清理），保存用的就是同一套原子写：



```
update-all.bat maa --show-config                            看看当前生效了什么（含每项来源）
update-all.bat maa --install "D:\RL\MAA-v6.9.5-win-x64"     指定安装目录（校验通过后记住）
update-all.bat maa --inspect "D:\RL"                        检查某目录并列出子目录候选
update-all.bat maa --mirror https://其他镜像/                换镜像（可重复传多次）
```

安装目录是**手动指定**的，不做自动定位 —— 契约是「要么用你指的目录，要么明确报错，
绝不静默回退到别处」。解析优先级：`--install` > 环境变量 > `config.json` > 交互询问。
详见 [`ghupdate/README.md`](ghupdate/README.md)。

---

## 打包分发

```
python tools\pack.py                    # -> dist\MaaUpdaterBat-YYYYMMDD.zip
python tools\pack.py --list             # 只列出会打包哪些文件，不写 zip
python tools\pack.py --no-config        # 发给别人时用（不含本机安装路径）
python tools\pack.py --out D:\x.zip     # 自定义输出位置
```

发布包的结构**故意不同于仓库结构**。仓库是给开发者看的，根目录并列着
`ghupdate` / `ghproxy` / `docs` 和一堆 VCS 文件；包只留用户需要的东西：

```
MaaUpdaterBat\
├── 启动更新器.bat          <-- 唯一入口，双击这个就行
├── 使用说明.txt
├── README.md
├── ghupdate\              主程序（21 个文件）
└── 可选\                  平时用不到，删了也不影响使用
    ├── docs\              排查与设计文档（7 个文件）
    └── ghproxy\           备用方案（7 个文件）
```

排除规则与 `.gitignore` 对齐（运行期产物、私钥、本机缓存），另加 VCS 元数据
与打包脚本自身。`ghupdate\config.json` 默认**打进包里**（自用 / 换机时省得
重新指定安装目录），`--no-config` 可去掉。

打包完成后脚本会**回读 zip 自检**三件「出错后极难排查」的事：换行符、中文
文件名编码、是否混进敏感文件。

> **为什么盯着 CRLF**：cmd.exe 读 LF-only 的 `.bat` 会出现行边界解析错位，
> 症状是把 `rem` 注释里的单词当成命令执行 —— 满屏「不是内部或外部命令」，
> 可脚本本身又「看起来能跑」。本仓库的 `ghupdate-gui.bat` 与
> `ghupdate-gui-debug.bat` 之前就是这个状态：`.gitattributes` 声明了
> `eol=crlf`，但工作区文件是在 Windows 上以 LF 直接写入的，而 git 只在检出
> 时才应用 eol，所以一直没被纠正。现已统一为 CRLF，打包脚本每次也会兜底
> 重写一遍。

---

## 已实机验证的结果（2026-10-15）

| 程序 | 更新前 | 更新后 | 包体量 | 耗时 | 通道 |
|---|---|---|---|---|---|
| MAA | v6.18.0 | **v6.19.0** | 19.57 MB（OTA 增量） | 60.8 s | ghfast.top |
| MaaEnd | v2.30.1 | **v2.32.0** | 295.21 MB（全量） | 227.1 s | ghfast.top |

两个包的 SHA256 均与 GitHub 官方 `digest` **逐字符一致**；用户配置
（`config/gui.json`、`config/mxu-MaaEnd.json`）时间戳未变，登录状态与设置完好。

作为对照：同样两个包走直连是 26–63 KB/s，MaaEnd 那 295 MB 至少需要 80 分钟，
而且实测会在 7 分钟和 19 分钟时被 RST 掐断。

### 资源链路的验证（2026-10-15）

| 项目 | 结果 |
|---|---|
| 资源包 | 13.53 MB，镜像下载 18.0–34.8 s（395–780 KB/s） |
| 包结构 | `MaaResource-main/resource/**` 共 5311 个文件 |
| 版本比对 | mirrorchyan `version_name` 与包内 `resource/version.json` 的 `last_updated` 完全一致 |
| 全量比对 | 本机 5311 个文件逐个 size+CRC32 比对 → **5311 相同 / 0 需写入**，验证零误判 |
| 修复演练 | 故意篡改 `stages.json` + 删掉一个包内文件 → 只写入 2 个文件（788 KB），其余 5309 个一字未动 |
| 用户数据 | `config.json` / `ocr_config.json` / `copilot` / `custom_infrast` 全程未被触碰 |

> 资源包 13.5 MB 的体量解释了它「一直还算能忍」的原因 —— 同样被限速，14 MB 能熬过去，
> 284 MB 必然断链。

---

## 环境要求

- Windows
- Python 3.8+（`update-all.bat` 会依次探测：托管 venv → 托管 3.13.12 → 系统 Python → `where python`）
- **图形界面**另需一个**带 tkinter 的解释器**。tkinter 随解释器编译而来，装不上也补不齐 ——
  本机 managed Python 3.13.x 没有 Tcl/Tk，因此**能跑命令行、跑不了界面**。
  `ghupdate-gui.bat` 会自动挑出可用的那个，全都不行会提示怎么修。
- **无需任何第三方 pip 包**（证书由 `openssl` 生成，代理只用 Python 标准库）
- `ghproxy` 另需 `openssl`（Git for Windows 自带）

---

## 注意事项

### 不会入库的内容

`.gitignore` 已排除运行期产物，**克隆下来即可直接使用**：

| 排除项 | 原因 |
|---|---|
| `ghproxy/certs/` | **含私钥**（`ghmirror-ca.key` / `github.key`），且是机器本地的。用 `gen-certs.bat` 重新生成 |
| `ghupdate/_cache/` | 下载缓存（实测约 315 MB） |
| `ghupdate/_backup/` | 更新前备份（实测约 372 MB），回滚用，保留在本地即可 |
| `ghupdate/config.json` | 本机配置（含个人安装路径），模板见 `config.example.json` |
| `*.log` / `*.pid` / `__pycache__` / `ca_installed.flag` | 运行时产物 |
| `dist/` | 打包产物，随时可用 `tools\pack.py` 重新生成 |

### 原有工作目录

本仓库最初从 `D:\RRL\.workbuddy\{ghupdate,ghproxy}` 迁移归集而来。那批原目录
（含 `_cache\` 315 MB 与 `_backup\` 372 MB 的运行期数据）已于 2026-10-15 清理完毕，
**本仓库现在是唯一副本**，`D:\RRL` 下只剩 `MaaUpdaterBat\` 与 `AC6\`。

### 依赖外部镜像

`ghupdate` 默认走第三方镜像 `ghfast.top`，它可能限速或下线。镜像现在是**可配置**的
（`--mirror` 或 `config.json` 的 `mirror.prefixes`），全部失效时会自动重试并回退直连
（63 KB/s 兜底），不会静默失败。

---

## 回滚

更新前会自动备份到 `_backup\<程序>-<时间戳>\`，整个目录复制回安装目录即可：

```
xcopy /E /Y /I "D:\RRL\MaaUpdaterBat\ghupdate\_backup\MAA-<时间戳>\*" "D:\RL\MAA-v6.9.5-win-x64\"
```
