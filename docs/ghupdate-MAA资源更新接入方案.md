# MAA「资源更新」接入 ghupdate —— 可行性验证与方案设计

> 日期：2026-10-15 16:00 起草，**同日 16:20 完成实施**
> 触发需求：把 MAA 的游戏资源更新也接进 `ghupdate`
> 现状：`ghupdate` 只覆盖**程序本体**（链路①），资源更新（链路②）依赖 MAA 自己点按钮
> 本文一~四章为**起草时的实测与设计**，五~六章为**实施结果**。所有数据均为实测，非推测。
> 关联提交：`feat: MAA 资源更新接入`（见 git log）

---

## 结论摘要

**可行，而且比程序本体更新更简单。**

| 维度 | 结论 |
|---|---|
| 版本检查 | ✅ mirrorchyan API **无需 CDK**，200 / 44 ms；本机版本就在 `resource/version.json` 里，**字符串直接比对** |
| 下载通道 | ✅ `ghfast.top` 镜像 **783 KB/s，14 MB / 18 秒**（直连仅 20.9 KB/s，差 37 倍） |
| 包结构 | ✅ 干净：`MaaResource-main/resource/*` → 安装目录 `resource/*`，一层映射 |
| 用户数据安全 | ✅ 包内**不含** `custom_infrast/`、`config/`、`onnx/`、`copilot/` |
| 增量写入 | ✅ 按 CRC32 逐文件比对，只写变化的。实测本机 5311/5311 全一致 → **写入量 0** |
| 校验手段 | ⚠️ **没有官方 SHA256**。ETag 已实测证伪（不是内容哈希），需改用语义校验 |
| 断点续传 | ❌ 镜像与直连**都不支持 Range**，14 MB 必须一次下完（18 秒，可接受） |

一句话：**版本比对靠 mirrorchyan，下载靠 ghfast.top，校验靠「包内 version.json 必须等于远端版本」，写入靠 CRC 差异**。四步都有实测支撑。

---

## 一、实测事实（方案的地基）

### 1.1 资源更新的真实链路（来自 MAA 自己的日志）

`D:\RL\MAA-v6.9.5-win-x64\debug\gui.log`：

```
[ResourceUpdater]   New version found: 2026-10-14+15:45:24.000, 昨日海
[HttpService]       Start to download file from
                    "https://github.com/MaaAssistantArknights/MaaResource/archive/refs/heads/main.zip"
                    and save to D:\RL\MAA-v6.9.5-win-x64\MaaResourceGithub.zip.temp
[HttpResponseLoggingExtension]  HTTP: OK GET
                    https://codeload.github.com/MaaAssistantArknights/MaaResource/zip/refs/heads/main
                    "34e65426…68e6" null 1469.309ms
```

**关键结论：资源更新也是走 GitHub。** 它和程序本体更新的区别只是——查版本用 mirrorchyan（通畅）而不是 api.maa.plus（失效），下载用的是 `archive/refs/heads/main.zip` 而不是 release 资产。

这也解释了为什么它「一直正常」：**包只有 14 MB**，即使被限速也能在几分钟内下完；而程序本体全量包 284 MB，在 63 KB/s 下几乎必然断链。

### 1.2 端点可达性与速度（本次实测）

| 端点 | 结果 | 用途 |
|---|---|---|
| `mirrorchyan.com/api/resources/MaaResource/latest` | **200，44 ms**，无需 CDK | 查资源版本 ✅ |
| `ghfast.top/https://github.com/…/main.zip` | **200，14,185,118 B / 18.1 s = 783 KB/s** | 下载主通道 ✅ |
| 直连 `codeload.github.com/…/zip/refs/heads/main` | **200，20.9 KB/s** | 兜底（慢 37 倍）⚠️ |

**两处重要细节**：

