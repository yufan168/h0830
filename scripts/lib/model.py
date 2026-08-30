"""把 content/*.md 載入成結構化的知識頁模型。

build.py 與 validate.py 共用這一份載入邏輯，確保「產出」與「驗證」
對內容契約的理解不會分岔。

內容契約：
- 每個 .md 檔對應一個產出頁面，frontmatter 定義該頁的識別與導覽位置。
- 正文以 `##` 切成區塊。faq.md 的 `##` 是分類、`###` 是問題；
  其他頁的 `##` 是章節、`###` 是子節。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import frontmatter, markdown

REQUIRED_FIELDS = ("title", "slug", "description", "updated", "owner", "nav_order", "nav_label")
OPTIONAL_FIELDS = ("icon", "site", "noindex")
QA_SLUG = "faq"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Item:
    """問答頁裡的單一問題。"""

    id: str
    title: str
    html: str
    text: str


@dataclass
class Section:
    """一個 `##` 區塊。章節頁用 html，問答頁用 items。"""

    id: str
    title: str
    html: str
    text: str
    items: list = field(default_factory=list)


@dataclass
class Page:
    slug: str
    title: str
    description: str
    updated: str
    owner: str
    nav_order: int
    nav_label: str
    icon: str
    intro_html: str
    sections: list
    source: Path
    raw_body: str

    @property
    def is_qa(self) -> bool:
        return self.slug == QA_SLUG

    @property
    def filename(self) -> str:
        return f"{self.slug}.html"

    @property
    def path(self) -> str:
        return f"/{self.slug}.html"

    @property
    def questions(self) -> list:
        return [item for section in self.sections for item in section.items]


@dataclass
class KnowledgeSite:
    site: dict
    pages: list
    errors: list

    @property
    def nav(self) -> list:
        return sorted(self.pages, key=lambda p: (p.nav_order, p.slug))

    def page(self, slug: str):
        return next((p for p in self.pages if p.slug == slug), None)

    @property
    def qa_page(self):
        return self.page(QA_SLUG)

    def popular(self, limit: int | None = 6) -> list:
        """首頁的問題清單。limit 為 None 時列出全部。"""
        page = self.qa_page
        if not page:
            return []
        return page.questions if limit is None else page.questions[:limit]


_H2 = re.compile(r"^##\s+(.*)$")
_H3 = re.compile(r"^###\s+(.*)$")


def load(root: Path) -> KnowledgeSite:
    root = Path(root)
    errors: list[str] = []
    pages: list[Page] = []
    site: dict = {}

    files = sorted((root / "content").glob("*.md"))
    if not files:
        errors.append("content/ 底下沒有任何 .md 內容檔")

    for path in files:
        rel = path.relative_to(root).as_posix()
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            errors.append(f"{rel}: 尚未填寫內容（目前是 L0 空殼）")
            continue
        try:
            data, body = frontmatter.split(raw, rel)
        except frontmatter.ContentError as exc:
            errors.append(str(exc))
            continue

        missing = [f for f in REQUIRED_FIELDS if data.get(f) in (None, "", [])]
        if missing:
            errors.append(f"{rel}: frontmatter 缺少必填欄位 {', '.join(missing)}")
            continue

        unknown = sorted(set(data) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS))
        if unknown:
            errors.append(
                f"{rel}: frontmatter 出現未定義欄位 {', '.join(unknown)}，"
                "請先更新 CLAUDE.md 的欄位契約再新增"
            )

        if isinstance(data.get("site"), dict):
            if site:
                errors.append(f"{rel}: site 設定區塊重複，全站只能有一個檔案帶 site:")
            site = data["site"]

        slug = str(data["slug"])
        seen: dict[str, int] = {}
        intro_html, sections = _parse_body(body, slug == QA_SLUG, seen)

        pages.append(
            Page(
                slug=slug,
                title=str(data["title"]),
                description=str(data["description"]),
                updated=str(data["updated"]),
                owner=str(data["owner"]),
                nav_order=int(data["nav_order"]),
                nav_label=str(data["nav_label"]),
                icon=str(data.get("icon") or "📄"),
                intro_html=intro_html,
                sections=sections,
                source=path,
                raw_body=body,
            )
        )

    if not site:
        errors.append("找不到站台設定，請在其中一個內容檔的 frontmatter 加上 site: 區塊")

    seen_slugs: dict[str, str] = {}
    for page in pages:
        if page.slug in seen_slugs:
            errors.append(f"{page.source.name}: slug「{page.slug}」與 {seen_slugs[page.slug]} 重複")
        seen_slugs[page.slug] = page.source.name

    return KnowledgeSite(site=site, pages=pages, errors=errors)


def _parse_body(body: str, is_qa: bool, seen: dict) -> tuple[str, list]:
    """把正文依 `##`（與問答頁的 `###`）切段並各自渲染。"""
    lines = body.replace("\r\n", "\n").split("\n")
    intro: list[str] = []
    groups: list[tuple[str, list[str]]] = []
    current: list[str] | None = None

    for line in lines:
        match = _H2.match(line.strip()) if not line.startswith("    ") else None
        if match and not _in_code(intro if current is None else current):
            current = []
            groups.append((match.group(1).strip(), current))
            continue
        (intro if current is None else current).append(line)

    intro_html, _ = markdown.render("\n".join(intro).strip())
    sections = []
    for title, block in groups:
        anchor = _unique(markdown.slugify(title), seen)
        text = "\n".join(block).strip()
        if is_qa:
            items = _parse_items(block, seen)
            sections.append(Section(id=anchor, title=title, html="", text=_plain(text), items=items))
        else:
            html, _ = markdown.render(text)
            sections.append(Section(id=anchor, title=title, html=html, text=_plain(text)))
    return intro_html, sections


def _parse_items(block: list[str], seen: dict) -> list:
    items = []
    title = None
    buf: list[str] = []
    for line in block:
        match = _H3.match(line.strip())
        if match:
            if title is not None:
                items.append(_make_item(title, buf, seen))
            title = match.group(1).strip()
            buf = []
        elif title is not None:
            buf.append(line)
    if title is not None:
        items.append(_make_item(title, buf, seen))
    return items


def _make_item(title: str, buf: list[str], seen: dict) -> Item:
    text = "\n".join(buf).strip()
    html, _ = markdown.render(text)
    return Item(id=_unique(markdown.slugify(title), seen), title=title, html=html, text=_plain(text))


def _in_code(lines: list[str]) -> bool:
    return sum(1 for line in lines if line.strip().startswith("```")) % 2 == 1


def _unique(base: str, seen: dict) -> str:
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}-{seen[base]}"


def _plain(text: str) -> str:
    """把 Markdown 壓成純文字，供搜尋索引使用。"""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"^[#>|\-*\d.]+\s*", " ", text, flags=re.M)
    text = re.sub(r"[`*\[\]()|]", " ", text)
    return re.sub(r"\s+", " ", text).strip()
