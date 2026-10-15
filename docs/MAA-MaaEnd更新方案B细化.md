# MAA / MaaEnd 更新规则分析 + 方案 B 细化设计

> 生成时间：2026-10-15 13:05
> 分析对象：`D:\RL\MAA-v6.9.5-win-x64`、`D:\RL\MaaEnd-win-x86_64-v2.23.0`
> 方法：读取程序自身日志/配置 + 二进制字符串还原 + 对官方元数据与压缩包的只读解析（ZIP 中央目录按 Range 拉取，未整包下载）
> 本文只做分析与设计，**未改动任何文件、未装证书、未动 hosts**

---

## 一、MAA 的更新规则

### 1.1 是**两条完全独立**的更新链路（这是最容易搞混的一点）

| 链路 | 负责组件 | 数据源 | 本机现状 |
|---|---|---|---|
| **① 程序本体** | `VersionUpdateDialogViewModel`（MAA.dll 内）+ `MAA.Updater.exe`（独立 C++ 进程） | `api.maa.plus` 查版本 → `stable.json` 的 assets → GitHub release 下载 | ❌ **完全失败** |
| **② 游戏资源** | `ResourceUpdater` | `api.maa.plus`（小文件 + ETag）+ `mirrorchyan.com/api/resources/MaaResource/latest` | ✅ **一直正常** |

证据：

```
gui.log  [VersionUpdateDialogViewModel] url: .../MAAComponent-OTA-v6.18.0_v6.19.0-win-x64.zip not available
gui.log  [VersionUpdateDialogViewModel] All mirrors are not available          ← 链路①
gui.log  [HttpResponseLoggingExtension] HTTP: OK GET https://mirrorchyan.com/api/resources/MaaResource/latest  133.497ms
gui.log  [ResourceUpdater] New version found: 2026-10-14+15:12:39.000, 昨日海  ← 链路② 正常
```

`resource/version.json` 的 `last_updated` = `2026-10-14 15:12:39.000` —— 与日志里"发现的版本"完全一致，说明**资源确实已经升到最新了**。

**结论：你遇到的"更新失败"，只发生在"程序本体"这条链路上。**

### 1.2 程序本体的资产命名规则（来自 `cache/version/stable.json`，共 67 个资产）

| 类型 | 命名 | 实例 | 大小 |
|---|---|---|---|
| 全量包 | `MAA-v{版本}-win-x64.zip` | `MAA-v6.19.0-win-x64.zip` | 297,639,087 B（284 MB） |
| 增量包 OTA | `MAAComponent-OTA-{起始版本}_{目标版本}-win-x64.zip` | `MAAComponent-OTA-v6.18.0_v6.19.0-win-x64.zip` | 20,515,525 B（19.6 MB） |

- OTA 覆盖**从 v6.16.0 起、一直到 v6.19.0-beta.2 的每一个起点版本**——官方为每个历史版本都准备了对应的增量包。
- **67 个资产的 `mirrors` 数组全部是 `[]`**（再次确认）→ 程序本体只有 GitHub 一条路可走。

### 1.3 本机真实版本（重要：目录名有误导）

| 项 | 值 | 来源 |
|---|---|---|
| **MAA 实际版本** | **v6.18.0** | `MAA.exe` FileVersion=6.18.0、`MAA.dll` ProductVersion=`v6.18.0+23feeddc…` |
| 目录名 `MAA-v6.9.5-win-x64` | 历史命名，**不代表版本** | — |
| 最新稳定版 | v6.19.0 | `api.maa.plus` |
| 当前待更包 | `MAAComponent-OTA-v6.18.0_v6.19.0-win-x64.zip` | `config/gui.new.json` → `Update.UpdatePackage` |
| 上次成功更新 | **2026-09-28 18:29:38** | `debug/pending-update-applier.log` 末尾 |

`MaaCore.dll` **没有 Win32 版本资源**（FileVersion 为空），所以不能靠它读版本。

### 1.4 `MAA.Updater.exe` 的工作机制（二进制字符串 + 日志还原）

它是一个**独立的 C++ 更新器**，流程如下：

```
1. MAA.exe 检测到新版本 → 下载包到安装目录 → 写 "update plan"
   → 启动 MAA.Updater.exe --mutex-name <名字> [--no-progress-ui|--show-console|--test-plan]
2. 更新器【等待父进程 MAA.exe 退出】（超时则 TerminateProcess 强杀）
3. 取互斥锁，阻止新的 MAA 实例启动
4. 解压到 NewVersionExtract\
5. 逐文件原子替换 InstallFileAtomic（被占用的文件先改名再落盘）
6. 按清单删除旧版本多余文件
7. 失败则【从备份目录回滚】
8. 重启 MAA：MAA.exe --skip-startup-auto-run
```

