# ghupdate —— MAA / MaaEnd 本体更新器（方案 B）

> 生成时间：2026-10-15
> 目标程序：`D:\RL\MAA-v6.9.5-win-x64`（MAA，实际版本 v6.18.0）、`D:\RL\MaaEnd-win-x86_64-v2.23.0`（MaaEnd）
> 关联文档：`D:\RRL\MaaUpdaterBat\docs\MAA-MaaEnd更新加速计划.md`、`D:\RRL\MaaUpdaterBat\docs\MAA-MaaEnd更新方案B细化.md`

## 为什么需要它

MAA 与 MaaEnd 的**程序本体更新**只能走 GitHub。本机到 GitHub 的**文件分发通道**被限速到
26–63 KB/s 且长连接会被中途 RST（`github.com:443` 直连干脆不可达）；MAA 官方元数据里
**67 个 `mirrors` 数组全为空**，三个官方 CDN 已移除。所以程序内点「检查更新」几乎必然失败。

本工具**绕开程序自带的更新器**，自己完成：

```
查版本 -> 选包(优先增量) -> 经 ghfast.top 镜像下载 -> SHA256 校验
       -> 备份 -> 解压覆盖 -> 应用 removelist -> 版本复核
```

**零系统改动**：不装证书、不改 hosts、不写任何程序配置文件（只「读」配置用于探测版本）。

## 快速开始

双击 **`update-all.bat`** 打开中文菜单，选 `1` 先干跑看看会做什么，再选 `2`/`3`/`4` 执行。

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
| `--check` | 只检查不下载（干跑） |
| `--prune` | **仅 MAA**：按新 `filelist.txt` 清理废弃程序文件（默认关闭） |
| `--restart` | 更新完成后启动程序 |
| `-y` | 不再交互确认 |
| `--no-backup` | 跳过备份（不建议） |
| `--no-verify` | 无官方摘要时仍继续（不建议） |
| `--proxy URL` | 显式代理，如 `http://127.0.0.1:7890` |
| `--install DIR` | 手动指定安装目录 |
| `--channel` | **仅 MAA**：`stable`（默认）/ `beta` / `alpha` |

## 目录结构

```
ghupdate\
├── update-all.bat      入口（纯 ASCII，双击即用）
├── ghupdate.py         中文菜单 + 分发
├── update_maa.py       MAA 更新器
├── update_maaend.py    MaaEnd 更新器
├── _common.py          共享库（HTTP/下载/校验/ZIP/备份/版本探测）
├── _cache\             下载缓存（*.part 支持断点续传；校验通过后成为 *.zip 可复用）
└── _backup\            更新前备份（回滚用）
```

## 它到底做了什么

### MAA（10 步）

1. 检查 `MAA.exe` 是否在运行（在运行则拒绝）
2. 探测当前版本：读 `config/gui.new.json` → `Update.UpdatePackage`，正则解出起点版本；
   并用 `MAA.exe` 的 PE 文件版本交叉校验
3. 查最新版本：`api.maa.plus/.../version/summary.json` → `stable.json` 的 67 个资产
4. 选包：优先找 `MAAComponent-OTA-<当前>_<最新>-win-x64.zip`（增量，约 20 MB）；
   找不到则降级 `MAA-v<最新>-win-x64.zip`（全量，约 284 MB）
5. 取官方 SHA256：`api.github.com/repos/MaaAssistantArknights/MaaRelease/releases/tags/<tag>`
6. 下载：`https://ghfast.top/https://github.com/...`，Range 断点续传，失败重试 3 次后回退直连
7. 校验：SHA256 与官方 `digest` 比对，**不符立即中止，不落地任何文件**
8. 备份：把「包内将覆盖的文件」+「removelist 目标」复制到 `_backup\MAA-<时间戳>\`
9. 应用：解压覆盖 → 按包内 `removelist.txt` 删旧文件 → 删除 `removelist.txt` 自身
10. 复核：重新读 `MAA.exe` 版本，确认等于目标版本

### MaaEnd（8 步）

1. 检查 `MaaEnd.exe` 是否在运行
2. 读 `interface.json` 的 `version`（注意：`MaaEnd.exe` 的 FileVersion 是 2.7.0，**不可用**）
3. `api.github.com/repos/MaaEnd/MaaEnd/releases/latest` → `tag_name`
4. **清理 `cache\*.downloading` 残骸**（经确认；可用 `--keep-residue` 保留）
5. 下载 `MaaEnd-win-x86_64-<tag>.zip`（经 ghfast.top，Range 续传）
6. SHA256 与资产 `digest` 比对
7. 备份 → 解压覆盖（**包内不含 `config/`**）
8. 重新读 `interface.json` 复核

## 安全性

| 事项 | 说明 |
|---|---|
| 不装证书 / 不改 hosts / 不写程序配置 | 全程只「读」配置文件 |
| 强制 SHA256 | 三个包官方都提供 `digest`；不符则中止且不覆盖 |
| 先备份后覆盖 | `_backup\<程序>-<时间戳>\`，整个目录复制回安装目录即可回滚 |
| 不会碰用户数据 | 三个包都**不含 `config/`**；`--prune` 也会跳过 `config/cache/debug/data/_MaaResource` |
| 运行时拒绝执行 | 检测到目标程序在运行会直接退出 |
| 幂等 | 已是最新则直接退出；重复运行安全 |

### 回滚方法

```
# 例：回滚 MAA
xcopy /E /Y /I "D:\RRL\MaaUpdaterBat\ghupdate\_backup\MAA-20261015-133000\*" "D:\RL\MAA-v6.9.5-win-x64\"
```

## 已知限制

- 依赖第三方镜像 `ghfast.top`，它可能限速或下线。失败时脚本会自动回退直连（63 KB/s 兜底）。
- `ghfast.top` **代理不了 `api.github.com`**（返回 403），所以「查版本/取摘要」走直连
  （实测 200 / 1.8 s），只有「下载文件」走镜像。
- 磁盘：MAA 增量约需 100 MB；全量约需 600 MB；MaaEnd 全量约需 900 MB
  （下载 + 解压 + 备份）。
- 无法复刻 `MAA.Updater.exe` 的私有 update plan 协议（未公开），所以是「自己做同样的动作」，
  而官方更新器还有「父进程退出后原子替换」的能力。本工具要求你先手动关掉程序。

## 环境要求

- Windows
- Python 3.8+（脚本会依次探测：托管 venv → 托管 3.13.12 → 系统 Python 3.12/3.13/3.14 → `where python`）
- 无需第三方 pip 包