1. **都不支持 Range。** `curl -r 0-99` 返回 `200` 而非 `206`，并立即开始传全量。这意味着**断点续传不可用**——现有的 `_cache/*.part` 机制在这里失效，中断就得重下。
2. **`Content-Length` 不稳定。** 首次 HEAD 请求没有该头（GitHub 动态打包，chunked），第二次再请求才出现 `Content-Length: 14185118`。进度显示需要容错：拿不到总长度时退化为「已下载 xx MB」而不显示百分比。

### 1.3 包结构（已完整下载并解析）

```
MaaResource-main.zip            13.53 MB（压缩后）
└── MaaResource-main/
    ├── resource/           5,336 项   ← 唯一需要的东西
    ├── cache/                  2 项   ← 跳过
    ├── .github/                4 项   ← 跳过
    ├── LICENSE
    └── README.md
```

**映射关系只有一条**：`MaaResource-main/resource/*` → `<安装目录>/resource/*`。

包内 `resource/` 的构成：

| 目录 | 文件数 | 解压后 |
|---|---|---|
| `Arknights-Tile-Pos/` | 4,269 | 86.94 MB |
| `template/` | 1,019 | 9.22 MB |
| `global/` | 16 | 1.29 MB |
| `tasks/` | 1 | — |
| 根文件（7 个） | 7 | 1.93 MB |
| **合计** | **5,311**（排除 `.gitignore`） | **99.38 MB** |

根文件是：`.gitignore`、`battle_data.json`、`infrast.json`、`item_index.json`、`recruitment.json`、`stages.json`、`version.json`。

**最值得注意的是「不包含什么」**：包内没有 `custom_infrast/`、`config/`、`copilot/`、`onnx/`、`PaddleOCR/`、`minitouch/`、`platform_diff/`。本机 `resource/` 有 20 个顶层条目、288 MB，而包里只覆盖其中 4 个目录 + 7 个根文件。

**所以：更新资源不会碰到你的自定义基建排班、不会碰 `config/`。**

### 1.4 校验依据：ETag 已证伪

GitHub archive 的 ETag 长得很像 SHA256，很容易误用：

```
ETag   : cc547535f3208d806063f7719896e96a4376f55b17f5a376601e0b15ed5d0dfc
实测   : c95911ab65674e083704b4b3bbd9fa7695c7ffa3d7ff1ad0fa565c594d53cd7c   ← 实际 SHA256
匹配   : False
```

**结论：ETag 不能当校验和。** 它对同一 commit 稳定（镜像与直连返回一致），可以拿来做「内容是否变化」的版本标识，但**不能用来验证下载完整性**。

GitHub 的 archive 包**不提供官方 digest**，所以程序本体更新那套「取 `api.github.com` 的 `digest` 比对 SHA256」在这里**用不了**。

### 1.5 替代校验方案：语义校验 + CRC32

两级校验，都不依赖官方摘要：

**第一级 · 包内版本语义比对**
解压**之前**，先从 zip 中读出 `resource/version.json` 的 `last_updated`，必须**严格等于** mirrorchyan 报的 `version_name`：

```
mirrorchyan 报的      : "2026-10-14 15:45:24.000"
包内 version.json 的  : "2026-10-14 15:45:24.000"   ← 必须一致
```

这一条能挡住：空包、错分支、截断的 zip、镜像挂掉的错误页、被换成的旧版本。比哈希更贴合语义。

**第二级 · zipfile 自带的 CRC32**
`zipfile.extract` 在解压每个条目时自动校验 CRC32，损坏即抛 `BadZipFile`。这不是防篡改，但能防传输损坏。

**另外**：CRC32 还能直接当**差异比对**用（见下），一份数据两用。

### 1.6 增量写入：已验证可行

把包内 5,311 个文件逐个与本机对应文件做 **size + CRC32** 比对：

```
包内文件（排除 .gitignore）: 5311
  本机同内容（无需写）     : 5311      ← 100%
  内容不同（需覆盖）       : 0
  本机缺失（需新增）       : 0

需要写入的字节数约: 0.00 MB
```