日志实证（`debug/pending-update-applier.log`）：
```
Deleted file: D:\RL\MAA-v6.9.5-win-x64\NewVersionExtract\resource\template\...\*.png
Relaunch command line: D:\RL\MAA-v6.9.5-win-x64\MAA.exe --skip-startup-auto-run
Relaunch succeeded.
```
且第 4 步的目录 `NewVersionExtract\` 就叫这个名字——**说明它确实是"先解压到临时目录，再对齐安装"**。

### 1.5 包内到底装了什么（只读解析 ZIP 中央目录的结果）

| 包 | 大小 | 条目数 | 顶层分布 | 根文件数 |
|---|---|---|---|---|
| MAA OTA | 19.6 MB | 680 | `resource` 667 / 根 8 / `Python` 5 | 8 |
| MAA 全量 | 284 MB | 10,748 | `resource` 10093 / `externals` 500 / `Res` 128 / 根 17 / `Python` 10 | 17 |
| MaaEnd 全量 | 295 MB | 2,695 | `resource` 2134 / `resource_adb` 386 / `tasks` 71 / `locales` 46 / `maafw` 28 / `data` 19 / 根 4 / `agent` 3 | 4 |

**MAA OTA 的 8 个根文件（就是这次要替换的全部程序文件）：**
```
filelist.txt       ← 新的全量清单（10669 行）
MAA.deps.json
MAA.dll
MAA.exe
MAA.Updater.exe
MaaCore.dll
MaaUtils.dll
removelist.txt     ← 【要删除的旧文件清单】只有 1 行：
                      resource/template/Roguelike/BlackFlow/BlackFlow@Roguelike@MovePreviewEnter.png
```

**MAA 全量比 OTA 多出的根文件**（.NET 运行时与推理库）：
```
DependencySetup_依赖库安装.bat  DirectML.dll  fastdeploy_ppocr_maa.dll
hostfxr.dll  hostpolicy.dll  MAA.runtimeconfig.json
MaaAdbControlUnit.dll  MaaWin32ControlUnit.dll  onnxruntime_maa.dll  opencv_world4_maa.dll
```

**MaaEnd 全量的 4 个根文件：** `interface.json`、`LICENSE`、`MaaEnd.exe`、`README.md`

> ✅ **决定性结论：三个包都不含 `config/`、`cache/`、`debug/` 等用户目录。**
> 也就是说，**直接解压覆盖不会破坏你的设置和登录状态**。这是方案 B 能成立的基础。

---

## 二、MaaEnd 的更新规则（对照）

| 项 | 内容 |
|---|---|
| 版本记录位置 | `interface.json` 的 `"version": "v2.30.1"`（**不是** exe 版本资源，`MaaEnd.exe` 的 FileVersion 是 2.7.0，不可用） |
| 配置位置 | `config/mxu-MaaEnd.json` → `settings.mirrorChyan = {cdk:"", channel:"stable", cdkEncrypted:""}` |
| 配置备份 | `cache/config_backup/mxu-MaaEnd-{时间戳}.json`（每次启动自动留档） |

检查更新的实际流程（`debug/2026-10-15-1.log`）：
```
检查 MaaFramework 版本... {"current":"v5.14.0","minimum":"v5.12.1","is_compatible":true}
检查更新: MaaEnd, 当前版本: v2.30.1, 频道: stable
无 CDK，尝试从 GitHub 获取版本 v2.32.0              ← 有 CDK 就走 MirrorChyan
更新检查完成: 最新版本=v2.32.0, 有更新=true
GitHub API 请求失败，尝试直接拼接下载链接
尝试直接下载链接: .../MaaEnd-win-x86_64-v2.32.0.zip
获取 GitHub Release 失败: 解析 JSON 失败: error decoding response body
检查直接下载链接失败: MaaEnd-win-x86_64-v2.32.0.zip error sending request
尝试直接下载链接: .../MaaEnd-win-x86_64-v2.32.0.exe      ← 两种后缀都试
直接下载链接也不可用
```

- 下载残骸命名规则：`{资产名}.downloading`，例如 `MaaEnd-win-x86_64-v2.31.0.zip.5.downloading`（46.9 MB，10-08 遗留）
- MaaEnd 依赖 MaaFramework（当前 v5.14.0，最低 v5.12.1），`maafw/` 目录随包更新

---

## 三、可复用的可达性清单（2026-10-15 实测）

| 目标 | 结果 | 方案 B 中的用途 |
|---|---|---|
| `api.maa.plus/.../version/summary.json` | **200, 0.23 s** | MAA 查版本 ✅ |
| `api.github.com/repos/...` | **200, 1.79 s** | MaaEnd 查版本 + 取官方 SHA256 ✅ |
| `mirrorchyan.com/api/...` | 200, 0.29 s | MAA 资源（链路②，本来就通） |
| `end.maafw.com` | 200, 0.24 s | MaaEnd 公告 |
| `ghfast.top/https://github.com/...` | **200, 669 KB/s – 2.24 MB/s** | 下载主通道 ⚠️ 速度波动 |
| `ghfast.top/https://api.github.com/...` | **403** | ❌ 镜像只能代理 github.com，代理不了 API |
| 直连 `release-assets.githubusercontent.com` | 63 KB/s | 兜底通道 |

