# -*- coding: utf-8 -*-
"""安装目录定位 —— 零第三方依赖。

设计契约：**要么用你指的目录，要么明确报错，绝不静默回退到其他目录。**
自动定位最怕“猜错了还默默更新错副本”，所以这里把决策权交回用户，
代价是失败时必须把“试过哪些、为什么不行、你可能想用哪个”讲清楚。

解析优先级：
  1. --install PATH                显式；本次生效，校验通过后写回配置
  2. GHUPDATE_INSTALL_MAA(_MAAEND) 显式；环境变量
  3. config.json 的 install.<kind>.path   隐式默认值，失效时可被交互输入覆盖
  4. 交互式询问（输入合法则写回配置）；非交互 / -y 下直接报错

1 和 2 是**显式来源**：一旦给出就以它为准，校验不过直接报错，
绝不回退到 config.json 或交互输入（唯一例外是“经用户确认”的一层子目录救回）。

版本探测通过 version_of 回调注入，本模块不依赖 _common，便于后续重构。
"""

from __future__ import annotations

import os
import sys

KINDS = {
    "maa": {
        "label": "MAA",
        "exe": "MAA.exe",
        # 判定为安装目录的必需文件（有主程序就算，不含 config/ 等用户数据）
        "require": ["MAA.exe"],
        "hint": "update-all.bat --install \"D:\\RL\\MAA-v6.9.5-win-x64\"",
    },
    "maaend": {
        "label": "MaaEnd",
        "exe": "MaaEnd.exe",
        # interface.json 是版本来源，缺失只影响版本判定，不作为拒绝理由
        "require": ["MaaEnd.exe"],
        "hint": "update-all.bat --install \"D:\\RL\\MaaEnd-win-x86_64-v2.23.0\"",
    },
}


class LocateError(Exception):
    """目录定位失败（语义错误，由调用方转成用户可读的报错）。"""


class LocateCancelled(Exception):
    """用户主动放弃指定。"""


#: 这些来源说明用户“显式指定”过目录，值得写回配置记住
EXPLICIT_SOURCES = ("--install", "交互输入", "子目录确认", "子目录选择")


# ---------------------------------------------------------------------------
# 路径规范化 / 校验
# ---------------------------------------------------------------------------

def normalize(raw):
    """清理用户给出的路径：引号、空字符、环境变量、正斜杠、尾部反斜杠。

    同时容忍“直接填了 exe 文件路径”的写法（自动取其所在目录）。
    """
    text = str(raw or "").strip()
    # cmd 拖拽会带引号，且可能是成对的中英文引号
    for pair in (("\"", "\""), ("'", "'"), ("\u201c", "\u201d")):
        if len(text) >= 2 and text.startswith(pair[0]) and text.endswith(pair[1]):
            text = text[1:-1]
    text = text.strip()
    if not text:
        return ""
    text = os.path.expandvars(text)
    text = os.path.expanduser(text)
    text = text.replace("/", os.sep)
    text = text.rstrip("\\/")
    if not text:
        return ""
    # 驱动器根目录 C: -> C:\
    if len(text) == 2 and text.endswith(":"):
        text += os.sep
    if os.path.isfile(text):
        text = os.path.dirname(text)
    return os.path.abspath(text)


def validate(kind, path):
    """返回 (是否有效, 原因)。path 需已 normalize。"""
    spec = KINDS[kind]
    if not path:
        return False, "未指定"
    if not os.path.isdir(path):
        return False, "目录不存在"
    missing = [name for name in spec["require"]
               if not os.path.isfile(os.path.join(path, name))]
    if missing:
        return False, "目录里没有 %s" % "、".join(missing)
    return True, ""


def describe_dir(path, limit=8):
    """列出目录内容（报错时帮用户判断自己指到哪儿了）。"""
    try:
        names = sorted(os.listdir(path or ""))
    except OSError:
        return ""
    dirs = [n + os.sep for n in names if os.path.isdir(os.path.join(path, n))]
    files = [n for n in names if not os.path.isdir(os.path.join(path, n))]
    items = dirs + files
    if len(items) > limit:
        items = items[:limit] + ["..."]
    return "、".join(items)


def probe_children(kind, parent, version_of=None, limit=20):
    """只看 parent 的**直接子目录**里有没有像样的安装目录。

    这是“手动指定”的一层容错，不是自动定位：不递归、不扫全盘。
    返回 [(路径, 版本说明), ...]。
    """
    if not parent or not os.path.isdir(parent):
        return []
    hits = []
    try:
        names = sorted(os.listdir(parent))
    except OSError:
        return []
    for name in names:
        child = os.path.join(parent, name)
        if not os.path.isdir(child):
            continue
        good, _ = validate(kind, child)
        if not good:
            continue
        hits.append((child, version_text(version_of, child)))
        if len(hits) >= limit:
            break
    return hits


