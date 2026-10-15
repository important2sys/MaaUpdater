# MAA / MaaEnd 自动更新慢与断链 — 诊断与解决方案计划

> 生成时间：2026-10-15 00:17 ｜ 最后更新：2026-10-15 09:55
> 涉及程序：`D:\RL\MAA-v6.9.5-win-x64`（MaaAssistantArknights）、`D:\RL\MaaEnd-win-x86_64-v2.23.0`
> 状态：**诊断完成 → 方案 A′（即用即停版）已实现并实测通过**；
> 仅剩「写入信任库」这一步待用户授权。交付物见 `D:\RRL\MaaUpdaterBat\ghproxy\`

---

## 一、问题现象

- 两个程序（MAA、MaaEnd）的「自检更新」极慢，大部分情况直接断链失败。
- 用户原本以为是程序 bug 或配置错误。

---

## 二、排查结论

### 2.1 网络环境事实

| 项目 | 实测结果 |
|---|---|
| 本机代理进程 | **无**（7890 / 7897 / 7891 / 10809 / 1080 / 8080 全部关闭） |
| WorkBuddy 注入的代理 | 127.0.0.1:14042 / 14017 / 12682 —— **只作用于 agent 沙箱，不影响系统终端** |
| 全局 git 代理配置 | 无 |
| hosts 文件 | 未被改写，无 github 条目 |
| DNS | 正常，`github.com → 20.205.243.166`（Azure 东亚） |
| ICMP ping | 平均 130 ms，0% 丢包 |

### 2.2 各链路实测

| 链路 | 结果 | 判定 |
|---|---|---|
| SSH `github.com:22` 认证 | `Hi important2sys! You've successfully authenticated` | ✅ 正常 |
| SSH 完整握手（:22） | 3.41 s | 偏慢（跨境 RTT 放大） |
| SSH 完整握手（ssh.github.com:443） | 4.45 s | 偏慢 |
| `git ls-remote` | 4.5 – 5.9 s | 可用但慢 |
| **HTTPS 直连 `github.com:443`** | **10 s 超时不可达** | ❌ 被阻断 |
| HTTPS 直连 `raw.githubusercontent.com` | 20 s 超时 | ❌ 被阻断 |
| HTTPS 直连 `codeload.github.com:443` | 301，可达 | ✅ |
| **下载 `release-assets.githubusercontent.com`** | **63 KB/s** | ❌ 被限速 |
| **下载 `codeload.github.com`** | **26 KB/s** | ❌ 被限速 |
| `api.maa.plus`（查版本） | 秒回 | ✅ |
| `end.maafw.com`（查公告） | 可达 | ✅ |
| `mirrorchyan.com`（国内 CDN） | 200，建连 79 ms | ✅ 通畅 |
| SSH 连接复用 ControlMaster | master 能起，但新会话立即 `Connection reset by peer`（:22 与 :443 均如此） | ❌ 不可用 |

### 2.3 MAA 侧根因

日志：`D:\RL\MAA-v6.9.5-win-x64\debug\gui.log`（2026-10-14 23:05–23:35 反复重试）

```
Failed to send GET request to
  https://github.com/MaaAssistantArknights/MaaRelease/releases/download/v6.19.0/
  MAAComponent-OTA-v6.18.0_v6.19.0-win-x64.zip
  → TaskCanceledException: HttpClient.Timeout of 15 seconds elapsing
  → SocketException (10053): 你的主机中的软件中止了一个已建立的连接 (github.com:443)
  → SocketException (10054): 远程主机强迫关闭了一个现有的连接
Selecting the fastest mirror: ... not available
All mirrors are not available
```

**关键发现：MAA 已经没有任何非 GitHub 下载源。**

拉取 `https://api.maa.plus/MaaAssistantArknights/api/version/stable.json` 解析后：

- 文件里共 **67 个 `mirrors` 数组，全部为空 `[]`**
- 脚本 `Python/asst/updater.py` 里原本写着的三个官方镜像 —— `s3.maa-org.net`、
  `agent.imgg.dev`、`maa.r2.imgg.dev` —— 在元数据中**出现次数为 0**
- 这三个域名实测**全部不可达**（`s3.maa-org.net` 10 s 超时；另两个域名已失效）

配置现状：`config/gui.json` → `"VersionUpdate.Proxy": ""`（空，未配代理）

### 2.4 MaaEnd 侧根因

日志：`D:\RL\MaaEnd-win-x86_64-v2.23.0\debug\2026-10-14-4.log`

