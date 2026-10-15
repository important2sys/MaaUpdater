# ghupdate —— MAA / MaaEnd 更新器（方案 B）

> ⚠️ **第三方非官方工具**，与 MAA / MaaEnd 开发组没有隶属关系。
> **默认直连 GitHub，不经过任何第三方服务器**；要用镜像加速请先读
> [`安全提醒与免责声明.md`](../安全提醒与免责声明.md)。
>
> 生成时间：2026-10-15（2026-10-15 增补：MAA **资源更新**）
> 目标程序：`D:\RL\MAA-v6.9.5-win-x64`（MAA，实测版本 v6.19.0）、
> `D:\RL\MaaEnd-win-x86_64-v2.23.0`（MaaEnd，实测版本 v2.32.0）
> 关联文档：`..\docs\` 下的 `MAA-MaaEnd更新加速计划.md`、`MAA-MaaEnd更新方案B细化.md`、
> `ghupdate-可配置化与GUI规划.md`、`ghupdate-MAA资源更新接入方案.md`
>
> 覆盖范围：**① MAA 程序本体 ② MAA 资源（关卡数据/模板图）③ MaaEnd 程序本体**。
> 原先只有 ①③，「资源」一直靠 MAA 自己点按钮更新。

## 为什么需要它

MAA 与 MaaEnd 的**程序本体更新**只能走 GitHub。本机到 GitHub 的**文件分发通道**被限速到
26–63 KB/s 且长连接会被中途 RST（`github.com:443` 直连干脆不可达）；MAA 官方元数据里
**67 个 `mirrors` 数组全为空**，三个官方 CDN 已移除。所以程序内点「检查更新」几乎必然失败。

本工具**绕开程序自带的更新器**，自己完成：

```
查版本 -> 选包(优先增量) -> 下载(默认直连，可选镜像) -> SHA256 校验
       -> 备份 -> 解压覆盖 -> 应用 removelist -> 版本复核
```

**零系统改动**：不装证书、不改 hosts、不写任何程序配置文件（只「读」配置用于探测版本）。

MAA 的**资源更新**（关卡坐标、模板图）同样是走 GitHub 的 archive 包，只是包只有 13.5 MB，
所以它在限速下「一直还能忍」。接入方式一样是走镜像，但校验手段不同 —— 见下文
[资源更新](#maares-7-步)。

## 快速开始

双击 **`update-all.bat`** 打开中文菜单：

```
   1. 仅检查更新（干跑，不下载任何文件）
   2. 更新 MAA 程序本体
   3. 更新 MAA 资源（关卡数据 / 模板图）
   4. 更新 MaaEnd
   5. 更新全部（本体 + 资源 + MaaEnd）
   6. 更改安装目录 / 查看配置
   7. 查看用法 / 高级选项
   0. 退出
```

菜单顶部会显示当前镜像、两个程序的安装目录名，以及 MAA 资源的当前版本。
**首次运行**如果还没指定过目录，会直接问你要路径（可直接把文件夹从资源管理器拖进窗口），
校验通过后自动记住。

命令行同样可用：

```
update-all.bat                        打开菜单
update-all.bat check                  三个都干跑（不下载任何东西）
update-all.bat maa                    更新 MAA 程序本体
update-all.bat maares                 更新 MAA 资源
update-all.bat maaend                 更新 MaaEnd
update-all.bat all                    本体 -> 资源 -> MaaEnd 依次更新
update-all.bat maa --with-resource    本体 + 资源，一条命令跑完
update-all.bat maa --prune --restart  更新 MAA，清理废弃文件并启动
```

> **`maares` 用的是哪个目录？** 和 MAA 本体同一个 —— 资源就在安装目录下的
> `resource\`。所以它复用 `install.maa.path`，不单独配。

### 图形界面

双击 **`ghupdate-gui.bat`**，一个窗口里看完两个程序的状态：

```
 MAA / MaaEnd 更新器
 镜像未启用（直连 GitHub）      配置：...\ghupdate\config.json
 ──────────────────────────────────────────────────────────────
  MAA                                              [已是最新]
  安装目录：D:\RL\MAA-v6.9.5-win-x64
  程序 v6.19.0                最新 v6.19.0
  资源 2026-10-14 15:45:24.000    已是最新
  [检查更新] [立即更新] [更新资源]                  [打开目录]
 ──────────────────────────────────────────────────────────────
  MaaEnd                                           [可更新]
  安装目录：D:\RL\MaaEnd-win-x86_64-v2.23.0
  程序 v2.32.0                最新 v2.33.0
  [检查更新] [立即更新]                            [打开目录]
 ──────────────────────────────────────────────────────────────
  ███████████░░░░░░░░░░░░░░░  45.2%  132.5 MB / 293.1 MB  3.27 MB/s
 ──────────────────────────────────────────────────────────────
  [收起日志]                                            [清空]
  [v] MAA 未在运行
  [1/6] 查询 MAA 最新版本（stable 频道）…
 ──────────────────────────────────────────────────────────────
  设置…   查看配置   退出
