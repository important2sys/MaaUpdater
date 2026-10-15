# ghproxy — MAA / MaaEnd 更新加速「即用即停」套件

> ⚠️ **第三方非官方工具**，与 MAA / MaaEnd 开发组没有隶属关系。
> 本方案会生成一个本地 CA 并**临时装入你的用户级信任库**（退出时还原），
> 风险高于默认的 `ghupdate` 方案 —— 请先读根目录
> [`安全提醒与免责声明.md`](../安全提醒与免责声明.md) 再决定是否使用。

> 用途：把 MAA / MaaEnd 访问 `github.com` 的下载请求，在本地拦截并回源到国内可用的
> GitHub 加速镜像（默认 `ghfast.top`），从而把 63 KB/s 提到 ~2.2 MB/s。
> **不常驻、不驻留证书、不改配置文件** —— 用完即走。

---

## 一、为什么是「即用即停」

方案 A 原本的顾虑是「要往系统装一个根证书」。本套件把它拆成了三件可逆的事：

| 组件 | 生存期 | 退出时 |
|---|---|---|
| 代理进程（127.0.0.1:8899） | 从启动到程序关闭 | 进程被杀，端口释放 |
| 本地根证书（当前用户 Root 库） | 从启动到程序关闭 | `certutil -delstore` 卸载 |
| 程序代理设置 | —— | **不写任何配置文件**，只用环境变量，进程结束即失效 |

三处清理全部自动执行；`ghproxy.py` 自己也会在退出（含 Ctrl+C、异常）时读
`ca_installed.flag` 并调用 `certutil -delstore` 卸载证书 —— 双保险。
万一整个脚本被强杀，双击 `restore.bat` 即可幂等还原。

---

## 二、快速开始

### 只想给 MAA 用
双击 **`run-maa.bat`**。
它会：装证书 → 起代理 → 带 `HTTP_PROXY/HTTPS_PROXY` 启动 MAA → MAA 关闭后自动停代理并卸证书。

### 只想给 MaaEnd 用
双击 **`run-maaend.bat`**（流程同上）。

### 想手动控制
```bat
ghproxy-ctl.bat start      :: 装证书 + 起代理（此后自己手动开程序）
ghproxy-ctl.bat status     :: 查看代理端口与证书状态
ghproxy-ctl.bat stop       :: 停代理 + 卸证书
```

手动模式下，程序需要知道代理地址。两种办法（任选）：
1. 启动程序前在同一个 cmd 窗口里设环境变量：
   ```bat
   set HTTP_PROXY=http://127.0.0.1:8899
   set HTTPS_PROXY=http://127.0.0.1:8899
   set NO_PROXY=localhost,127.0.0.1
   ```
2. 或在程序设置里填代理 `http://127.0.0.1:8899`（MAA 侧：`config/gui.json` 的
   `VersionUpdate.Proxy`；MaaEnd 侧：设置里的代理地址）。

---

## 三、文件说明

| 文件 | 作用 |
|---|---|
| `ghproxy.py` | 拦截代理本体。**纯 Python 标准库，无第三方依赖** |
| `ghproxy-ctl.bat` | 主控：`start` / `stop` / `status` / `install-ca` / `remove-ca` |
| `run-maa.bat` | 一键：MAA 全流程（含自动清理） |
| `run-maaend.bat` | 一键：MaaEnd 全流程（含自动清理） |
| `restore.bat` | 应急幂等还原：停代理 + 卸证书 |
| `gen-certs.bat` | 重新生成本地 CA 与 `github.com` 叶证书（需 openssl） |
| `certs/` | CA 与叶证书、CA 指纹文件 |
| `ghproxy.log` | 运行日志（每次请求一行，含速度） |

---

## 四、工作原理

```
MAA / MaaEnd
     |  ①  环境变量 HTTP_PROXY/HTTPS_PROXY 生效
     v
127.0.0.1:8899  (ghproxy.py)
     |
     ├─ CONNECT github.com:443   → 用本地 CA 签发的证书终结 TLS，
     |                             把路径改写为 https://ghfast.top/https://github.com/<原路径>
     |                             流式回传，完整支持 Range 断点续传
     |
     └─ CONNECT 其他域名          → 纯 TCP 透传，不解密、不干预
```

关键点：
- 只监听 `127.0.0.1`，不对局域网暴露。
- 默认**只拦截 `github.com` 一个域名**（`--hosts` 可调）。其余流量原样透传。
- 镜像站自己处理 github.com → release-assets.githubusercontent.com 的 302 跳转，
  所以不需要再拦截第二个域名。
