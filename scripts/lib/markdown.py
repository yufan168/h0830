"""知識卡專用的極簡 Markdown 渲染器。

刻意只支援客服知識頁需要的語法，避免內容作者引入無法被版型規範約束的結構：
標題（h2 至 h4）、段落、有序與無序清單、表格、引用、程式碼區塊、水平線，
以及行內的粗體、斜體、行內程式碼與連結。原始 HTML 一律逸出。
"""

from __future__ import annotations

import html
import re

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_OL_ITEM = re.compile(r"^(\d+)[.)]\s+(.*)$")
_UL_ITEM = re.compile(r"^[-*]\s+(.*)$")


def slugify(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text).strip().lower()
    text = re.sub(r"[\s]+", "-", text)
    text = re.sub(r"[^\w一-鿿-]", "", text)
    return text.strip("-") or "section"


def inline(text: str) -> str:
    """處理行內語法，先逸出再還原受控標記。"""
    placeholders: list[str] = []

    def stash(rendered: str) -> str:
        placeholders.append(rendered)
        return f"\x00{len(placeholders) - 1}\x00"

    text = _INLINE_CODE.sub(lambda m: stash(f"<code>{html.escape(m.group(1))}</code>"), text)
    text = html.escape(text, quote=False)
    text = _LINK.sub(
        lambda m: stash(_link(m.group(1), m.group(2))),
        text,
    )
    text = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", text)
    text = _ITALIC.sub(lambda m: f"<em>{m.group(1)}</em>", text)
    for i, rendered in enumerate(placeholders):
        text = text.replace(f"\x00{i}\x00", rendered)
    return text


def _link(label: str, href: str) -> str:
    safe_href = html.escape(href, quote=True)
    external = href.startswith(("http://", "https://"))
    attrs = ' target="_blank" rel="noopener noreferrer"' if external else ""
    return f'<a href="{safe_href}"{attrs}>{html.escape(label, quote=False)}</a>'


def render(body: str) -> tuple[str, list[dict]]:
    """回傳 (HTML, 標題清單)。標題清單供麵包屑與階層檢查使用。"""
    lines = body.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    headings: list[dict] = []
    i = 0
    seen_ids: dict[str, int] = {}

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            cls = f' class="lang-{html.escape(lang, quote=True)}"' if lang else ""
            out.append(f'<pre class="code-block"><code{cls}>{html.escape(chr(10).join(buf))}</code></pre>')
            continue

        heading = _HEADING.match(stripped)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2).strip()
            base = slugify(text)
            seen_ids[base] = seen_ids.get(base, 0) + 1
            anchor = base if seen_ids[base] == 1 else f"{base}-{seen_ids[base]}"
            headings.append({"level": level, "text": text, "id": anchor})
            out.append(f'<h{level} id="{anchor}">{inline(text)}</h{level}>')
            i += 1
            continue

        if set(stripped) <= {"-", "*", "_"} and len(stripped) >= 3:
            out.append("<hr />")
            i += 1
            continue

        if stripped.startswith("|") and _is_table(lines, i):
            block, i = _collect(lines, i, lambda s: s.startswith("|"))
            out.append(_table(block))
            continue

        if stripped.startswith("> "):
            block, i = _collect(lines, i, lambda s: s.startswith(">"))
            inner = " ".join(s.lstrip(">").strip() for s in block)
            out.append(f"<blockquote><p>{inline(inner)}</p></blockquote>")
            continue

        if _UL_ITEM.match(stripped) or _OL_ITEM.match(stripped):
            block, i = _collect(lines, i, lambda s: bool(_UL_ITEM.match(s) or _OL_ITEM.match(s)))
            ordered = bool(_OL_ITEM.match(block[0]))
            tag = "ol" if ordered else "ul"
            items = []
            for raw in block:
                match = _OL_ITEM.match(raw) if ordered else _UL_ITEM.match(raw)
                text = match.group(2) if ordered else match.group(1)
                items.append(f"<li>{inline(text.strip())}</li>")
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue

        block, i = _collect(lines, i, lambda s: bool(s) and not _breaks_paragraph(s))
        out.append(f"<p>{inline(' '.join(s.strip() for s in block))}</p>")

    return "\n".join(out), headings


def _breaks_paragraph(stripped: str) -> bool:
    return bool(
        stripped.startswith(("```", "|", "> ", "#"))
        or _UL_ITEM.match(stripped)
        or _OL_ITEM.match(stripped)
    )


def _collect(lines: list[str], i: int, keep) -> tuple[list[str], int]:
    block = []
    while i < len(lines) and lines[i].strip() and keep(lines[i].strip()):
        block.append(lines[i].strip())
        i += 1
    return block, i


def _is_table(lines: list[str], i: int) -> bool:
    return (
        i + 1 < len(lines)
        and lines[i + 1].strip().startswith("|")
        and set(lines[i + 1].strip()) <= set("|-: ")
    )


def _table(block: list[str]) -> str:
    rows = [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in block]
    header, body = rows[0], rows[2:]
    head_html = "".join(f"<th scope=\"col\">{inline(c)}</th>" for c in header)
    body_html = "".join(
        "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>" for row in body
    )
    return (
        '<div class="table-wrap">'
        f"<table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>"
        "</div>"
    )