def version_text(version_of, path):
    if not version_of:
        return ""
    try:
        got = version_of(path) or ""
    except Exception:  # noqa: BLE001
        return ""
    return str(got).strip()


# ---------------------------------------------------------------------------
# 交互
# ---------------------------------------------------------------------------

class Prompt:
    """默认的终端交互实现。测试时可替换为 FakePrompt。"""

    def echo(self, msg=""):
        sys.stdout.write(str(msg) + "\n")
        sys.stdout.flush()

    def ask(self, question):
        """返回用户输入；EOF / 无法读取时返回 None。"""
        sys.stdout.write(question)
        sys.stdout.flush()
        try:
            line = sys.stdin.readline()
        except (EOFError, OSError, KeyboardInterrupt):
            return None
        if not line:
            return None
        return line.strip()

    def ask_yes_no(self, question, default=True):
        suffix = " [Y/n] " if default else " [y/N] "
        got = self.ask(str(question) + suffix)
        if got is None:
            return False
        got = got.strip().lower()
        if not got:
            return default
        if got in ("y", "yes"):
            return True
        if got in ("n", "no"):
            return False
        return default

    def ask_choice(self, question, items):
        """items 是 [(路径, 版本), ...]；返回选中的路径，取消返回 ""。"""
        self.echo(str(question))
        for idx, (path, ver) in enumerate(items, 1):
            self.echo("    %d) %s   %s" % (idx, path, ver or ""))
        got = self.ask("  请输入序号（直接回车 = 取消）：")
        if got is None or not got.strip():
            return ""
        try:
            num = int(got.strip())
        except ValueError:
            return ""
        if 1 <= num <= len(items):
            return items[num - 1][0]
        return ""


def interactive_ok():
    """是否具备交互条件（双击 bat / 终端下为真；管道重定向为假）。"""
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def _error_text(kind, tried):
    spec = KINDS[kind]
    lines = ["找不到 %s 的安装目录。" % spec["label"]]
    if tried:
        lines.append("  已尝试：")
        for path, source, why in tried:
            lines.append("    - %s（来自 %s）-> %s" % (path or "(空)", source, why))
    lines.append("  %s 的安装目录就是包含 %s 的那个文件夹。" % (spec["label"], spec["exe"]))
    lines.append("  可以这样指定：%s" % spec["hint"])
    return "\n".join(lines)


def _rescue_by_child(kind, raw, cfg, allow_prompt, version_of, prompt, tried):
    """父目录容错：在 raw 的**直接子目录**里找像样的安装目录。

    返回 (路径, 来源) 或 None。**只有用户确认过才会返回**；
    非交互模式下一律不自动采用（只记入 tried）。
    """
    if not cfg.parent_probe:
        return None
    spec = KINDS[kind]
    parent = normalize(raw)
    hits = probe_children(kind, parent, version_of)
    if not hits:
        return None
    if len(hits) > 1:
        if allow_prompt:
            chosen = prompt.ask_choice(
                "  %s 不是 %s 安装目录本身，但它的子目录里有多个候选："
                % (parent, spec["label"]), hits)
            if chosen:
                return chosen, "子目录选择"
        for path, _ver in hits:
            tried.append((path, "子目录候选", "非交互模式，未自动采用"))
        return None
    path, ver = hits[0]
    if not allow_prompt:
        tried.append((path, "子目录候选", "非交互模式，未自动采用"))
        return None
    question = ("  你指定的 %s 不是 %s 安装目录本身。\n"
                "  但在它下面找到：%s%s\n  用这个吗？"
                % (parent, spec["label"], path, ("（%s）" % ver) if ver else ""))
    if prompt.ask_yes_no(question, default=True):
        return path, "子目录确认"
    tried.append((path, "子目录候选", "用户未采纳"))
    return None


def _explicit_error_text(kind, path, source, why, tried):
    """显式指定（--install / 环境变量）不可用时的报错文案。

    必须让用户看清三件事：指到了哪、为什么不行、怎么改回已保存的目录。
    """
    spec = KINDS[kind]
    lines = ["你指定的 %s 安装目录不可用：" % spec["label"]]
    lines.append("      %s   （来自 %s）" % (path or "(空路径)", source))
    lines.append("    —— %s" % why)
    content = describe_dir(path)
    if content:
        lines.append("")
        lines.append("    该目录内容：%s" % content)
    cands = [t for t in tried if t[1] == "子目录候选"]
    if cands:
        lines.append("")
        lines.append("    它下面的候选：")
        for cpath, _src, reason in cands:
            lines.append("      - %s   （%s）" % (cpath, reason))
    lines.append("")
    lines.append("    %s 不会改用 config.json 里保存的目录。" % source)
    if source == "--install":
        lines.append("    要改用已保存的目录，请去掉 --install 后重新运行。")
    else:
        lines.append("    要改用已保存的目录，请清除 %s 后重新运行。" % source)
    return "\n".join(lines)


