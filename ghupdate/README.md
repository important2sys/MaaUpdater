# ghupdate —— MAA / MaaEnd 更新器

`ghupdate` 是 MaaUpdaterBat 的功能主体，覆盖三条相互独立的更新链路：

| 链路 | 对象 | 子命令 |
|---|---|---|
| ① | MAA 程序本体 | `maa` |
| ② | MAA 资源（关卡数据 / 模板图） | `maares` |
| ③ | MaaEnd 程序本体 | `maaend` |

它绕开程序自带的更新器，自行完成「查版本 → 选包 → 下载 → 校验 → 备份 → 覆盖 →
复核」。**零系统改动**：不安装证书、不修改 hosts、不写入任何程序自身的配置文件
（仅「读」配置以探测版本）。

> **第三方非官方工具**，与 MAA / MaaEnd 开发组没有隶属关系。
> **默认直连 GitHub，不经过任何第三方服务器**；如需启用镜像加速，请先阅读
> [`../安全提醒与免责声明.md`](../安全提醒与免责声明.md)。

相关文档：[`../README.md`](../README.md)（项目总览）、
[`../docs/技术说明.md`](../docs/技术说明.md)（官方机制与实测数据）。

---

## 一、快速开始

### 命令行

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

菜单顶部显示当前镜像状态、两个程序的安装目录，以及 MAA 资源的当前版本。首次运行时
若尚未指定目录，会直接询问路径（支持将文件夹从资源管理器拖入窗口），校验通过后自动
记录。

子命令形式同样可用：

```
update-all.bat                        打开菜单
update-all.bat check                  三条链路全部干跑（不下载任何文件）
update-all.bat maa                    更新 MAA 程序本体
update-all.bat maares                 更新 MAA 资源
update-all.bat maaend                 更新 MaaEnd
update-all.bat all                    本体 -> 资源 -> MaaEnd 依次更新
update-all.bat maa --with-resource    本体 + 资源，一条命令执行完毕
update-all.bat maa --prune --restart  更新 MAA，清理废弃文件并启动
```

> **`maares` 使用哪个目录？** 与 MAA 本体相同 —— 资源位于安装目录下的 `resource\`，
> 因此复用 `install.maa.path`，无需单独配置。

### 图形界面

双击 **`ghupdate-gui.bat`**，在同一窗口内查看全部状态：

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

- **检查更新** —— 仅查询版本，不下载。MAA 卡片会**同时**查询程序与资源，状态徽章取
  两者综合结论（最常见的情形正是「程序已最新、资源已过期」）
- **立即更新** —— 与命令行完全相同的流程（下载 → 校验 → 备份 → 覆盖 → 复核），执行
  前弹出一次确认框，过程中进度条与日志实时刷新
- **更新资源** —— 仅执行资源链路，同样走完整的下载 / 校验 / 备份 / 写入
- **设置…** —— 镜像地址、安装目录、代理、超时与重试、更新通道、备份 / 校验 / 重启等
  全部开关
- **查看配置** —— 等价于 `--show-config`，含每一项的来源

图形界面与命令行**共用同一份 `config.json`**。界面调用的是 `update_maa.main()` /
`update_maa_res.main()` / `update_maaend.main()`，而非另写一套逻辑，因此不会出现
「界面可用而命令行不可用」之类的差异。

#### 关于解释器选择

本机 managed Python（3.13.x）**未编译 Tcl/Tk**，`import tkinter` 会失败。因此
`ghupdate-gui.bat` 按序探测 `%MAAUPD_PYTHON%` → `%LOCALAPPDATA%\Programs\Python\
Python3*` → `%APPDATA%\uv\python\cpython-*` → `PATH`，对每个候选执行
`import tkinter` 验证，取第一个可用者。全部不可用时会列出探测过的位置并提示修复方法，
**不影响命令行使用**。

同时提供 **`ghupdate-gui-debug.bat`**（保留控制台以查看 traceback，用于排查）。两者
均会把崩溃信息追加至 `ghupdate\gui-error.log`。

---

## 二、命令行选项

| 选项 | 作用 |
|---|---|
| `--install DIR` | 指定安装目录（含 `MAA.exe` / `MaaEnd.exe` 的文件夹）；校验通过后写入配置 |
| `--no-save` | 配合 `--install`：仅本次生效，不写入配置 |
| `--inspect [DIR]` | 检查目录是否为安装目录，并列出子目录候选（不做任何改动） |
| `--forget-install [maa\|maaend\|all]` | 清除已保存的安装路径 |
| `--mirror URL` | 覆盖镜像前缀，可重复传入以形成候选列表 |
| `--no-mirror` | 本次禁用镜像，直连 GitHub |
| `--config PATH` | 指定配置文件（默认 `ghupdate\config.json`） |
| `--show-config` | 打印当前生效配置（含每项来源）后退出 |
| `--check` | 仅检查不下载（干跑） |
| `--with-resource` | **仅 MAA**：本体更新完成后接着更新资源 |
| `--force` | **仅 maares**：版本号相同时仍逐文件比对并补齐差异（用于修复残缺的本地资源） |
| `--prune` | **仅 MAA**：按新 `filelist.txt` 清理废弃的程序文件（默认关闭） |
| `--restart` | 更新完成后启动程序 |
| `-y` | 不再交互确认 |
| `--no-backup` | 跳过备份（不建议） |
| `--no-verify` | 无官方摘要时仍继续（不建议） |
| `--proxy URL` | 显式代理，例如 `http://127.0.0.1:7890` |
| `--channel` | **仅 MAA**：`stable`（默认）/ `beta` / `alpha` |