**已验证的端到端下载（MAA OTA 增量包）：**
```
经 ghfast.top 下载 20,515,525 B，耗时 30.7 s
本地 SHA256  0dd03078e71ef6f2e55a1114c470fe36933e59d64a82ac515e68d717a4d4fed5
官方 digest sha256:0dd03078e71ef6f2e55a1114c470fe36933e59d64a82ac515e68d717a4d4fed5
→ 逐字符一致 ✅
```

三个包官方**都提供 digest**，方案 B 可强制校验：

| 包 | 官方 SHA256 |
|---|---|
| `MAA-v6.19.0-win-x64.zip` | `51463ce5cbcb37b85c1e3a5bd3fb11d7a33f4607a2c65578b96297366629b73a` |
| `MAAComponent-OTA-v6.18.0_v6.19.0-win-x64.zip` | `0dd03078e71ef6f2e55a1114c470fe36933e59d64a82ac515e68d717a4d4fed5` |
| `MaaEnd-win-x86_64-v2.32.0.zip` | `f335b1c260f8719bf4e527519ee64026c8c2aeb80f462aac58abbb5d2a671328` |

---

## 四、方案 B 细化设计

### 4.1 设计原则

1. **零系统改动**：不装证书、不改 hosts、不改程序配置文件（只**读**配置用于版本探测）
2. **不复刻 `MAA.Updater.exe` 的私有协议**（update plan 未公开、风险高），而是自己完成「下载 → 校验 → 解压覆盖 → 应用 removelist」，这也正是官方 `Python/asst/updater.py` 的历史做法
3. **强制 SHA256 校验**：下载完成、解压之前必须与官方 digest 比对
4. **先备份、可回滚**
5. **幂等**：重复运行安全，已是最新则直接退出

### 4.2 目录结构

```
D:\RRL\MaaUpdaterBat\ghupdate\
├── update_maa.py        # MAA 更新器（含版本探测/选包/下载/校验/解压/清单应用）
├── update_maaend.py     # MaaEnd 更新器
├── update-all.bat       # 入口：菜单选择 MAA / MaaEnd / 全部 / 仅检查
├── README.md            # 中文说明 + 回滚方法
├── _cache\              # 下载缓存（*.part 支持断点续传；校验通过后自动删除）
└── _backup\<时间戳>\    # 每次更新前的备份（可手动复制回来回滚）
```

### 4.3 MAA 更新流程（10 步）

