#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ghproxy.py —— GitHub 更新加速用的本地拦截代理（零第三方依赖，仅用标准库）

设计原则
--------
1. 只监听 127.0.0.1，绝不对外暴露。
2. 只拦截白名单域名（默认仅 github.com）；其余域名一律纯 TCP 透传，绝不干预。
3. 被拦截域名的请求，改写为「镜像站 + 原 URL」回源（默认 ghfast.top），
   完整支持 Range 断点续传与流式回传，不落盘、不缓存。
4. 即用即停：进程启动时写入 pid 文件，退出（含 Ctrl+C / 异常）时清理；
   若检测到「证书已安装」标记，退出时自动把根证书从「当前用户」库中卸载。

用法
----
    python ghproxy.py                     # 默认 127.0.0.1:8899
    python ghproxy.py --port 8899
    python ghproxy.py --upstream https://ghfast.top
    python ghproxy.py --hosts github.com,codeload.github.com
    python ghproxy.py --idle-timeout 1800 # 30 分钟无请求自动退出
"""

import argparse
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
from http.client import HTTPConnection, HTTPSConnection

HERE = os.path.dirname(os.path.abspath(__file__))
CERT_DIR = os.path.join(HERE, "certs")
CA_CRT = os.path.join(CERT_DIR, "ghmirror-ca.crt")
LEAF_CRT = os.path.join(CERT_DIR, "github.crt")
LEAF_KEY = os.path.join(CERT_DIR, "github.key")
PID_FILE = os.path.join(HERE, "ghproxy.pid")
FLAG_CA_INSTALLED = os.path.join(HERE, "ca_installed.flag")
LOG_FILE = os.path.join(HERE, "ghproxy.log")

DEFAULT_HOSTS = "github.com"
DEFAULT_UPSTREAM = "https://ghfast.top"

MAX_REDIRECTS = 5
CHUNK = 64 * 1024
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 120

_log_lock = threading.Lock()
_last_activity = time.time()

# 自身监听地址，用于防止代理把请求回环给自己造成自连接
SELF_ADDR = ("127.0.0.1", 8899)
HEALTH_PATH = "/__ghmirror_health"


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    with _log_lock:
        print(line, flush=True)
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def touch_activity():
    global _last_activity
    _last_activity = time.time()


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f TB" % n


# --------------------------------------------------------------------------
# 上游请求：跟随跳转 + 流式返回
# --------------------------------------------------------------------------
FORWARD_HEADERS = ("range", "if-range", "if-none-match", "if-modified-since",
                   "user-agent", "accept")

RESP_HEADERS = ("content-type", "content-length", "content-range", "accept-ranges",
                "etag", "last-modified", "content-disposition", "date", "vary")


def _connect(url):
    u = urllib.parse.urlsplit(url)
    host = u.hostname
    if u.scheme == "https":
        conn = HTTPSConnection(host, u.port or 443, timeout=CONNECT_TIMEOUT)
    else:
        conn = HTTPConnection(host, u.port or 80, timeout=CONNECT_TIMEOUT)
    target = u.path or "/"
    if u.query:
        target += "?" + u.query
    return conn, target


def open_upstream(url, method, headers):
    """返回 (conn, resp)。自动跟随 3xx 跳转。响应体尚未读取，由调用方流式消费。"""
    hops = 0
    while True:
        u = urllib.parse.urlsplit(url)
        if (u.hostname, u.port or (443 if u.scheme == "https" else 80)) == SELF_ADDR:
            raise IOError("拒绝回环到自身代理: %s" % url)
        conn, target = _connect(url)
        hdrs = dict(headers)
        hdrs["Connection"] = "close"
        # Host 由 http.client 依目标主机自动填写，避免把 github.com 带过去
        hdrs.pop("Host", None)
        hdrs.pop("host", None)
        try:
            conn.request(method, target, headers=hdrs)
            resp = conn.getresponse()
        except Exception:
            conn.close()
            raise

        if resp.status in (301, 302, 303, 307, 308) and hops < MAX_REDIRECTS:
            loc = resp.getheader("Location")
            try:
                resp.read()
            except Exception:
                pass
            conn.close()
            if not loc:
                raise IOError("3xx without Location from %s" % url)
            url = urllib.parse.urljoin(url, loc)
            hops += 1
            if resp.status == 303:
                method = "GET"
            log("  -> redirect(%d) %s" % (resp.status, url[:150]))
            continue
        return conn, resp


# --------------------------------------------------------------------------
# 请求解析 / 响应回写
# --------------------------------------------------------------------------
def read_request(rfile):
    """从二进制流读一个 HTTP/1.x 请求，返回 (method, target, headers) 或 None。"""
    line = rfile.readline(65536)
    if not line:
        return None
    try:
        parts = line.decode("latin-1").strip().split()
        method, target = parts[0], parts[1]
    except (UnicodeDecodeError, IndexError):
        return None
    headers = {}
    while True:
        hl = rfile.readline(65536)
        if not hl or hl in (b"\r\n", b"\n"):
            break
        try:
            k, _, v = hl.decode("latin-1").partition(":")
        except UnicodeDecodeError:
            continue
        if k:
            headers[k.strip()] = v.strip()
    return method, target, headers


def respond(wfile, status, reason, headers, body_iter=None):
    wfile.write(("HTTP/1.1 %d %s\r\n" % (status, reason)).encode("latin-1"))
    for k, v in headers:
        wfile.write(("%s: %s\r\n" % (k, v)).encode("latin-1"))
    wfile.write(b"Connection: close\r\n\r\n")
    wfile.flush()
    if body_iter is not None:
        for chunk in body_iter:
            wfile.write(chunk)
        wfile.flush()


def is_intercepted(host, hosts):
    host = (host or "").lower()
    return host in hosts


def mirror_url(upstream, host, target):
    """把 https://github.com/<path> 改写成 https://ghfast.top/https://github.com/<path>"""
    return "%s/https://%s%s" % (upstream.rstrip("/"), host, target)