---

## 三、安装目录解析

本工具**不做自动定位**。设计契约为：

> **要么使用指定目录，要么明确报错 —— 绝不静默回退到其他目录。**

自动探测的风险在于「猜错后仍静默更新正确副本之外的目录」，因此决策权交回使用者；
代价是失败时必须说明「尝试过哪些、为何不可用、可能的候选是什么」。

### 3.1 优先级

| 级别 | 来源 | 类别 | 说明 |
|---|---|---|---|
| 1 | `--install PATH` | **显式** | 命令行，最高优先级 |
| 2 | `GHUPDATE_INSTALL_MAA` / `GHUPDATE_INSTALL_MAAEND` | **显式** | 环境变量 |
| 3 | `config.json` → `install.*.path` | 隐式默认值 | 持久生效 |
| 4 | 交互式询问 | — | 输入合法则写回配置 |

**显式来源一旦给出即以其为准。** `--install` 或环境变量指定的目录若不可用，将直接
报错退出，**不会退回使用 `config.json` 中保存的目录** —— 否则可能出现「以为在更新 A、
实际改动了 B」的情况。如需改回已保存的目录，去掉 `--install`（或清除环境变量）后
重新运行。

`config.json` 属隐式默认值，失效时允许被交互输入覆盖。

### 3.2 路径规范化

以下写法均被识别：

| 输入 | 处理结果 |
|---|---|
| `"D:\RL\MAA-v6.9.5-win-x64" ` | 去除引号与首尾空格 |
| `D:/RL/MAA-v6.9.5-win-x64/` | 正斜杠、尾部反斜杠 |
| `D:\RL\MAA-v6.9.5-win-x64\MAA.exe` | 直接填 exe 文件 → 取所在目录 |
| `%USERPROFILE%\Desktop\MAA` | 展开环境变量 |
| `D:\RL`（父目录） | 一层容错：询问「使用下面那个吗」；非交互时直接报错 |
| `D:\RRL\MaaUpdaterBat` | 非安装目录 → 报错，并列出目录内容供判断 |

### 3.3 一层子目录容错

配置项 `locate.parent_probe`（默认开启、可关闭）。若指定目录本身不是安装目录，但其
**直接子目录**中存在唯一候选，则询问「是否使用该目录」。这不是全盘扫描，仅用于拦截
「顺手填入 `D:\RL`」这类常见输入错误。

非交互模式（`-y` 或管道重定向）下**不会**自动采用任何候选，只会报错。关闭该行为：
配置中设 `"locate": { "parent_probe": false }`。

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

最后一项版本号读自 `MAA.exe` 的真实 PE 版本，而非目录名。本机目录名
`MAA-v6.9.5-win-x64` 中实际安装的是 v6.19.0，目录名可能误导。

---

## 四、配置文件