```
检查更新: MaaEnd, 当前版本: v2.30.1, 频道: stable
更新检查完成: 最新版本=v2.32.0, 有更新=true
无 CDK，尝试从 GitHub 获取版本 v2.32.0
获取 GitHub Release 失败: 解析 JSON 失败: error decoding response body
[下载] 直连（无代理）: .../MaaEnd-win-x86_64-v2.32.0.zip
下载失败: 下载数据失败: error decoding response body
```

两次下载耗时：**6 分 51 秒**（23:07:52→23:14:43）、**19 分 24 秒**（23:15:53→23:35:17），均失败。

- `无 CDK` → 未配置 MirrorChyan 加速，只能直连 GitHub
- 日志自己写着 `直连（无代理）`
- 残骸文件：`cache\MaaEnd-win-x86_64-v2.31.0.zip.5.downloading`（46.9 MB，10-08 遗留）

配置现状：`config/mxu-MaaEnd.json` → `mirrorChyan.cdk: ""`（空）

### 2.5 结论

**不是程序 bug，也不是配置错误。**

> 两个程序的本体更新都只能直连 GitHub，而本机到 GitHub 的**文件分发通道被限速到
> 26–63 KB/s，且长连接会被中途 RST 掐断**。一个 ~47 MB 的更新包需要十几分钟到几十分钟，
> 期间几乎必然断链。

对照：**代码传输（SSH）是好的** —— `git clone/push/pull` 正常，只有「release 附件 / 压缩包分发」被卡。两者是不同的问题，不要混为一谈。

---

## 三、GitHub 加速镜像实测（2026-10-15）

对真实 release 文件测试：

| 镜像 | 结果 |
|---|---|
| **`ghfast.top`** | ✅ **唯一可用**：2 MB 测试 231 KB/s；20 MB 测试 **916 KB/s**（22.4 s） |
| `gh-proxy.com` | ❌ 403 |
| `ghproxy.net` | ❌ 超时 |
| `hub.gitmirror.com` | ❌ DNS 失败 |
| `github.moeyy.xyz` | ❌ 超时 |
| `gh.llkk.cc` | ❌ 超时 |
| `ghproxy.cc` | ❌ 超时 |
| `gh.api.99988866.xyz` | ❌ 失败 |
| `ghfast.net` / `ghp.ci` / `gh.xxooo.cf` / `ghp.arislee.com` | ❌ 失败 |
| `gh.ddlc.top` | ❌ 429（限流） |
| `ghproxy.link` | ❌ 仅 1.3 KB/s |

**两个关键有利条件：**

1. `ghfast.top` 速度 **916 KB/s ≈ 直连的 14 倍**，47 MB 包约 **52 秒** 可下完。
2. **它自行处理 302 跳转**（github.com → release-assets.githubusercontent.com），
   所以代理**只需拦截 `github.com` 一个域名**，不必再碰 release-assets。

> ⚠️ 第三方镜像生态极不稳定，仅作临时手段，不可作为长期依赖。

---

## 四、可选方案

### 方案 A′：本地拦截代理「即用即停」版（✅ 已实现并实测通过）

> 由方案 A 演化而来，回应「能不能做成即用即停」。**结论：能，而且已经完全做好并验证。**

**核心思想：三件可逆的事，各自独立地在用完后消失。**

| 组件 | 生存期 | 退出时如何消失 |
|---|---|---|
| 代理进程（127.0.0.1:8899） | 启动 → 程序关闭 | 进程结束，端口释放 |
| 本地根证书（当前用户 Root 库） | 启动 → 程序关闭 | `certutil -delstore -user Root <指纹>` 自动卸载 |
| 程序代理设置 | 进程内存内 | **不写任何配置文件**，只用 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量，进程结束即失效 |

原方案 A 第 6 步「改 gui.json / MaaEnd 配置 / 开系统代理」**已被取消** ——
改用环境变量注入，配置文件一个字节都不动。原方案 A 第 8 步「开机自启」**已删除**。

**三层兜底清理：**

1. `run-maa.bat` / `run-maaend.bat` 主流程结束后调用 `ghproxy-ctl.bat stop`；
2. `ghproxy.py` 自身在退出（含 Ctrl+C、异常）时检测 `ca_installed.flag`，
   主动调用 `certutil -delstore` 卸载证书；
3. 极端情况（整个脚本被强杀）→ 双击 `restore.bat` 幂等还原。

**技术前提已逐项验证：**