```

- **检查更新** —— 只查版本、不下载。MAA 那张卡会**同时**查程序与资源，
  徽章把两者合起来判定（最常见的情况正是「程序已最新、资源过期」）
- **立即更新** —— 与命令行**完全相同**的流程（下载 → 校验 → 备份 → 覆盖 → 复核），
  动手前弹一次确认框，过程中进度条实时走、日志逐行刷
- **更新资源** —— 只跑资源那条链路，同样走完整的下载/校验/备份/写入
- **设置…** —— 镜像地址、安装目录、代理、超时/重试、更新通道、备份/校验/重启等全部开关
- **查看配置** —— 等价于 `--show-config`，含每一项的来源

界面与命令行**共用同一个 `config.json`**，改一边另一边立刻生效。界面调用的是
`update_maa.main()` / `update_maa_res.main()` / `update_maaend.main()`，不是另写一套逻辑
—— 所以不会出现「界面能更新、命令行不行」这类差异。

> **为什么 GUI 要单独挑解释器**：本机 managed Python（3.13.x）**没有编译 Tcl/Tk**，
> 连 `import tkinter` 都失败。`ghupdate-gui.bat` 按序探测
> `%MAAUPD_PYTHON%` → `%LOCALAPPDATA%\Programs\Python\Python3*` →
> `%APPDATA%\uv\python\cpython-*` → PATH，逐个试 `import tkinter`，谁行用谁。
> 全都不行会列出探测过的位置并提示怎么修，**命令行不受影响**。
>
> 窗口起不来时用 **`ghupdate-gui-debug.bat`**（保留控制台看 traceback）。
> 两者都会把崩溃信息追加到 `ghupdate\gui-error.log`。

### 选项

| 选项 | 作用 |
|---|---|
| `--install DIR` | 指定安装目录（含 `MAA.exe` / `MaaEnd.exe` 的文件夹）；校验通过后写进配置，下次免输 |
| `--no-save` | 配合 `--install`：只本次生效，不写配置 |
| `--inspect [DIR]` | 检查目录是不是安装目录，并列出子目录候选（不做任何改动） |
| `--forget-install [maa\|maaend\|all]` | 清除已保存的安装路径 |
| `--mirror URL` | 覆盖镜像前缀，可重复传多次形成候选列表 |
| `--no-mirror` | 本次禁用镜像，直连 GitHub |
| `--config PATH` | 指定配置文件（默认 `ghupdate\config.json`） |
| `--show-config` | 打印当前生效配置（含每项来源）后退出 |
| `--check` | 只检查不下载（干跑） |
| `--with-resource` | **仅 MAA**：本体更新完接着更新资源，一条命令跑完 |
| `--force` | **仅 maares**：版本号相同也逐文件比对并补齐差异（用于修复残缺的本地资源） |
| `--prune` | **仅 MAA**：按新 `filelist.txt` 清理废弃程序文件（默认关闭） |
| `--restart` | 更新完成后启动程序 |
| `-y` | 不再交互确认 |
| `--no-backup` | 跳过备份（不建议） |
| `--no-verify` | 无官方摘要时仍继续（不建议） |
| `--proxy URL` | 显式代理，如 `http://127.0.0.1:7890` |
| `--channel` | **仅 MAA**：`stable`（默认）/ `beta` / `alpha` |