位置按序探测，先命中先用：

1. `--config PATH`
2. 环境变量 `GHUPDATE_CONFIG`
3. **`ghupdate\config.json`**（默认，便携）
4. 均无 → 内置默认值

优先级：**CLI 参数 > 环境变量 > config.json > 内置默认**

`config.json` 不入版本库，模板见 `config.example.json`。首次手动指定目录时自动生成。

```jsonc
{
  "version": 1,
  "mirror": {
    // 默认 false：不替使用者选择第三方中转，也不让下载内容流经它。
    // 启用前请先阅读根目录《安全提醒与免责声明.md》—— 镜像站能看到请求的
    // 地址，也有能力替换返回的内容；程序本体有官方 SHA256 兜底，资源包没有。
    "enabled": false,
    // 候选地址按顺序尝试，命中即用。两种写法：
    //   前缀式 "https://ghfast.top/"   -> 拼成 <前缀><完整 github url>
    //   模板式 "https://x.com/{url}"   -> {url} 替换为完整 github url
    "prefixes": ["https://ghfast.top/"],
    // 镜像全部失败后是否再试 GitHub 直连（26–63 KB/s，较慢但可通）
    "fallback_direct": true
  },
  "install": {
    // 空 = 未指定，运行时询问；填写后永久生效
    "maa": { "path": "" },
    "maaend": { "path": "" }
  },
  "locate": {
    // 指定目录内无主程序时，仅在其“直接子目录”中探查一层并征求确认
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

查看当前生效的配置及各项来源：

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

`[来源]` 只会是「默认 / config.json / 环境变量 / CLI」之一，排查配置未生效时较为
有用。

---

## 五、镜像

**`mirror.enabled` 的默认值为 `false`** —— 默认直连 GitHub，不经过任何第三方服务器。
这是基于安全的默认选择而非性能选择，完整理由见
[`../安全提醒与免责声明.md`](../安全提醒与免责声明.md)：镜像站是第三方反向代理，能够
看到请求地址，也有能力替换返回内容；程序本体有官方 SHA256 摘要兜底，而 **MAA 资源包
没有官方摘要**，此时安全性完全取决于是否信任该镜像站。

启用方式（任选其一）：

```
update-all.bat maa --mirror https://ghfast.top/              本次启用，并追加一个候选
update-all.bat maa --mirror https://a/ --mirror https://b/   多个候选
update-all.bat maa --no-mirror                               本次强制直连（覆盖配置）
```

或在 `config.json` 中将 `mirror.enabled` 改为 `true`，候选地址填入
`mirror.prefixes`（默认已保留 `https://ghfast.top/`）。亦可在界面中修改：
「设置…」→ 勾选「启用镜像加速」。

> 此类镜像仅能代理 `github.com` 的下载直链，**无法代理 `api.github.com`**（实测
> `ghfast.top` 返回 403）。因此「查版本 / 取 SHA256 摘要」始终走直连，仅「下载更新包」
> 经镜像。

---

## 六、更新流程

### 6.1 MAA 程序本体

1. 读配置 → 确定安装目录（手动指定）→ 写回配置
2. 检查 `MAA.exe` 是否运行（运行中则拒绝）
3. 探测当前版本：读 `config/gui.new.json` 的 `Update.UpdatePackage`，正则解出起点
   版本；并以 `MAA.exe` 的 PE 文件版本交叉校验
4. 查最新版本：`api.maa.plus/.../version/summary.json` → `stable.json` 的 67 个资产
5. 选包：优先 `MAAComponent-OTA-<当前>_<最新>-win-x64.zip`（增量，约 20 MB）；
   若无则降级为 `MAA-v<最新>-win-x64.zip`（全量，约 284 MB）
6. 取官方 SHA256：`api.github.com/repos/MaaAssistantArknights/MaaRelease/releases/
   tags/<tag>`
7. 下载：按配置展开候选列表（`<镜像前缀><完整 URL>` → … → 直连），支持 Range 断点
   续传，每条通道失败重试 3 次后切换下一条；日志中列出完整尝试顺序