两个结论：
1. 本机资源确实已是最新（`last_updated` 与 mirrorchyan 报的一致），**没有假差异**。
2. **CRC32 比对方法可靠**——5311 个文件零误判。

这意味着日常更新只需写入**真正变化的文件**：新活动副本的地图坐标（`Arknights-Tile-Pos/` 下几十个 JSON）、更新的 `stages.json`、少量新模板图。预计**几 MB 量级**，而不是 99 MB 全量覆盖。

---

## 二、方案设计

### 2.1 流程（9 步）

| 步 | 动作 | 失败处理 |
|---|---|---|
| 1 | 定位 MAA 安装目录（复用 `locate.resolve`） | 报错退出，不猜 |
| 2 | 检查 `MAA.exe` 是否在运行（复用 `check_running`） | 拒绝执行，提示关闭 |
| 3 | 读本机 `resource/version.json` → `local_ver` | 文件缺失 → 视为「需全量」，不中止 |
| 4 | 查 mirrorchyan → `remote_ver` | 失败 → 报错退出（这是唯一的版本来源） |
| 5 | `local_ver == remote_ver` ? | 相同 → 「资源已是最新」，exit 0 |
| 6 | **下载 zip** → `_cache/MaaResource.zip` | 镜像 → 直连兜底；都失败则报错 |
| 7 | **校验包**：读 zip 内 `resource/version.json`，必须 == `remote_ver` | 不符 → **立即中止，不落地任何文件** |
| 8 | **比对 + 备份**：算出需写入清单，把将被覆盖的文件备份到 `_backup/res-{时间戳}/` | 空间不足 → 中止 |
| 9 | **应用 + 复核**：只覆盖变化文件；重读版本确认 == `remote_ver` | 复核不符 → 提示用备份回滚 |

### 2.2 五个关键决策

**① 校验用语义比对，不用 SHA256**
理由见 1.4 —— archive 包没有官方 digest，ETag 也不是内容哈希。硬要 SHA256 就只能自建基线（第一次下载记下来，之后比对），但那等于**首次下载无保护**，反而更弱。语义校验从一开始就有效。

**② 只写变化文件，不做全量覆盖**
- 备份量从 99 MB 降到实际变化量（几 MB）
- 写入快、失败面小
- 实测 5311/5311 判断正确，方法可靠

**③ 不做 `--prune`（不删本地多余文件）**
资源包没有 `removelist.txt`，无法判断哪些本地文件该删。保守只增改、不删。

**④ 必须经镜像，直连只作兜底**
20.9 KB/s 下 14 MB 要 11 分钟且大概率被 RST，作为主通道不可接受。

**⑤ 目录名映射硬编码为 `MaaResource-main/`**
GitHub archive 的顶层目录名 = `<仓库名>-<分支名>`，它是稳定的。但仍要加一层容错：解压时**忽略顶层目录名**，只认 `*/resource/` 这一层，避免 GitHub 改命名规则就崩。

### 2.3 与程序本体更新的关系

两条链路**完全独立**，可分别执行，也互不干扰：

| | 链路① 程序本体 | 链路② 资源 |
|---|---|---|
| 版本源 | `api.maa.plus` → `stable.json` | `mirrorchyan.com` |
| 包大小 | 19.6 MB（OTA）/ 284 MB（全量） | 13.5 MB |
| 校验 | 官方 SHA256 | 语义比对 + CRC32 |
| 频率 | 低（版本发布时） | **高（每次游戏活动更新）** |
| 是否含 config/ | 不含 | 不含 |

**唯一的重叠**：程序本体全量包含 10093 个 `resource/` 文件，资源包包含其中 5311 个。两者内容一致，**先跑哪个都行**，后跑的会覆盖先跑的（内容相同，无副作用）。

**建议顺序**：程序本体 → 资源。因为资源更新更频繁，放后面能拿到最新。

---

## 三、边界情况