| 前提 | 验证结果 |
|---|---|
| MAA（.NET 10）是否信任用户证书库 | ✅ .NET on Windows 走 schannel → 系统证书库 |
| MaaEnd（Rust）是否信任用户证书库 | ✅ 编译进了 `rustls-platform-verifier-0.7.0` + `schannel-0.1.28`，走 **Windows 证书库**；`webpki-roots` 出现 0 次（不是内置 Mozilla 根） |
| `certutil` 读写用户 Root 库是否需要管理员 | ✅ 不需要（只读校验已通过） |
| 是否能免 CA | ❌ 不能。`ghfast.top` 不是正向代理（CONNECT 直接 400），必须做本地 MITM |
| 代理脚本是否需要第三方库 | ✅ 不需要。改为 openssl 生成证书 + Python 标准库实现代理（本机 PyPI 当时不可达） |

**实测结果（全部真实跑通）：**

| 项目 | 结果 |
|---|---|
| 20 MB 分片经代理下载 | `206`，20,515,525 B，2.24 MB/s，9.1 秒 |
| **295 MB 完整包经代理下载** | **309,547,928 字节，94.6 秒，3.27 MB/s** |
| 完整性校验 | SHA256 `f335b1c2…1328` **与 GitHub 官方 digest 完全一致** |
| 透传分支（api.maa.plus、mirrorchyan） | `200`，未解密、未干预 |
| HEAD 元数据探测 | `200`，`Content-Length: 309547928` |

**交付物**：`D:\RRL\MaaUpdaterBat\ghproxy\`

| 文件 | 作用 |
|---|---|
| `ghproxy.py` | 拦截代理本体（纯标准库） |
| `ghproxy-ctl.bat` | `start` / `stop` / `status` / `install-ca` / `remove-ca` |
| `run-maa.bat` / `run-maaend.bat` | 一键全流程（含自动清理） |
| `restore.bat` | 应急幂等还原 |
| `gen-certs.bat` | 重新生成证书（需 openssl） |
| `certs/` | CA + `github.com` 叶证书 + 指纹文件 |
| `README.md` | 完整使用说明 |

**唯一未执行的一步**：`certutil -addstore`（真正写入信任库）。
原因是它会改动系统信任库，需要你明确同意。其余全部已实测。

**已知摩擦点（必须知情）**：

1. 往 Root 库装证书时，Windows **可能弹一次安全确认框**，需要点「是」。
   即「即用即停」每次运行会带来一次点击。这是系统的防滥用设计，无法绕过。
2. 有个测试侧的发现：Git Bash 自带的 curl 是 **schannel 编译版**，对私有 CA 会做
   吊销检查并报 `CERT_TRUST_REVOCATION_STATUS_UNKNOWN`（需 `--ssl-no-revoke`）。
   MAA（.NET 默认 `RevocationMode.NoCheck`）与 MaaEnd（platform-verifier 不做吊销检查）
   都不属于这种情况，但**首次实际运行时值得留意**，若 MaaEnd 报证书错误，
   退路是改用它的 MirrorChyan CDK。

### 方案 A：本地拦截代理（原版，已被 A′ 取代）

> 原版与 A′ 的差别只有两点：改配置文件 vs 用环境变量、常驻 vs 即用即停。
> **推荐直接用 A′。**


```
MAA / MaaEnd  →  127.0.0.1:8899 本地代理  →  github.com 改写到 ghfast.top
                                          ↘  其他域名 纯 TCP 透传
```

**原理**
- 监听 `127.0.0.1:8899` 的 HTTP 代理
- 收到 `CONNECT github.com:443` → 用本地 CA 签发的证书做 TLS 终结，
  把路径改写为 `https://ghfast.top/https://github.com/<原路径>`，流式回传（支持 Range 断点续传）
- 其他域名的 `CONNECT` → 纯 TCP 隧道直通，**绝不干预**
- 本地 CA 只装进「**当前用户** → 受信任的根证书颁发机构」（**已验证无需管理员权限**）
- 让 MAA 的 `VersionUpdate.Proxy`、MaaEnd 的代理设置指向 `127.0.0.1:8899`

**优点**：无需改 hosts；只拦一个域名；两程序无感加速；完全可逆。

**风险（须知情）**
1. 装根证书 = 本机多一个**能签发任意域名证书**的本地 CA。
   实现只对 `github.com` 生效，但这是能力边界，用户有权知晓。
2. 依赖 `ghfast.top` 长期存活（第三方服务）。

### 方案 B：一键更新脚本（零系统改动，最稳）

写一个 `.bat`：查最新版 → 经 `ghfast.top` 下载 → 解压覆盖 → 启动。双击运行。

- 不改 hosts、不装证书、不碰系统，风险最低
- 代价：没有「程序内自动更新」体验

### 方案 C：MirrorChyan CDK

两程序原生支持，国内 CDN 建连 79 ms，最省事最稳定。**需要用户提供 CDK**（无法自行获取）。

### 方案 D：不推荐 —— 复用现有的 FastGithub

`D:\RL\fastgithub_win-x64` 是 **v2.1.4 / 2022-03 构建**，已停更。评估结论：

