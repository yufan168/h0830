"""把 content/ 載入成結構化的知識庫模型。

build.py 與 validate.py 共用這一份載入邏輯，確保「產出」與「驗證」
對內容契約的理解不會分岔。
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import frontmatter, markdown

REQUIRED_FIELDS = ("id", "title", "category", "summary", "tags", "status", "owner", "updated")
OPTIONAL_FIELDS = ("weight", "related", "noindex")
STATUSES = {
    "published": {"label": "已發布", "css": "is-published"},
    "review": {"label": "審核中", "css": "is-review"},
    "deprecated": {"label": "已停用", "css": "is-deprecated"},
}
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Card:
    id: str
    title: str
    category: str
    summary: str
    tags: list
    status: str
    owner: str
    updated: str
    weight: int
    related: list
    body: str
    html: str
    headings: list
    source: Path

    @property
    def url(self) -> str:
        return f"/a/{self.id}/"

    @property
    def listed(self) -> bool:
        """是否出現在首頁與分類頁清單。停用的知識卡只保留內頁。"""
        return self.status != "deprecated"

    @property
    def status_label(self) -> str:
        return STATUSES[self.status]["label"]

    @property
    def status_css(self) -> str:
        return STATUSES[self.status]["css"]


@dataclass
class Category:
    id: str
    name: str
    summary: str
    icon: str
    weight: int
    cards: list = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"/c/{self.id}/"

    @property
    def listed_cards(self) -> list:
        return [c for c in self.cards if c.listed]

    @property
    def count(self) -> int:
        return len(self.listed_cards)


@dataclass
class KnowledgeBase:
    site: dict
    categories: list
    cards: list
    errors: list

    @property
    def by_id(self) -> dict:
        return {c.id: c for c in self.cards}

    @property
    def listed_cards(self) -> list:
        return [c for c in self.cards if c.listed]

    def category(self, cid: str):
        return next((c for c in self.categories if c.id == cid), None)

    def popular(self, limit: int = 6) -> list:
        ranked = sorted(self.listed_cards, key=lambda c: (c.weight, c.id))
        return ranked[:limit]

    def recent(self, limit: int = 5) -> list:
        return sorted(self.listed_cards, key=lambda c: (c.updated, c.id), reverse=True)[:limit]


def load(root: Path) -> KnowledgeBase:
    root = Path(root)
    errors: list[str] = []

    taxonomy_path = root / "content" / "taxonomy.yml"
    if not taxonomy_path.exists():
        raise frontmatter.ContentError("找不到 content/taxonomy.yml")
    taxonomy = frontmatter.parse_yaml(taxonomy_path.read_text(encoding="utf-8"), str(taxonomy_path))

    site = dict(taxonomy.get("site") or {})
    categories = []
    for raw in taxonomy.get("categories") or []:
        missing = [k for k in ("id", "name", "summary") if not raw.get(k)]
        if missing:
            errors.append(f"content/taxonomy.yml: 分類 {raw.get('id', '?')} 缺少欄位 {', '.join(missing)}")
            continue
        categories.append(
            Category(
                id=str(raw["id"]),
                name=str(raw["name"]),
                summary=str(raw["summary"]),
                icon=str(raw.get("icon") or "📄"),
                weight=int(raw.get("weight") or 999),
            )
        )
    categories.sort(key=lambda c: (c.weight, c.id))

    cards = []
    for path in sorted((root / "content" / "faq").glob("*.md")):
        rel = path.relative_to(root).as_posix()
        try:
            data, body = frontmatter.split(path.read_text(encoding="utf-8"), rel)
        except frontmatter.ContentError as exc:
            errors.append(str(exc))
            continue

        missing = [f for f in REQUIRED_FIELDS if data.get(f) in (None, "", [])]
        if missing:
            errors.append(f"{rel}: frontmatter 缺少必填欄位 {', '.join(missing)}")
            continue

        unknown = sorted(set(data) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS))
        if unknown:
            errors.append(f"{rel}: frontmatter 出現未定義欄位 {', '.join(unknown)}，請先更新 CLAUDE.md 的欄位契約")

        status = str(data["status"])
        if status not in STATUSES:
            errors.append(f"{rel}: status「{status}」不合法，只能是 {', '.join(STATUSES)}")
            continue

        html_body, headings = markdown.render(body)
        cards.append(
            Card(
                id=str(data["id"]),
                title=str(data["title"]),
                category=str(data["category"]),
                summary=str(data["summary"]),
                tags=[str(t) for t in (data["tags"] or [])],
                status=status,
                owner=str(data["owner"]),
                updated=str(data["updated"]),
                weight=int(data.get("weight") or 500),
                related=[str(r) for r in (data.get("related") or [])],
                body=body,
                html=html_body,
                headings=headings,
                source=path,
            )
        )

    known = {c.id for c in categories}
    for card in cards:
        category = next((c for c in categories if c.id == card.category), None)
        if category is None:
            errors.append(
                f"{card.source.name}: category「{card.category}」不在 taxonomy.yml，"
                f"可用分類為 {', '.join(sorted(known))}"
            )
            continue
        category.cards.append(card)

    for category in categories:
        category.cards.sort(key=lambda c: (c.weight, c.updated, c.id))

    return KnowledgeBase(site=site, categories=categories, cards=cards, errors=errors)


def today() -> str:
    return dt.date.today().isoformat()