## 安装目录：手动指定，不自动探测

本工具**不做自动定位**。设计契约是：

> **要么用你指的目录，要么明确报错 —— 绝不静默回退到其他目录。**

自动探测最怕「猜错了还默默更新到错误副本」，所以决策权交回给你，代价是失败时
必须把「试过哪些、为什么不行、你可能想用哪个」讲清楚。

**解析优先级**

| 级别 | 来源 | 类别 | 说明 |
|---|---|---|---|
| 1 | `--install PATH` | **显式** | 命令行，最高优先级 |
| 2 | `GHUPDATE_INSTALL_MAA` / `GHUPDATE_INSTALL_MAAEND` | **显式** | 环境变量 |
| 3 | `config.json` → `install.maa.path` / `install.maaend.path` | 隐式默认值 | 持久生效 |
| 4 | 交互式询问 | — | 控制台里问你；输入合法则写回配置 |

**显式来源一旦给出就以它为准**：`--install` 或环境变量指的目录若不可用，直接报错
退出，**不会退回去用 `config.json` 里保存的目录** —— 否则你以为在更新 A，实际动了 B。
要改回已保存的目录，去掉 `--install`（或清除环境变量）重新运行即可。

`config.json` 是**隐式默认值**，失效时允许被交互输入覆盖。

**路径会被自动规范化**（这些写法都能认）：

| 你的输入 | 处理结果 |
|---|---|
| `"D:\RL\MAA-v6.9.5-win-x64" ` | 去掉引号与首尾空格 |
| `D:/RL/MAA-v6.9.5-win-x64/` | 正斜杠、尾部反斜杠 |
| `D:\RL\MAA-v6.9.5-win-x64\MAA.exe` | 直接填 exe 文件 → 取所在目录 |
| `%USERPROFILE%\Desktop\MAA` | 展开环境变量 |
| `D:\RL`（父目录） | 一层容错：问「用下面那个吗」；非交互时直接报错 |
| `D:\RRL\MaaUpdaterBat` | 不是安装目录 → 报错，并列出目录内容供你判断 |

**一层子目录容错**（`locate.parent_probe`，默认开、可关）：
若你给的目录本身不是安装目录，但它的**直接子目录**里有唯一一个像样的候选，
会问你一句「用这个吗」。这不是全盘扫描，只是挡住「顺手填了 `D:\RL`」这类最常见的手误。

非交互模式（`-y` 或管道重定向）下**不会**自动采用任何候选，只会报错。
想关掉整个容错：配置里设 `"locate": { "parent_probe": false }`。

排查用：

```
update-all.bat maa --inspect "D:\RL"
```

```
MAA 安装目录检查
  D:\RL
    判定：不是安装目录 —— 目录里没有 MAA.exe
    目录内容：001\、AALC_V1.4.10\、...
    该目录的直接子目录里有这些候选：
      - D:\RL\MAA-v6.9.5-win-x64   6.19.0
```

注意最后那个版本号 —— **是读 `MAA.exe` 的真实 PE 版本，不是目录名**。
本机目录名 `MAA-v6.9.5-win-x64` 里实际装的是 v6.19.0，同名目录并存时目录名会误导。

## 配置文件

位置（按序探测，先命中先用）：

1. `--config PATH`
2. 环境变量 `GHUPDATE_CONFIG`
3. **`ghupdate\config.json`**（默认，便携）
4. 都没有 → 用内置默认值

优先级：**CLI 参数 > 环境变量 > config.json > 内置默认**

`config.json` 不进版本库（已 gitignore），模板见 `config.example.json`。
首次手动指定目录时会自动生成。