8. 校验：SHA256 与官方 `digest` 比对，**不符立即中止，不落地任何文件**
9. 备份：将「包内将覆盖的文件」与「removelist 目标」复制至 `_backup\MAA-<时间戳>\`
10. 应用：解压覆盖 → 按包内 `removelist.txt` 删除旧文件 → 删除 `removelist.txt` 自身
11. 复核：重新读取 `MAA.exe` 版本，确认等于目标版本

### 6.2 MaaEnd

1. 读配置 → 确定安装目录（手动指定）→ 写回配置
2. 检查 `MaaEnd.exe` 是否运行
3. 读 `interface.json` 的 `version`（注意：`MaaEnd.exe` 的 FileVersion 为 2.7.0，不可用）
4. 查最新版本：`api.github.com/repos/MaaEnd/MaaEnd/releases/latest` → `tag_name`
5. 清理 `cache\*.downloading` 残骸（经确认；可用 `--keep-residue` 保留）
6. 下载 `MaaEnd-win-x86_64-<tag>.zip`（候选列表同上，支持 Range 续传）
7. SHA256 与资产 `digest` 比对
8. 备份 → 解压覆盖（**包内不含 `config/`**）→ 重新读取 `interface.json` 复核

### 6.3 MAA 资源（maares）

资源指 MAA 安装目录下 `resource\` 内的关卡坐标、模板图、`stages.json` 等，与「游戏
资源」无关。MAA 自带的「资源更新」按钮执行的即为该流程。

1. 读配置 → 确定安装目录（与 MAA 本体共用 `install.maa.path`）
2. 检查 `MAA.exe` 是否运行
3. 读本机 `resource\version.json` 的 `last_updated`
4. 查远端版本：`mirrorchyan.com/api/resources/MaaResource/latest`（**无需 CDK**）
   —— 版本号即同一字符串，直接比对
5. 下载 `github.com/MaaAssistantArknights/MaaResource/archive/refs/heads/main.zip`
   （13.5 MB，经镜像）
6. **校验**：`zipfile.testzip()` 逐条验证 CRC32 → 读包内 `resource\version.json`，
   其 `last_updated` 必须**严格等于**远端版本，否则立即中止、不落地任何文件
7. **仅写入变化的文件**：逐文件按 `size` + CRC32 比对，变化的先备份再覆盖；写完后
   重读 `version.json` 复核

> **为何不用 SHA256**：GitHub 的 archive 包**没有官方 digest**，其 ETag 经实测已
> **证伪**（`cc547535…` ≠ 实际 SHA256 `c95911ab…`），不能作为校验和。因此改用语义
> 校验 ——「包内版本必须等于远端版本」可拦截空包、错分支、下载截断、镜像错误页与旧
> 缓存。
>
> **为何不删除多余文件**：包内没有 `removelist.txt`，无法判断哪些本地文件应当删除。
> 保守策略是只增改、不删除。实测包内 5,311 个文件与本机逐字节一致时，**写入量为 0**。

---

## 七、安全性

| 事项 | 说明 |
|---|---|
| 不装证书 / 不改 hosts / 不写程序配置 | 全程仅「读」配置文件 |
| 强制 SHA256 | **程序本体**的三个包官方均提供 `digest`；不符则中止且不覆盖 |
| 资源用语义校验 | 资源包无官方摘要，改用「包内 `version.json` == 远端版本」+ zip CRC32；不符即中止 |
| 先备份后覆盖 | 备份至 `_backup\<程序>-<时间戳>\`，将整个目录复制回安装目录即可回滚 |
| 资源只改变化文件 | 逐文件 `size` + CRC32 比对，未变化的文件**一个字节都不写** |
| 不触碰用户数据 | 三个包**均不含 `config/`**；资源包亦不含 `custom_infrast/`、`copilot/`、`onnx/` 等；`--prune` 还会跳过 `config/cache/debug/data/_MaaResource` |
| 版本文件最后写 | 资源写入若中途失败，`version.json` 会被**跳过**，避免被误判为「已更新」 |
| 运行时拒绝执行 | 检测到目标程序运行中会直接退出 |
| 幂等 | 已是最新则直接退出；重复运行安全 |
| 配置写入为原子替换 | 先写 `.tmp` 再 `os.replace`，不会损坏已有配置 |

### 回滚方法

```
# 例：回滚 MAA
xcopy /E /Y /I "D:\RRL\MaaUpdaterBat\ghupdate\_backup\MAA-20261015-133000\*" "D:\RL\MAA-v6.19.0-win-x64\"
```

---

## 八、目录结构

```
ghupdate\
├── update-all.bat         命令行入口（纯 ASCII，双击即用）
├── ghupdate-gui.bat       图形界面入口（自动挑选带 tkinter 的解释器 + pythonw）
├── ghupdate-gui-debug.bat 同上，但保留控制台以查看报错（排查用）
├── ghupdate.py            中文菜单与子命令分发
├── update_maa.py          MAA 本体更新器
├── update_maa_res.py      MAA 资源更新器
├── update_maaend.py       MaaEnd 更新器
├── _common.py             共享库（HTTP / 下载 / 校验 / ZIP / 备份 / 版本探测 / 配置编排）
├── core\                  纯逻辑模块（CLI 与 GUI 共用，不依赖界面）
│   ├── config.py          配置加载·合并·来源追踪·保存
│   ├── events.py          事件契约（Reporter）与终端实现
│   ├── locate.py          安装目录解析（4 级优先级 + 规范化 + 校验 + 一层容错）
│   └── mirror.py          镜像候选构造
├── gui\                   图形界面（Tkinter，零第三方依赖）
│   ├── app.py             主窗口（单页卡片式）+ 线程与事件循环
│   ├── reporter.py        队列桥接：将逻辑事件投递给主线程
│   ├── settings.py        设置面板（镜像 / 目录 / 网络 / 行为）
│   └── theme.py           DPI、字体、配色
├── config.example.json    配置模板（config.json 不入库）
├── _cache\                下载缓存（*.part 支持断点续传；校验通过后成为 *.zip 可复用）
├── _backup\               更新前备份（回滚用）
└── gui-error.log          界面崩溃日志（仅在出错时生成）
```

---

## 九、已知限制

- **镜像默认关闭**（`mirror.enabled = false`），因此开箱即用的是直连通道：较慢
  （26–63 KB/s）且可能中途断线。如需提速须自行启用镜像，候选地址与风险说明见
  [`../安全提醒与免责声明.md`](../安全提醒与免责声明.md)。`ghfast.top` 本身也可能
  限速或下线，届时可直接更换（`--mirror` 或修改 `config.json`）。
- 镜像**无法代理 `api.github.com`**（返回 403），因此「查版本 / 取摘要」走直连
  （实测 200 / 1.8 s），仅「下载文件」经镜像。
- 磁盘占用：MAA 增量包约需 100 MB；MAA 全量包约需 600 MB；MaaEnd 全量包约需 900 MB
  （含下载、解压与备份）。
- 无法复刻 `MAA.Updater.exe` 的私有 update plan 协议（未公开），因此是「自行完成同样
  的动作」。官方更新器另具备「父进程退出后原子替换」的能力，本工具要求先手动关闭
  程序。
- 目录名不代表版本（`MAA-v6.9.5-win-x64` 中为 v6.19.0）。判断「是否已是最新」一律以
  程序内部版本为准，`--inspect` 亦显示真实版本。
- **资源版本的唯一来源是 mirrorchyan**。该服务不可用即无法获取远端版本号，也就无法
  校验资源包，因此会**直接报错退出**，而非「跳过检查强行下载」。可稍后重试。
- **资源包不支持断点续传**（镜像与直连对 Range 请求均返回 200 全量）。中断后需重新
  下载 13.5 MB，约 20–35 秒，故未实现续传。
- 资源更新比程序本体更新**频繁得多**（每次游戏活动都会变化），日常真正需要执行的多为
  `maares` 而非 `maa`。

---

## 十、环境要求

- **Windows**
- **命令行**：Python 3.8+。`update-all.bat` 按序探测托管 venv → 托管 3.13.x →
  系统 Python 3.12/3.13/3.14 → `where python`
- **图形界面**：另需一个**带 tkinter 的解释器**。tkinter 随解释器编译，无法通过
  `pip` 补装，因此 managed Python 3.13.x（无 Tcl/Tk）无法运行界面、但可运行命令行。
  `ghupdate-gui.bat` 会自动挑选可用者
- 无需任何第三方 pip 包