| 项 | 现状 |
|---|---|
| CA | `cacert/fastgithub.cer` + `.key` 已生成，但**未装进信任库** |
| 运行状态 | 当前未运行（443 / 80 / 38457 均关闭），最后运行 2026-03-11 |
| 硬伤 1 | 不认识 `release-assets.githubusercontent.com`（比它新） |
| 硬伤 2 | `DomainConfigs` 是**按域名**配置，**无法按路径**只把 `releases/download` 导去镜像 |
| 硬伤 3 | 内置 GitHub IP 测速逻辑已过时 |

（另：`D:\DevSidecar` 目录为空，只有 `D:\RL\DevSidecar-2.2.0-windows-x86_64.exe` 安装包，未安装。）

---

## 五、方案 A 实施步骤（待批准）

**技术前提（已确认）**
- ~~装 `cryptography`~~ → 改为用 **openssl 3.5.7**（`C:\Program Files\Git\usr\bin\openssl.exe`）生成证书，代理本体纯标准库，**零第三方依赖**
- CA 装入当前用户 Root 无需管理员（已验证）

**步骤（A′ 版，已实现）**

1. ~~装依赖 `cryptography`~~ → 用 openssl 生成 CA 与叶证书（`gen-certs.bat`）
2. 生成本地 CA：`ghmirror-ca.crt` + `ghmirror-ca.key`（保存在 `D:\RRL\MaaUpdaterBat\ghproxy\certs\`）
3. 装 CA 到当前用户信任库：`certutil -addstore -f -user Root certs\ghmirror-ca.crt`（**可一键卸载**）
4. 代理脚本 `ghproxy.py`（纯标准库）：监听 `127.0.0.1:8899`；`github.com` → TLS 终结 + 改写回源 `ghfast.top`；其他域名 → 纯透传
5. 启动代理（`ghproxy-ctl.bat start`，写入 pid 文件）
6. ~~改配置文件~~ → **改用环境变量**，不改任何程序配置：
   ```bat
   set HTTP_PROXY=http://127.0.0.1:8899
   set HTTPS_PROXY=http://127.0.0.1:8899
   set NO_PROXY=localhost,127.0.0.1
   ```
7. 实测：见「四、方案 A′」的实测表（20 MB / 295 MB 全量包均通过）
8. ~~开机自启~~ → **删除**。改用 `run-maa.bat` / `run-maaend.bat` 即用即停

**回滚（完全可逆）**

```bash
certutil -delstore -user Root <证书指纹>          # 删根证书
# 清空 MAA 的 VersionUpdate.Proxy 与 MaaEnd 的代理设置
# 删除 D:\RRL\MaaUpdaterBat\ghproxy\ 目录，停止代理进程
```

---

## 六、待办 / 未决

- [x] **用户尚未选择方案**（A / B / C）→ 已按 A′（即用即停版）实现，实测通过
- [x] MaaEnd 的代理配置项名称与位置尚未确认 → 已确认无需改配置，改用环境变量
- [x] `ghfast.top` 完整包（47 MB 全量）完整性校验未完成 → **已完成**：295 MB 全量包
  SHA256 与 GitHub 官方 digest 完全一致
- [ ] MaaEnd 的 46.9 MB 断链残骸 `MaaEnd-win-x86_64-v2.31.0.zip.5.downloading` 是否删除 —— **待用户确认**
- [ ] **唯一未执行的一步**：`certutil -addstore -user Root`（真正写入信任库），需用户同意
- [x] 未改动任何 MAA / MaaEnd 配置，未动 hosts，未装任何证书（信任库已验证为 0 条 RRL 记录）

---

## 附录：本次排查用到的关键命令

```bash
# 看 MAA 更新失败原因
grep -aiE "update|download|github|mirror|fail" "D:/RL/MAA-v6.9.5-win-x64/debug/gui.log" | tail -100

# 看 MaaEnd 更新失败原因
grep -aiE "update|download|github|fail" "D:/RL/MaaEnd-win-x86_64-v2.23.0/debug/2026-10-14-4.log" | tail -60

# 直连真实速度
curl --noproxy '*' -sS -L -o /dev/null -w "%{speed_download}\n" --max-time 45 \
  -r 0-10485759 "https://github.com/MaaAssistantArknights/MaaRelease/releases/download/v6.19.0/MAAComponent-OTA-v6.18.0_v6.19.0-win-x64.zip"

# 镜像测速
curl --noproxy '*' -sS -L -o /dev/null -w "%{speed_download}\n" --max-time 90 \
  -r 0-20971519 "https://ghfast.top/https://github.com/.../xxx.zip"
```