| 情况 | 处理 |
|---|---|
| MAA 正在运行 | 拒绝执行（`resource/` 下文件被占用，覆盖会失败） |
| mirrorchyan 不可达 | 报错退出。**不做「跳过检查直接下载」** —— 没有 `remote_ver` 就无法校验包 |
| 下载中断 | 重下整个 14 MB（无断点续传）。重试 3 次后转直连 |
| 拿不到 `Content-Length` | 进度退化为「已下载 xx MB」，不显示百分比 |
| 包内版本 ≠ 远端版本 | 立即中止。这通常意味着镜像返回了旧缓存或错误内容 |
| 本机 `version.json` 缺失 | 不中止，走全量比对（所有文件都算「需新增」） |
| 磁盘空间 | 需 14 MB（zip）+ 变化量（备份）。实际约 20 MB |
| 想回滚 | 把 `_backup/res-{时间戳}/` 复制回 `resource/` |
| 镜像返回 HTML 错误页 | `zipfile.is_zipfile()` 前置检查，不是合法 zip 直接判失败 |

---

## 四、集成点

### 4.1 代码结构

新增 `ghupdate/update_maa_res.py`（独立脚本，约 250 行），复用现有模块：

- `locate.resolve` / `validate` —— 目录解析
- `_common.check_running` / `download` / `human` / `log` / `ok` / `warn` / `die`
- `_common.build_download_urls` —— 镜像候选构造
- `core.events` —— 事件上报（GUI 与 CLI 共用一套）

**不新增配置项** —— 镜像、超时、重试、备份开关全部沿用 `config.json` 现有字段。

### 4.2 CLI

`ghupdate.py` 菜单加一项（现为 5 项 → 6 项）：

```
  3) 更新 MAA 资源（关卡数据 / 模板图）
```

子命令：`update-all.bat maares`。给 `update_maa.py` 加 `--with-resource` 开关，可一次跑完程序本体 + 资源。

### 4.3 GUI

MAA 卡片增加一行资源状态 + 一个按钮：

```
┌─────────────────────────────────────────┐
│ MAA                           [已是最新] │
│ D:\RL\MAA-v6.9.5-win-x64                │
│ 程序  v6.19.0   已是最新                 │
│ 资源  2026-10-14 15:45:24   已是最新     │
│                        [检查] [更新资源] │
└─────────────────────────────────────────┘
```

「更新资源」复用现有的后台线程 + 队列事件机制，不新增线程模型。

---

## 五、已拍板的决策（2026-10-15）

| # | 决策点 | 结论 | 理由 |
|---|---|---|---|
| 1 | 独立入口还是合并入口 | **两者都提供** | `update-all.bat maares` 给日常（资源更新最频繁）；`maa --with-resource` 给「一次跑完」 |
| 2 | `all` 要不要含资源 | **含**，顺序 `maa -> maares -> maaend` | 「全部」就该是全部；资源排在本体后面，能拿到本体全量包之后的最新一份 |
| 3 | GUI 资源行的粒度 | **只显示 `last_updated` 时间戳** | 「本次将更新 N 个文件」必须先下 14 MB 才知道，代价与收益不成比例 |
| 4 | 是否开工 | **当日完成** | 复用已验证的下载与比对逻辑，风险低 |

## 六、实施记录与验证

### 6.1 交付物

| 文件 | 说明 |
|---|---|
| `ghupdate/update_maa_res.py` | 新增，资源更新器本体（约 290 行） |
| `ghupdate/ghupdate.py` | 菜单 6 项 → 7 项；新增 `maares` 子命令；`all`/`check` 扩为三个动作 |
| `ghupdate/update_maa.py` | 新增 `--with-resource`；主流程抽成 `_run_binary(args) -> (rc, install)` |
| `ghupdate/gui/app.py` | MAA 卡片新增资源行与「更新资源」按钮；徽章改为程序+资源综合判定 |
| `ghupdate/gui/theme.py` | 新增 `CardRes.TLabel`；窗口基准高度 640 → 660 |
| `ghupdate/_common.py` | `download()` 在未给 `expected_size` 时改从响应头取 `Content-Length` 当总长度 |
| `ghupdate/core/events.py` | `ConsoleReporter._write` 增加 `stream is None` 保护（pythonw 场景） |

