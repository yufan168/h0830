"""YAML frontmatter 解析。

優先使用 PyYAML；若環境沒有 PyYAML，退回內建的極簡縮排解析器，
支援 mapping、list of scalar、list of mapping 與三層巢狀，足以涵蓋
content/taxonomy.yml 與知識卡 frontmatter 的語法子集。
"""

from __future__ import annotations

import re

try:  # pragma: no cover - 取決於執行環境
    import yaml

    HAVE_YAML = True
except ImportError:  # pragma: no cover
    yaml = None
    HAVE_YAML = False

_FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", re.S)


class ContentError(Exception):
    """內容格式錯誤，帶有檔案路徑資訊。"""


def split(text: str, source: str = "<memory>") -> tuple[dict, str]:
    """把 Markdown 檔切成 (frontmatter dict, 正文)。"""
    match = _FM_RE.match(text.lstrip("﻿"))
    if not match:
        raise ContentError(f"{source}: 檔案開頭必須是 --- 包住的 YAML frontmatter")
    head, body = match.group(1), match.group(2)
    data = parse_yaml(head, source)
    if not isinstance(data, dict):
        raise ContentError(f"{source}: frontmatter 必須是 key: value 形式")
    return data, body


def parse_yaml(text: str, source: str = "<memory>") -> object:
    if HAVE_YAML:
        try:
            return yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:  # pragma: no cover - 交給呼叫端顯示
            raise ContentError(f"{source}: YAML 解析失敗：{exc}") from exc
    return _MiniYaml(text, source).parse()


class _MiniYaml:
    """極簡縮排式 YAML 解析器，僅支援本專案用到的語法。"""

    def __init__(self, text: str, source: str):
        self.source = source
        self.lines: list[tuple[int, str]] = []
        for raw in text.splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            self.lines.append((len(raw) - len(raw.lstrip(" ")), self._strip_comment(stripped)))

    @staticmethod
    def _strip_comment(line: str) -> str:
        out, quote = [], ""
        for i, ch in enumerate(line):
            if quote:
                out.append(ch)
                if ch == quote:
                    quote = ""
            elif ch in "\"'":
                quote = ch
                out.append(ch)
            elif ch == "#" and i > 0 and line[i - 1] == " ":
                break
            else:
                out.append(ch)
        return "".join(out).rstrip()

    def parse(self) -> object:
        if not self.lines:
            return {}
        value, idx = self._block(0, self.lines[0][0])
        if idx != len(self.lines):
            raise ContentError(f"{self.source}: 第 {idx + 1} 個有效行縮排不一致")
        return value

    def _block(self, i: int, indent: int):
        if self.lines[i][1].startswith("- "):
            return self._sequence(i, indent)
        return self._mapping(i, indent)

    def _sequence(self, i: int, indent: int):
        items = []
        while i < len(self.lines) and self.lines[i][0] == indent and self.lines[i][1].startswith("- "):
            rest = self.lines[i][1][2:].strip()
            child_indent = indent + 2
            if _is_key(rest):
                # list of mapping，第一個 key 與 "- " 同行。
                item: dict = {}
                i = self._pair(item, i, rest, child_indent)
                while i < len(self.lines) and self.lines[i][0] == child_indent and not self.lines[i][1].startswith("- "):
                    i = self._pair(item, i, self.lines[i][1], child_indent)
                items.append(item)
            else:
                items.append(_scalar(rest))
                i += 1
        return items, i

    def _mapping(self, i: int, indent: int):
        data: dict = {}
        while i < len(self.lines) and self.lines[i][0] == indent:
            line = self.lines[i][1]
            if line.startswith("- "):
                break
            i = self._pair(data, i, line, indent)
        return data, i

    def _pair(self, data: dict, i: int, line: str, indent: int) -> int:
        if ":" not in line:
            raise ContentError(f"{self.source}: 無法解析的行「{line}」")
        key, _, raw = line.partition(":")
        key, raw = key.strip(), raw.strip()
        if raw:
            data[key] = _scalar(raw)
            return i + 1
        nxt = i + 1
        if nxt < len(self.lines) and self.lines[nxt][0] > indent:
            value, nxt = self._block(nxt, self.lines[nxt][0])
            data[key] = value
            return nxt
        data[key] = None
        return i + 1


def _is_key(text: str) -> bool:
    key, sep, _ = text.partition(":")
    return bool(sep) and bool(key.strip()) and " " not in key.strip()


def _scalar(raw: str):
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    low = raw.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~", ""):
        return None
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    return raw