def resolve(kind, cfg, cli_install="", allow_prompt=True, version_of=None,
            prompt=None, echo=None):
    """确定安装目录。成功返回 (路径, 来源说明)，失败抛 LocateError / LocateCancelled。"""
    prompt = prompt or Prompt()
    echo = echo or prompt.echo
    spec = KINDS[kind]

    # ---- 1~2. 显式来源：--install > 环境变量 ----
    # 契约：显式指定过就以它为准。校验不过直接报错，绝不回退到其他来源。
    explicit = []
    if cli_install:
        explicit.append((cli_install, "--install"))
    env_name = "GHUPDATE_INSTALL_%s" % kind.upper()
    env_val = os.environ.get(env_name)
    if env_val:
        explicit.append((env_val, "环境变量 " + env_name))

    tried = []
    if explicit:
        raw, source = explicit[0]
        path = normalize(raw)
        good, why = validate(kind, path)
        if good:
            return path, source
        # 只允许“经用户确认”的一层子目录救回；不做任何静默替换。
        rescued = _rescue_by_child(kind, raw, cfg, allow_prompt, version_of,
                                   prompt, tried)
        if rescued:
            return rescued
        tried.append((path or str(raw), source, why))
        raise LocateError(_explicit_error_text(kind, path, source, why, tried))

    # ---- 3. config.json（隐式默认值；失效时可被交互输入覆盖）----
    cfg_raw = cfg.install_path(kind)
    if cfg_raw:
        path = normalize(cfg_raw)
        good, why = validate(kind, path)
        if good:
            return path, "config.json"
        tried.append((path or str(cfg_raw), "config.json", why))
        rescued = _rescue_by_child(kind, cfg_raw, cfg, allow_prompt, version_of,
                                   prompt, tried)
        if rescued:
            return rescued

    # ---- 4. 交互式询问 ----
    if allow_prompt:
        echo("")
        echo("  请指定 %s 的安装目录 —— 也就是 %s 所在的那个文件夹。"
             % (spec["label"], spec["exe"]))
        echo("  提示：可直接把文件夹从资源管理器拖进本窗口，再回车；输入 q 放弃。")
        while True:
            raw = prompt.ask("  目录 > ")
            if raw is None:
                raise LocateCancelled("无法读取输入（当前不是交互式终端）")
            text = raw.strip()
            if text.lower() in ("q", "quit", "exit"):
                raise LocateCancelled("已放弃指定安装目录。")
            if not text:
                continue
            path = normalize(text)
            good, why = validate(kind, path)
            if good:
                return path, "交互输入"
            echo("    [x] %s -> %s" % (path or text, why))
            content = describe_dir(path)
            if content:
                echo("        该目录内容：%s" % content)
            # 输到父目录时，顺手把下一层里像样的候选递上来
            if cfg.parent_probe:
                hits = probe_children(kind, path, version_of)
                if len(hits) == 1:
                    child, ver = hits[0]
                    if prompt.ask_yes_no(
                            "        不过它下面有一个像样的：%s%s\n        用这个吗？"
                            % (child, ("（%s）" % ver) if ver else ""), default=True):
                        return child, "子目录确认"
                elif len(hits) > 1:
                    chosen = prompt.ask_choice("        它的直接子目录里有多个候选：", hits)
                    if chosen:
                        return chosen, "子目录选择"

    # ---- 5. 失败：把过程和出路讲清楚 ----
    lines = [_error_text(kind, tried)]
    if not allow_prompt:
        lines.append("")
        lines.append("  当前是非交互模式（-y 或没有可用终端），不会自动猜测目录。")
        lines.append("  请显式指定后再运行，或直接编辑 config.json 里的 install.%s.path。" % kind)
    raise LocateError("\n".join(lines))


def inspect(kind, path, version_of=None, echo=None):
    """--inspect：只报告，不改动任何东西。返回退出码。"""
    echo = echo or (lambda msg="": sys.stdout.write(str(msg) + "\n"))
    spec = KINDS[kind]
    echo("%s 安装目录检查" % spec["label"])
    if not path:
        echo("  （未指定目录；可用 --inspect \"路径\" 或先配置 install.%s.path）" % kind)
        return 1

    target = normalize(path)
    good, why = validate(kind, target)
    echo("  %s" % target)
    if good:
        echo("    判定：是安装目录")
        echo("    版本：%s" % (version_text(version_of, target) or "(读不到)"))
        return 0

    echo("    判定：不是安装目录 —— %s" % why)
    content = describe_dir(target)
    echo("    目录内容：%s" % (content or "(无法读取)"))
    hits = probe_children(kind, target, version_of)
    if hits:
        echo("    该目录的直接子目录里有这些候选：")
        for child, ver in hits:
            echo("      - %s   %s" % (child, ver or ""))
    else:
        echo("    该目录的直接子目录里也没有候选。")
    return 1
