# MaaUpdaterBat

MAA / MaaEnd **程序本体更新**加速工具集。

本机到 GitHub 的**文件分发通道**被限速到 26–63 KB/s，且长连接会被中途 RST
（`github.com:443` 直连干脆不可达）。两个程序的「检查更新」因此几乎必然失败 ——
MAA 官方元数据里 **67 个 `mirrors` 数组全为空**，三个官方 CDN 镜像已被移除；
MaaEnd 日志里明写自己是「直连（无代理）」，两次下载分别跑了 6 分 51 秒和 19 分 24 秒后失败。

本仓库提供**两条独立的解决路线**，都绕开程序自带的更新器。

---

## 目录

```
MaaUpdaterBat\
├── ghupdate\              方案 B：独立更新器（推荐，零系统改动）
│   ├── update-all.bat         入口，双击即用（纯 ASCII）
│   ├── ghupdate.py            中文菜单 + 分发
│   ├── update_maa.py          MAA 更新器
│   ├── update_maaend.py       MaaEnd 更新器
│   ├── _common.py             共享库（HTTP / 下载 / 校验 / ZIP / 备份 / 版本探测）
│   └── README.md              详细说明
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
    └── MAA-MaaEnd加速-风险说明.md     写入系统信任库的风险评估
```

---

## 两条路线怎么选

| | **ghupdate**（方案 B） | **ghproxy**（方案 A′） |
|---|---|---|
| 原理 | 自己下载 + 校验 + 解压覆盖 | 本地 MITM 代理，把 `github.com` 回源到镜像 |
| 系统改动 | **零**（不装证书、不改 hosts、不写程序配置） | 需临时把本地 CA 装入当前用户信任库 |
| 使用方式 | 双击 `update-all.bat` | 双击 `run-maa.bat` / `run-maaend.bat` |
| 程序内自动更新 | 不支持（需先退出程序） | 支持（程序内点「检查更新」即可） |
| 风险 | 低 | 中（CA 信任范围为整个 Windows 账号） |
| 现状 | ✅ 已实机验证可用 | 已实现并验证，**未安装 CA**（备用） |

**默认推荐 `ghupdate`。** 只有在你想保留「程序内自动更新」体验时，才考虑 `ghproxy`。
`ghproxy` 的风险细节见 [`docs/MAA-MaaEnd加速-风险说明.md`](docs/MAA-MaaEnd加速-风险说明.md)。

---

## 快速开始

```
cd ghupdate
update-all.bat              # 中文菜单
update-all.bat check        # 干跑，不下载任何东西
update-all.bat maa          # 只更新 MAA
update-all.bat all          # 先 MAA 再 MaaEnd
```

⚠️ **更新前必须先完全退出对应程序** —— 脚本检测到目标程序在运行会直接拒绝执行
（运行时文件被占用，替换必然失败）。

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

---

## 环境要求

- Windows
- Python 3.8+（`update-all.bat` 会依次探测：托管 venv → 托管 3.13.12 → 系统 Python → `where python`）
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
| `*.log` / `*.pid` / `__pycache__` / `ca_installed.flag` | 运行时产物 |

### 原有工作目录

本仓库是从 `D:\RRL\.workbuddy\{ghupdate,ghproxy}` 迁移归集而来。原目录**保留未删**，
其中 `_cache\`（315 MB）与 `_backup\`（372 MB）是当时实机更新的运行期数据；
2026-10-15 那次更新的回滚备份仍在 `D:\RRL\.workbuddy\ghupdate\_backup\`。

### 依赖外部镜像

`ghupdate` 的下载通道依赖第三方镜像 `ghfast.top`，它可能限速或下线。
镜像不可用时脚本会自动重试并回退直连（63 KB/s 兜底），不会静默失败。

---

## 回滚

更新前会自动备份到 `_backup\<程序>-<时间戳>\`，整个目录复制回安装目录即可：

```
xcopy /E /Y /I "D:\RRL\MaaUpdaterBat\ghupdate\_backup\MAA-<时间戳>\*" "D:\RL\MAA-v6.9.5-win-x64\"
```