**没有新增任何配置项** —— 镜像、超时、重试、备份开关全部沿用 `config.json` 现有字段。
资源复用 `install.maa.path`（资源就在 MAA 安装目录下）。

### 6.2 与方案的四处偏差

1. **`--force` 是新增的**。方案里没有。用于「版本号相同但本地文件残缺」的场景
   （例如上次更新中途失败）。默认关闭。
2. **进度条不需要「降级方案」**。方案 1.2 担心拿不到 `Content-Length`，实测发现：
   同一地址走 **GET** 时 GitHub 稳定返回 `Content-Length: 14185118`，走 HEAD 才没有。
   于是改为在 `download()` 里从响应对象读头部，**零额外请求**就拿到了总长度，
   顺带让进度条和「大小不符」检测都能工作。
3. **不传 `expected_size`，因而每次都重新下载**。这是刻意的：URL 指向分支 `main`，
   内容会变；若复用缓存 zip，会被第 7 步的语义校验拦下（拿的是旧版本），
   用户将永远卡在失败里。代码里已加注释说明，避免后人「优化」成 bug。
4. **资源更新器的 `version_of` 回调不打印任何东西**。因为 GUI 的只读扫描会在
   `pythonw`（无控制台、`stdout is None`）下调用它；安静失败比在界面上刷日志合适。

### 6.3 验证结果（全部实测）

| 项目 | 结果 |
|---|---|
| 离线单测（合成 zip，覆盖解析/比对/写入/失败保护/幂等/健壮性） | **43/43 通过** |
| `--check` 干跑（真实目录，不下载） | 正确识别「已是最新」 |
| `--inspect` | 正确报出资源版本 `2026-10-14 15:45:24.000` |
| 真实全流程（下载 13.53 MB + 5311 文件 CRC 比对） | 5311 相同 / 0 需写入，**零写入** |
| 修复演练（篡改 1 个 + 删除 1 个包内文件） | 只写入 2 个文件（788 KB），其余 5309 个一字未动 |
| 用户数据（`config.json`/`copilot`/`custom_infrast`） | 全程未被触碰 |
| GUI 冒烟（卡片结构/资源行/状态汇总/事件/降级/真实联网检查） | **38/38 通过** |
| pythonw 且 stdout/stderr/stdin 全为 `None` | 正常启动、无崩溃日志 |
| CLI 回归（与 HEAD 逐字节对比，5 组） | 4 组一致，第 5 组（菜单）为预期的功能变更 |

**实施中发现并修掉的两个真 bug**（都在 GUI）：

1. 「检查更新」结束后徽章卡在「进行中」—— `_task_done` 的 check 分支没有重算状态。
   改为在收尾处统一调用 `_sync_status` / `_sync_note`。
2. 失败说明被「已是最新」覆盖 —— `_sync_note` 在状态含 `failed` 时应直接返回，
   让失败文案优先。

### 6.4 使用

```
update-all.bat maares                 日常：只更新资源
update-all.bat maa --with-resource    一条命令：本体 + 资源
update-all.bat all                    全部：本体 + 资源 + MaaEnd
update-all.bat maares --force         版本号相同也强制逐文件比对并补齐差异
```

界面：MAA 卡片上多一行「资源 …」和一个 **[更新资源]** 按钮；点「检查更新」会
**同时**查程序与资源，徽章取两者的综合结论。

## 七、一句话总结

MAA 的资源更新**本来就是走 GitHub 的 archive zip**，包只有 13.5 MB，所以它「一直正常」；
接入 `ghupdate` 的实现路径是 **mirrorchyan 查版本 → ghfast.top 下载 → 包内 version.json 语义校验
→ CRC32 差异只写变化文件**——四步全部实测通过，且不含任何用户数据。