# --------------------------------------------------------------------------
# 处理一个已解密的 HTTPS 会话
# --------------------------------------------------------------------------
def handle_mitm(tls_sock, host, upstream, port=443):
    rfile = tls_sock.makefile("rb")
    wfile = tls_sock.makefile("wb")
    try:
        while True:
            req = read_request(rfile)
            if req is None:
                return
            method, target, headers = req
            touch_activity()

            if target == HEALTH_PATH:
                respond(wfile, 200, "OK", [("Content-Type", "text/plain"),
                                           ("Content-Length", "2")], [b"OK"])
                return

            fwd = {}
            for k, v in headers.items():
                if k.lower() in FORWARD_HEADERS:
                    fwd[k] = v

            target_url = mirror_url(upstream, host, target)
            t0 = time.time()
            conn, resp = open_upstream(target_url, method, fwd)

            out_headers = []
            for k in RESP_HEADERS:
                v = resp.getheader(k)
                if v is not None:
                    out_headers.append((k.title(), v))
            out_headers.append(("X-Gh-Mirror", "ghproxy"))

            body_len = int(resp.getheader("content-length") or 0)
            reason = resp.reason or ""

            def stream():
                sent = 0
                try:
                    while True:
                        chunk = resp.read(CHUNK)
                        if not chunk:
                            break
                        sent += len(chunk)
                        yield chunk
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    dt = time.time() - t0
                    spd = (sent / dt) if dt > 0 else 0
                    log("  %s %s%s -> %d  %s  %.0f KB/s  (%.1fs)"
                        % (method, host, target[:80], resp.status, human(sent), spd / 1024.0, dt))

            if method == "HEAD":
                try:
                    conn.close()
                except Exception:
                    pass
                respond(wfile, resp.status, reason, out_headers, None)
            else:
                respond(wfile, resp.status, reason, out_headers, stream())
            return
    except (ssl.SSLError, OSError, IOError) as exc:
        log("  !! MITM 会话异常 %s: %s" % (host, exc))
    finally:
        try:
            rfile.close()
            wfile.close()
            tls_sock.close()
        except Exception:
            pass


# --------------------------------------------------------------------------
# 处理明文 HTTP 代理请求（绝对地址形式），例如 http://github.com/...
# --------------------------------------------------------------------------
def handle_plain(client, first_line, rfile, wfile, upstream, hosts):
    try:
        parts = first_line.decode("latin-1").strip().split()
        method, target = parts[0], parts[1]
    except (UnicodeDecodeError, IndexError):
        respond(wfile, 400, "Bad Request", [("Content-Length", "0")])
        return
    headers = {}
    while True:
        hl = rfile.readline(65536)
        if not hl or hl in (b"\r\n", b"\n"):
            break
        k, _, v = hl.decode("latin-1").partition(":")
        if k:
            headers[k.strip()] = v.strip()

    u = urllib.parse.urlsplit(target)
    if not u.hostname:
        respond(wfile, 400, "Bad Request", [("Content-Length", "0")])
        return

    if is_intercepted(u.hostname, hosts):
        path = u.path or "/"
        if u.query:
            path += "?" + u.query
        url = mirror_url(upstream, u.hostname, path)
    else:
        url = target

    fwd = {}
    for k, v in headers.items():
        if k.lower() in FORWARD_HEADERS:
            fwd[k] = v
    try:
        conn, resp = open_upstream(url, method, fwd)
    except Exception as exc:
        respond(wfile, 502, "Bad Gateway", [("Content-Length", "0")])
        log("  !! 上游失败 %s: %s" % (url[:120], exc))
        return

    out_headers = []
    for k in RESP_HEADERS:
        v = resp.getheader(k)
        if v is not None:
            out_headers.append((k.title(), v))

    def stream():
        try:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                conn.close()
            except Exception:
                pass

    respond(wfile, resp.status, resp.reason or "", out_headers,
            None if method == "HEAD" else stream())


