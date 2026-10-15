# ghupdate —— MAA / MaaEnd 本体更新器（方案 B）

> 生成时间：2026-10-15
> 目标程序：`D:\RL\MAA-v6.9.5-win-x64`（MAA，实测版本 v6.19.0）、
> `D:\RL\MaaEnd-win-x86_64-v2.23.0`（MaaEnd，实测版本 v2.32.0）
> 关联文档：`..\docs\` 下的 `MAA-MaaEnd更新加速计划.md`、`MAA-MaaEnd更新方案B细化.md`、
> `ghupdate-可配置化与GUI规划.md`

## 为什么需要它

MAA 与 MaaEnd 的**程序本体更新**只能走 GitHub。本机到 GitHub 的**文件分发通道**被限速到
26–63 KB/s 且长连接会被中途 RST（`github.com:443` 直连干脆不可达）；MAA 官方元数据里
**67 个 `mirrors` 数组全为空**，三个官方 CDN 已移除。所以程序内点「检查更新」几乎必然失败。

本工具**绕开程序自带的更新器**，自己完成：

```
查版本 -> 选包(优先增量) -> 经镜像下载(可配置) -> SHA256 校验
       -> 备份 -> 解压覆盖 -> 应用 removelist -> 版本复核
```

**零系统改动**：不装证书、不改 hosts、不写任何程序配置文件（只「读」配置用于探测版本）。

## 快速开始

双击 **`update-all.bat`** 打开中文菜单：

```
   1. 仅检查更新（干跑，不下载任何文件）
   2. 更新 MAA
   3. 更新 MaaEnd
   4. 更新全部（MAA + MaaEnd）
   5. 更改安装目录 / 查看配置
   6. 查看用法 / 高级选项
   0. 退出
```

菜单顶部会显示当前镜像与两个程序的安装目录名。**首次运行**如果还没指定过目录，
会直接问你要路径（可直接把文件夹从资源管理器拖进窗口），校验通过后自动记住。

命令行同样可用：

```
update-all.bat                        打开菜单
update-all.bat check                  两个都干跑（不下载任何东西）
update-all.bat maa                    更新 MAA
update-all.bat maaend                 更新 MaaEnd
update-all.bat all                    先 MAA 再 MaaEnd
update-all.bat maa --prune --restart  更新 MAA，清理废弃文件并启动
```

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

**解析优先级（命中即用）**

| 级别 | 来源 | 说明 |
|---|---|---|
| 1 | `--install PATH` | 命令行，最高优先级 |
| 2 | `GHUPDATE_INSTALL_MAA` / `GHUPDATE_INSTALL_MAAEND` | 环境变量 |
| 3 | `config.json` → `install.maa.path` / `install.maaend.path` | 持久生效 |
| 4 | 交互式询问 | 控制台里问你；输入合法则写回配置 |

**路径会被自动规范化**（这些写法都能认）：

| 你的输入 | 处理结果 |
|---|---|
| `"D:\RL\MAA-v6.9.5-win-x64" ` | 去掉引号与首尾空格 |
| `D:/RL/MAA-v6.9.5-win-x64/` | 正斜杠、尾部反斜杠 |
| `D:\RL\MAA-v6.9.5-win-x64\MAA.exe` | 直接填 exe 文件 → 取所在目录 |
| `%USERPROFILE%\Desktop\MAA` | 展开环境变量 |
| `D:\Rel` | 目录不存在 → 报错 |

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
    "enabled": true,
    // 按顺序尝试，命中即用。两种写法：
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

  mirror.enabled             = true  [config.json]
  mirror.prefixes            = https://ghfast.top/  [config.json]
  install.maa.path           = D:\RL\MAA-v6.9.5-win-x64  [config.json]
  ...
```

`[来源]` 只会是「默认 / config.json / 环境变量 / CLI」之一，排查配置没生效时很有用。

## 换镜像

镜像列表化之后，`ghfast.top` 挂了不必改代码。三种改法：

```
update-all.bat maa --mirror https://新的镜像/            只本次
update-all.bat maa --mirror https://a/ --mirror https://b/   多个候选
update-all.bat maa --no-mirror                           本次直接直连
```

或写进 `config.json` 的 `mirror.prefixes` 数组。

> 注意：这类镜像只能代理 `github.com` 的下载直链，**代理不了 `api.github.com`**
> （实测 `ghfast.top` 返回 403）。所以「查版本 / 取 SHA256 摘要」始终走直连，
> 只有「下载更新包」走镜像。

## 目录结构

```
ghupdate\
├── update-all.bat         入口（纯 ASCII，双击即用）
├── ghupdate.py            中文菜单 + 分发
├── update_maa.py          MAA 更新器
├── update_maaend.py       MaaEnd 更新器
├── _common.py             共享库（HTTP/下载/校验/ZIP/备份/版本探测/配置编排）
├── core\                  纯逻辑模块（CLI 与将来的 GUI 共用）
│   ├── config.py          配置加载·合并·来源追踪·保存
│   ├── locate.py          安装目录解析（4 级优先级 + 规范化 + 校验 + 一层容错）
│   └── mirror.py          镜像候选构造
├── config.example.json    配置模板（config.json 不入库）
├── _cache\                下载缓存（*.part 支持断点续传；校验通过后成为 *.zip 可复用）
└── _backup\               更新前备份（回滚用）
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

## 安全性

| 事项 | 说明 |
|---|---|
| 不装证书 / 不改 hosts / 不写程序配置 | 全程只「读」配置文件 |
| 强制 SHA256 | 三个包官方都提供 `digest`；不符则中止且不覆盖 |
| 先备份后覆盖 | `_backup\<程序>-<时间戳>\`，整个目录复制回安装目录即可回滚 |
| 不会碰用户数据 | 三个包都**不含 `config/`**；`--prune` 也会跳过 `config/cache/debug/data/_MaaResource` |
| 运行时拒绝执行 | 检测到目标程序在运行会直接退出 |
| 幂等 | 已是最新则直接退出；重复运行安全 |
| 配置写入是原子替换 | 先写 `.tmp` 再 `os.replace`，不会写坏已有配置 |

### 回滚方法

```
# 例：回滚 MAA
xcopy /E /Y /I "D:\RRL\MaaUpdaterBat\ghupdate\_backup\MAA-20261015-133000\*" "D:\RL\MAA-v6.9.5-win-x64\"
```

## 已知限制

- 默认镜像 `ghfast.top` 可能限速或下线 —— 现在**可以直接换**（`--mirror` 或改 `config.json`），
  全部失效时会自动回退直连（63 KB/s 兜底）。
- 镜像**代理不了 `api.github.com`**（返回 403），所以「查版本/取摘要」走直连
  （实测 200 / 1.8 s），只有「下载文件」走镜像。
- 磁盘：MAA 增量约需 100 MB；全量约需 600 MB；MaaEnd 全量约需 900 MB
  （下载 + 解压 + 备份）。
- 无法复刻 `MAA.Updater.exe` 的私有 update plan 协议（未公开），所以是「自己做同样的动作」，
  而官方更新器还有「父进程退出后原子替换」的能力。本工具要求你先手动关掉程序。
- 目录名不代表版本（`MAA-v6.9.5-win-x64` 里是 v6.19.0）。判断「是否最新」一律以程序内部
  版本为准，`--inspect` 也会显示真实版本。

## 环境要求

- Windows
- Python 3.8+（脚本会依次探测：托管 venv → 托管 3.13.12 → 系统 Python 3.12/3.13/3.14 → `where python`）
- 无需第三方 pip 包