| 步 | 动作 | 说明 |
|---|---|---|
| 1 | **进程检查** | 若 `MAA.exe` 在运行 → 拒绝执行（运行时 DLL 被占用，替换必失败）。提示先关闭 |
| 2 | **探测当前版本** | 首选：读 `config/gui.new.json` → `Configurations.Default.Update.UpdatePackage`，正则 `OTA-(.+)_(.+)-win-x64\.zip` 取起点 = 当前版本。备选：读 `MAA.exe` 的 FileVersion |
| 3 | **交叉校验** | `Update.Name` 必须等于最新版本号；不一致说明配置过期 → **直接改用全量包**（不猜） |
| 4 | **查最新版本** | `api.maa.plus/.../version/summary.json` → `stable.version` + `stable.detail` → 拉 detail 的 `stable.json` 拿 assets 列表 |
| 5 | **选包** | 优先在 assets 中找 `MAAComponent-OTA-v{当前}_{最新}-win-x64.zip`；找不到 → 降级 `MAA-v{最新}-win-x64.zip` |
| 6 | **下载** | `https://ghfast.top/https://github.com/...`，Range 续传到 `_cache\*.part`；失败重试 3 次，仍失败回退直连（63 KB/s 兜底） |
| 7 | **校验** | 从 `api.github.com/.../releases/tags/{tag}` 取 `digest` → 比对 SHA256。**不符立即中止，不落地任何文件** |
| 8 | **备份** | 把「包内将覆盖的文件」+「removelist 目标」复制到 `_backup\{时间戳}\`（OTA 约 20 MB，全量约 284 MB） |
| 9 | **应用** | ① `zipfile.extractall(安装目录)` 覆盖；② 若有 `removelist.txt` → 逐行删除对应文件；③ 删除 `removelist.txt` 自身 |
| 10 | **校验** | 重新读 `MAA.exe` FileVersion，确认等于目标版本 |

**可选第 11 步（默认关闭，需 `--prune`）**：按包内新 `filelist.txt`（10669 行）删除多余文件，范围**仅限** `resource/`、`externals/`、`Res/`、`Python/` 及根目录中"清单内的文件"，**绝不触碰** `config/`、`cache/`、`debug/`、`data/`、`_MaaResource/`、`NewVersionExtract/`。

### 4.4 MaaEnd 更新流程（8 步）

| 步 | 动作 |
|---|---|
| 1 | 检查 `MaaEnd.exe` 是否在运行 |
| 2 | 读 `interface.json` 的 `version` 得到当前版本 |
| 3 | `api.github.com/repos/MaaEnd/MaaEnd/releases/latest` → `tag_name` |
| 4 | **先清理 `cache\*.downloading` 残骸**（含那个 46.9 MB 的 v2.31.0 遗留） |
| 5 | 下载 `MaaEnd-win-x86_64-{tag}.zip`（经 ghfast.top，Range 续传） |
| 6 | SHA256 与 digest 比对 |
| 7 | 备份 `config/`；解压覆盖（包内不含 `config/`） |
| 8 | 重新读 `interface.json` 的 `version` 校验 |

### 4.5 边界情况与应对

| 情况 | 处理 |
|---|---|
| ghfast.top 限速/挂掉 | 重试 3 次（退避）→ 回退直连 → 仍失败则保留 `.part`，下次续传 |
| SHA256 不符 | 立即中止；不覆盖、不解压（校验发生在 `_cache` 内） |
| 程序正在运行 | 拒绝执行，提示关闭 |
| 目录名与真实版本不符 | 一律以 `MAA.exe` FileVersion / `interface.json` 为准 |
| 少见的起点版本（如 beta/alpha） | 找不到对应 OTA → 自动降级全量包 |
| 磁盘空间 | OTA 约需 100 MB；全量约需 600 MB（下载 + 解压 + 备份） |
| 想回滚 | 把 `_backup\{时间戳}\` 整个复制回安装目录 |
| MaaEnd 的 `data/`、`resource/` | 属于**随包内容**，会按官方行为覆盖（与它自己的更新器一致） |

### 4.6 与方案 A′（即用即停代理）的关系

- 方案 B **完全独立**，不需要代理、不需要证书、不碰信任库
- 若两者都要：B 的下载步骤可以把地址从 `ghfast.top` 换成 `127.0.0.1:8899`，但**没有必要**——B 直接用 ghfast.top 已经够用
- **建议顺序**：先上方案 B（零系统改动，先把版本升上去、验证可行），之后若仍想要"程序内点一下就更新"的体验，再考虑 A′

### 4.7 待你确认的点

- [ ] 是否需要 `--prune`（按新 filelist 全量对齐、清理废弃文件）
- [ ] 更新完成后是否**自动启动**对应程序
- [ ] MaaEnd 那个 46.9 MB 的 `.downloading` 残骸，方案 B 默认会清掉——同意吗
- [ ] 是否需要"只检查不更新"的干跑模式（`--check`）

---

## 五、一句话总结

MAA 的「资源更新」一直是通的，**坏的只有「程序本体」那一条**，而它坏的原因是官方元数据里 67 个 `mirrors` 全为空、只剩 GitHub 一条路。
方案 B 的做法是：**绕开它的更新器，自己经 ghfast.top 把包拉下来、用官方 SHA256 校验、解压覆盖、并按包里的 `removelist.txt` 删旧文件**——三个包都不含 `config/`，所以不会动你的设置。已实测下载 + 校验闭环通过。