- 请求不落盘、不缓存，纯流式转发。

---

## 五、实测数据（2026-10-15，全部为真实跑通结果）

| 项目 | 直连 GitHub | 经本代理 |
|---|---|---|
| 下载 release 附件速度 | 26 – 63 KB/s | **2.24 MB/s（20 MB 分片）/ 3.27 MB/s（完整包）** |
| 20 MB 分片 | 常超时中断 | **9.1 秒**（`206 Partial Content`） |
| **295 MB 完整包** | 约 80 分钟且几乎必然断链 | **94.6 秒** |
| Range 断点续传 | 常被 RST | 正常返回 206 |
| 其他域名（api.maa.plus / mirrorchyan） | 正常 | 正常（纯透传，200） |

**完整性校验（最关键的一项）** —— 经代理下载的 295 MB 完整包：

```
官方 GitHub digest : sha256:f335b1c260f8719bf4e527519ee64026c8c2aeb80f462aac58abbb5d2a671328
本代理下载结果      : sha256:f335b1c260f8719bf4e527519ee64026c8c2aeb80f462aac58abbb5d2a671328
字节数              : 309,547,928 == 309,547,928
```

结论：**逐字节一致，镜像未篡改、未截断、无静默损坏。**

---

## 五之二、运行前提（已在你的机器上验证）

- Python 标准库即可，**不需要 pip 安装任何第三方包**（本机 PyPI 当时不可达）。
- `certutil` 与当前用户 Root 库的读写**均不需要管理员权限**（已验证可访问，未写入）。
- 证书生成依赖 `openssl` —— 本机 `C:\Program Files\Git\usr\bin\openssl.exe`（OpenSSL 3.5.7）。
  生成的 `certs/` 已随本套件提供，日常运行**不需要**再调用 openssl。

---

## 六、验证与回滚

**验证是否干净**（应输出 CA 不存在）：
```bat
ghproxy-ctl.bat status
```
或手动查：
```bat
certutil -store -user Root | findstr /i "RRL"
```
（正常应无任何输出。）

**完全卸载本套件**：
```bat
restore.bat
```
然后直接删除整个 `ghproxy` 目录即可。系统不留任何残留 —— 证书、hosts、全局配置
全程未被修改（唯一动过的是「当前用户 → 受信任的根证书颁发机构」这一项，且每次用完即卸）。

**CA 指纹**（卸载用的标识）：
```
E348D7F96684F6C8A9F8F42E0DA2519C96748B34
```

---

## 七、你必须知道的三件事

1. **装证书时可能弹一次 Windows 安全警告。** 往 Root 存储导入证书时，
   系统可能弹出「是否安装此证书」的确认框，需要点「是」。这是 Windows 的
   防滥用设计，无法绕过。也就是说「即用即停」每次运行会带来**一次点击**。

2. **本地 CA 的能力边界。** 这个 CA 在技术上能签发任意域名的证书，
   但本套件的实现**只对 `github.com` 生效**，其余域名一律透传不解密。
   装证书 = 临时信任一个本地 CA，你应当知道这一点。用完即卸就是为了把
   这个窗口压到最短。

3. **`ghfast.top` 是第三方公益镜像**，随时可能限速或下线。今天它是唯一可用的
   （其余 12 个镜像全部失败）。这是**临时手段，不是长久之计**。
   若它失效，可换 `--upstream` 或改用 MirrorChyan CDK。

---

## 八、常见问题

**Q：为什么 MAA 里还是慢？**
先看 `ghproxy.log` 有没有出现 `MITM github.com` 行。没有的话，说明程序没用上代理 ——
检查它是被 `run-maa.bat` 启动的，或者手动设了代理指向 `127.0.0.1:8899`。

**Q：MaaEnd 提示证书错误？**
MaaEnd 用的是 rustls + `rustls-platform-verifier`（走 Windows 证书库），理论上信任本
CA。若报错，优先改用它的 MirrorChyan CDK 通道，或改用一键脚本方案手动替换。

**Q：代理起不来？**
`ghproxy-ctl.bat status` 看端口；`ghproxy.log` 看原因。常见是 8899 被占用，
换端口：`ghproxy.py --port 8898`，并同步改 `run-*.bat` 里的 `PORT`。

**Q：怎么彻底不用了？**
`restore.bat` → 删除整个 `ghproxy` 目录。结束。