# --------------------------------------------------------------------------
# 透传隧道
# --------------------------------------------------------------------------
def handle_tunnel(client, host, port):
    try:
        up = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
    except OSError as exc:
        client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        log("  !! 透传建连失败 %s:%s (%s)" % (host, port, exc))
        return
    up.settimeout(None)
    client.settimeout(None)

    def pipe(src, dst):
        try:
            while True:
                data = src.recv(CHUNK)
                if not data:
                    break
                dst.sendall(data)
        except OSError:
            pass
        finally:
            try:
                dst.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    t = threading.Thread(target=pipe, args=(client, up), daemon=True)
    t.start()
    pipe(up, client)
    t.join(timeout=1)
    for s in (client, up):
        try:
            s.close()
        except OSError:
            pass
    touch_activity()


# --------------------------------------------------------------------------
# 连接分发
# --------------------------------------------------------------------------
def handle_client(client, addr, tls_ctx, upstream, hosts):
    client.settimeout(READ_TIMEOUT)
    try:
        rfile = client.makefile("rb")
        wfile = client.makefile("wb")
        req = read_request(rfile)
        if req is None:
            return
        method, target, headers = req
        touch_activity()

        if method.upper() == "CONNECT":
            host_port = target
            if ":" in host_port:
                host, _, p = host_port.rpartition(":")
                port = int(p)
            else:
                host, port = host_port, 443

            if is_intercepted(host, hosts):
                wfile.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                wfile.flush()
                try:
                    tls_sock = tls_ctx.wrap_socket(client, server_side=True)
                except (ssl.SSLError, OSError) as exc:
                    log("  !! TLS 终结失败 %s: %s" % (host, exc))
                    return
                log("MITM  %s -> %s" % (host, upstream))
                handle_mitm(tls_sock, host, upstream, port)
            else:
                log("PASS  %s:%s" % (host, port))
                wfile.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                wfile.flush()
                handle_tunnel(client, host, port)
            return

        # 明文代理请求
        if urllib.parse.urlsplit(target).path == HEALTH_PATH:
            respond(wfile, 200, "OK", [("Content-Type", "text/plain"),
                                       ("Content-Length", "2")], [b"OK"])
            return
        log("PLAIN %s %s" % (method, target[:100]))
        handle_plain(client, ("%s %s HTTP/1.1" % (method, target)).encode(),
                     rfile, wfile, upstream, hosts)
    except (OSError, ssl.SSLError, IOError):
        pass
    finally:
        try:
            client.close()
        except OSError:
            pass


# --------------------------------------------------------------------------
# 证书卸载（仅在带标记时执行）
# --------------------------------------------------------------------------
def uninstall_ca_if_needed():
    if not os.path.exists(FLAG_CA_INSTALLED):
        return
    try:
        thumb = open(FLAG_CA_INSTALLED, encoding="utf-8").read().strip()
        if thumb:
            subprocess.run(["certutil", "-delstore", "-user", "Root", thumb],
                           capture_output=True, timeout=30)
            log("已自动卸载根证书 (指纹 %s)" % thumb)
    except Exception as exc:
        log("!! 卸载根证书失败，请手动运行 restore.bat：%s" % exc)
    finally:
        try:
            os.remove(FLAG_CA_INSTALLED)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description="GitHub 更新加速本地拦截代理")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--upstream", default=DEFAULT_UPSTREAM)
    ap.add_argument("--hosts", default=DEFAULT_HOSTS)
    ap.add_argument("--idle-timeout", type=int, default=0,
                    help="秒；0 表示不自动退出")
    args = ap.parse_args()

    hosts = set(h.strip().lower() for h in args.hosts.split(",") if h.strip())

    global SELF_ADDR
    SELF_ADDR = (args.host, args.port)

    for p in (LEAF_CRT, LEAF_KEY):
        if not os.path.exists(p):
            log("缺少证书文件 %s，请先运行 gen-certs.bat" % p)
            return 2

    tls_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls_ctx.load_cert_chain(LEAF_CRT, LEAF_KEY)
    tls_ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(128)
    srv.settimeout(1.0)

    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))

    log("=" * 62)
    log("ghproxy 已启动  http://%s:%d" % (args.host, args.port))
    log("拦截域名: %s" % ", ".join(sorted(hosts)))
    log("回源镜像: %s" % args.upstream)
    log("其他域名: 纯 TCP 透传（不干预）")
    log("=" * 62)

    try:
        while True:
            try:
                client, addr = srv.accept()
            except socket.timeout:
                if args.idle_timeout and (time.time() - _last_activity) > args.idle_timeout:
                    log("空闲超过 %d 秒，自动退出" % args.idle_timeout)
                    break
                continue
            threading.Thread(target=handle_client,
                             args=(client, addr, tls_ctx, args.upstream, hosts),
                             daemon=True).start()
    except KeyboardInterrupt:
        log("收到中断信号，正在退出…")
    finally:
        try:
            srv.close()
        except OSError:
            pass
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        uninstall_ca_if_needed()
        log("ghproxy 已停止")
    return 0


if __name__ == "__main__":
    sys.exit(main())
