"""極簡樣板引擎，語法為 Mustache 的子集。

- {{key}}        逸出後輸出
- {{{key}}}      原樣輸出（僅用於已渲染的 HTML）
- {{#key}}…{{/key}}  list 走迴圈，其他真值渲染一次，假值略過
- {{^key}}…{{/key}}  假值時渲染一次
- {{> name}}     載入 templates/partials/name.html
- {{.}}          迴圈中的目前項目
巢狀查找會沿著 context stack 往上找，找不到視為空字串。
"""

from __future__ import annotations

import html
import re
from pathlib import Path

_TOKEN = re.compile(r"\{\{([#^/>{]?)\s*([\w.]+)\s*\}?\}\}")


class TemplateError(Exception):
    pass


class Engine:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._cache: dict[str, list] = {}

    def render(self, name: str, context: dict) -> str:
        return "".join(self._render(self._load(name), [context]))

    def _load(self, name: str) -> list:
        if name not in self._cache:
            path = self.root / name
            if not path.exists():
                raise TemplateError(f"找不到樣板 {path}")
            self._cache[name] = _parse(path.read_text(encoding="utf-8"), str(path))
        return self._cache[name]

    def _render(self, nodes: list, stack: list) -> list[str]:
        out: list[str] = []
        for node in nodes:
            kind = node[0]
            if kind == "text":
                out.append(node[1])
            elif kind == "var":
                value = _lookup(stack, node[1])
                out.append(html.escape(_stringify(value), quote=False))
            elif kind == "raw":
                out.append(_stringify(_lookup(stack, node[1])))
            elif kind == "partial":
                out.extend(self._render(self._load(f"partials/{node[1]}.html"), stack))
            elif kind == "section":
                value = _lookup(stack, node[1])
                if isinstance(value, (list, tuple)):
                    for item in value:
                        out.extend(self._render(node[2], stack + [item if isinstance(item, dict) else {".": item}]))
                elif value:
                    out.extend(self._render(node[2], stack + [value if isinstance(value, dict) else {}]))
            elif kind == "inverted":
                value = _lookup(stack, node[1])
                if not value:
                    out.extend(self._render(node[2], stack))
        return out


def _parse(text: str, source: str) -> list:
    nodes: list = []
    stack: list[tuple[str, str, list]] = []
    target = nodes
    pos = 0
    for match in _TOKEN.finditer(text):
        if match.start() > pos:
            target.append(("text", text[pos:match.start()]))
        pos = match.end()
        sigil, name = match.group(1), match.group(2)
        if sigil in ("#", "^"):
            child: list = []
            stack.append(("section" if sigil == "#" else "inverted", name, child))
            target = child
        elif sigil == "/":
            if not stack or stack[-1][1] != name:
                raise TemplateError(f"{source}: 區塊 {{{{/{name}}}}} 沒有對應的開頭")
            kind, key, child = stack.pop()
            target = stack[-1][2] if stack else nodes
            target.append((kind, key, child))
        elif sigil == ">":
            target.append(("partial", name))
        elif sigil == "{":
            target.append(("raw", name))
        else:
            target.append(("var", name))
    if stack:
        raise TemplateError(f"{source}: 區塊 {{{{#{stack[-1][1]}}}}} 沒有收尾")
    if pos < len(text):
        target.append(("text", text[pos:]))
    return nodes


def _lookup(stack: list, key: str):
    if key == ".":
        return stack[-1].get(".", stack[-1])
    head, _, tail = key.partition(".")
    for scope in reversed(stack):
        if isinstance(scope, dict) and head in scope:
            value = scope[head]
            for part in tail.split(".") if tail else []:
                if not isinstance(value, dict) or part not in value:
                    return None
                value = value[part]
            return value
    return None


def _stringify(value) -> str:
    if value is None or value is False:
        return ""
    if value is True:
        return "true"
    return str(value)