```jsonc
{
  "version": 1,
  "mirror": {
    // 默认 false：不替使用者选择第三方中转，也不让下载内容经过它。
    // 打开前请先读根目录《安全提醒与免责声明.md》—— 镜像站能看到你请求的
    // 地址，也有能力替换返回的内容；程序本体有官方 SHA256 兜底，资源包没有。
    "enabled": false,
    // 候选地址，按顺序尝试，命中即用。两种写法：
    //   前缀式 "https://ghfast.top/"   -> 拼成 <前缀><完整 github url>
    //   模板式 "https://x.com/{url}"   -> {url} 替换为完整 github url
    "prefixes": ["https://ghfast.top/"],
    // 镜像全挂后是否再试 GitHub 直连（26–63 KB/s，慢但能通）
    "fallback_direct": true
  },
  "install": {
    // 空 = 未指定，运行时会问你；填上后永久生效
    "maa": { "path": "" },
    "maaend": { "path": "" }
  },
  "locate": {
    // 指定目录里没有主程序时，只在它的“直接子目录”里探一层并征求确认
    "parent_probe": true
  },
  "network": { "proxy": "", "timeout": 30, "retries": 3 },
  "behavior": {
    "prune": false, "restart": false, "backup": true,
    "verify": true, "keep_residue": false
  },
  "ui": { "language": "zh-CN" }
}
```

看看当前到底生效了什么（含每项来源）：

```
update-all.bat maa --show-config
```

```
配置文件：D:\RRL\MaaUpdaterBat\ghupdate\config.json
  状态  ：已读取

  mirror.enabled             = false  [config.json]
  mirror.prefixes            = https://ghfast.top/  [config.json]
  install.maa.path           = D:\RL\MAA-v6.9.5-win-x64  [config.json]
  ...
```

`[来源]` 只会是「默认 / config.json / 环境变量 / CLI」之一，排查配置没生效时很有用。

## 镜像：默认关闭

**`mirror.enabled` 的默认值是 `false`** —— 默认直连 GitHub，不经过任何第三方
服务器。这是安全选择而非性能选择，完整理由见根目录
[`安全提醒与免责声明.md`](../安全提醒与免责声明.md)：镜像站是第三方反向代理，
能看到你请求的地址，也有能力替换返回的内容；程序本体有官方 SHA256 摘要兜底，
而 **MAA 资源包没有官方摘要**，走镜像时是否安全完全取决于你是否信任那个站。

要用镜像得自己打开：

```
update-all.bat maa --mirror https://ghfast.top/              本次启用，并加一个候选
update-all.bat maa --mirror https://a/ --mirror https://b/   多个候选
update-all.bat maa --no-mirror                               本次强制直连（覆盖配置）
```

或写进 `config.json`：把 `mirror.enabled` 改成 `true`，候选地址填在
`mirror.prefixes` 里（默认已保留 `https://ghfast.top/`）。界面里也能改：
「设置…」→ 勾选「启用镜像加速」。

> 注意：这类镜像只能代理 `github.com` 的下载直链，**代理不了 `api.github.com`**
> （实测 `ghfast.top` 返回 403）。所以「查版本 / 取 SHA256 摘要」始终走直连，
> 只有「下载更新包」走镜像。

## 目录结构

```
ghupdate\
├── update-all.bat         命令行入口（纯 ASCII，双击即用）
├── ghupdate-gui.bat       图形界面入口（自动挑带 tkinter 的解释器 + pythonw）
├── ghupdate-gui-debug.bat 同上，但保留控制台看报错（排障用）
├── ghupdate.py            中文菜单 + 分发
├── update_maa.py          MAA 本体更新器
├── update_maa_res.py      MAA 资源更新器（关卡数据 / 模板图）
├── update_maaend.py       MaaEnd 更新器
├── _common.py             共享库（HTTP/下载/校验/ZIP/备份/版本探测/配置编排）
├── core\                  纯逻辑模块（CLI 与 GUI 共用，不依赖界面）
│   ├── config.py          配置加载·合并·来源追踪·保存
│   ├── events.py          事件契约（Reporter）+ 终端实现
│   ├── locate.py          安装目录解析（4 级优先级 + 规范化 + 校验 + 一层容错）
│   └── mirror.py          镜像候选构造
├── gui\                   图形界面（Tkinter，零第三方依赖）
│   ├── app.py             主窗口（单页卡片式）+ 线程与事件循环
│   ├── reporter.py        队列桥接：把逻辑事件投给主线程
│   ├── settings.py        设置面板（镜像/目录/网络/行为）
│   └── theme.py           DPI、字体、配色
├── config.example.json    配置模板（config.json 不入库）
├── _cache\                下载缓存（*.part 支持断点续传；校验通过后成为 *.zip 可复用）
├── _backup\               更新前备份（回滚用）
└── gui-error.log          界面崩溃日志（仅在出错时生成）
```

## 它到底做了什么

### MAA（10 步）

1. 读配置 → 确定安装目录（手动指定）→ 写回配置
2. 检查 `MAA.exe` 是否在运行（在运行则拒绝）
3. 探测当前版本：读 `config/gui.new.json` → `Update.UpdatePackage`，正则解出起点版本；
   并用 `MAA.exe` 的 PE 文件版本交叉校验
4. 查最新版本：`api.maa.plus/.../version/summary.json` → `stable.json` 的 67 个资产
5. 选包：优先找 `MAAComponent-OTA-<当前>_<最新>-win-x64.zip`（增量，约 20 MB）；
   找不到则降级 `MAA-v<最新>-win-x64.zip`（全量，约 284 MB）
6. 取官方 SHA256：`api.github.com/repos/MaaAssistantArknights/MaaRelease/releases/tags/<tag>`
7. 下载：按配置展开候选列表（`<镜像前缀><完整 URL>` → … → 直连），Range 断点续传，
   每个通道失败重试 3 次后切下一个；日志里会列出完整尝试顺序
8. 校验：SHA256 与官方 `digest` 比对，**不符立即中止，不落地任何文件**
9. 备份：把「包内将覆盖的文件」+「removelist 目标」复制到 `_backup\MAA-<时间戳>\`
10. 应用：解压覆盖 → 按包内 `removelist.txt` 删旧文件 → 删除 `removelist.txt` 自身
11. 复核：重新读 `MAA.exe` 版本，确认等于目标版本

### MaaEnd（8 步）

1. 读配置 → 确定安装目录（手动指定）→ 写回配置
2. 检查 `MaaEnd.exe` 是否在运行
3. 读 `interface.json` 的 `version`（注意：`MaaEnd.exe` 的 FileVersion 是 2.7.0，**不可用**）
4. `api.github.com/repos/MaaEnd/MaaEnd/releases/latest` → `tag_name`
5. **清理 `cache\*.downloading` 残骸**（经确认；可用 `--keep-residue` 保留）
6. 下载 `MaaEnd-win-x86_64-<tag>.zip`（候选列表同上，Range 续传）
7. SHA256 与资产 `digest` 比对
8. 备份 → 解压覆盖（**包内不含 `config/`**）→ 重新读 `interface.json` 复核

### maares（7 步）

资源 = MAA 安装目录下 `resource\` 里的关卡坐标、模板图、`stages.json` 等。
它和「游戏资源」不是一回事，MAA 自己的「资源更新」按钮做的就是这件事。

1. 读配置 → 确定安装目录（与 MAA 本体共用 `install.maa.path`）
2. 检查 `MAA.exe` 是否在运行
3. 读本机 `resource\version.json` 的 `last_updated`
4. 查远端版本：`mirrorchyan.com/api/resources/MaaResource/latest`（**无需 CDK**，实测 44 ms）
   —— 版本号就是同一个字符串，直接比对
5. 下载 `github.com/MaaAssistantArknights/MaaResource/archive/refs/heads/main.zip`
   （13.5 MB，走镜像；实测 395–780 KB/s）
6. **校验**：`zipfile.testzip()` 逐条验 CRC32 → 读包内 `resource\version.json`，
   `last_updated` 必须**严格等于**远端版本，否则立即中止、不落地任何文件
7. **只写变化的文件**：逐文件按 size + CRC32 比对，变化的先备份再覆盖；
   写完后重读 `version.json` 复核

> **为什么不用 SHA256**：GitHub 的 archive 包**没有官方 digest**，而它的 ETag 经实测
> **证伪**（`cc547535…` ≠ 实际 SHA256 `c95911ab…`），不能当校验和。所以改用语义校验
> ——「包内版本必须等于远端版本」能挡住空包、错分支、截断、镜像错误页、旧缓存。
>
> **为什么不删多余文件**：包内没有 `removelist.txt`，无法判断哪些本地文件该删。
> 保守只增改、不删。实测包内 5311 个文件与本机逐字节一致时，**写入量为 0**。

## 安全性

| 事项 | 说明 |
|---|---|
| 不装证书 / 不改 hosts / 不写程序配置 | 全程只「读」配置文件 |
| 强制 SHA256 | **程序本体**的三个包官方都提供 `digest`；不符则中止且不覆盖 |
| 资源用语义校验 | 资源包没有官方摘要，改用「包内 `version.json` == 远端版本」+ zip CRC32；同样不符即中止 |
| 先备份后覆盖 | `_backup\<程序>-<时间戳>\`，整个目录复制回安装目录即可回滚 |
| 资源只改变化文件 | 逐文件 size + CRC32 比对，未变化的**一个字节都不写** |
| 不会碰用户数据 | 三个包都**不含 `config/`**；资源包也不含 `custom_infrast/`、`copilot/`、`onnx/` 等；`--prune` 还会跳过 `config/cache/debug/data/_MaaResource` |
| 版本文件最后写 | 资源写入若中途失败，`version.json` 会被**跳过**，避免被误判成「已更新」 |
| 运行时拒绝执行 | 检测到目标程序在运行会直接退出 |
| 幂等 | 已是最新则直接退出；重复运行安全 |
| 配置写入是原子替换 | 先写 `.tmp` 再 `os.replace`，不会写坏已有配置 |

### 回滚方法

```
# 例：回滚 MAA
xcopy /E /Y /I "D:\RRL\MaaUpdaterBat\ghupdate\_backup\MAA-20261015-133000\*" "D:\RL\MAA-v6.9.5-win-x64\"
```

## 已知限制

- **镜像默认关闭**（`mirror.enabled = false`），所以开箱即用的是直连：慢
  （26–63 KB/s）且可能中途断线。要提速得自己启用镜像 —— 候选地址与风险说明见
  根目录《安全提醒与免责声明.md》。`ghfast.top` 本身也可能限速或下线，届时可以
  直接换（`--mirror` 或改 `config.json`）。
- 镜像**代理不了 `api.github.com`**（返回 403），所以「查版本/取摘要」走直连
  （实测 200 / 1.8 s），只有「下载文件」走镜像。
- 磁盘：MAA 增量约需 100 MB；全量约需 600 MB；MaaEnd 全量约需 900 MB
  （下载 + 解压 + 备份）。
- 无法复刻 `MAA.Updater.exe` 的私有 update plan 协议（未公开），所以是「自己做同样的动作」，
  而官方更新器还有「父进程退出后原子替换」的能力。本工具要求你先手动关掉程序。
- 目录名不代表版本（`MAA-v6.9.5-win-x64` 里是 v6.19.0）。判断「是否最新」一律以程序内部
  版本为准，`--inspect` 也会显示真实版本。
- **资源版本的唯一来源是 mirrorchyan**。它挂了就无法拿到远端版本号，也就无法校验包，
  因此会**直接报错退出**，而不是「跳过检查硬下」。此时可稍后重试。
- **资源包不支持断点续传**（镜像与直连对 Range 都返回 200 全量）。中断就得重下 13.5 MB
  —— 约 20–35 秒，尚可接受，所以没做续传。
- 资源更新比程序更新**频繁得多**（每次游戏活动都会变），日常真正需要跑的多半是
  `maares` 而不是 `maa`。

## 环境要求

- Windows
- **命令行**：Python 3.8+（`update-all.bat` 会依次探测：托管 venv → 托管 3.13.12 →
  系统 Python 3.12/3.13/3.14 → `where python`）
- **图形界面**：还需要一个**带 tkinter 的解释器** —— tkinter 是随解释器编译进去的，
  装不上也补不齐，所以 managed Python 3.13.x（无 Tcl/Tk）**跑不了界面但能跑命令行**。
  `ghupdate-gui.bat` 会自动挑出可用的那个（见上文）
- 无需任何第三方 pip 包
