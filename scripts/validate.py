#!/usr/bin/env python3
"""交付閘門：檢查 content/ 的內容契約與 site/ 的版型契約。

用法：
    python3 scripts/validate.py           檢查內容與既有產出
    python3 scripts/validate.py --strict  把 REVIEW 等級的提醒也視為失敗

離開碼 0 代表通過，1 代表有 GATE 級錯誤，2 代表內容尚未填寫（L0 空殼）。
規則編號對應 design/brief.md，方便回頭查是哪一條契約。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import model  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site"

CJK = r"㐀-䶿一-鿿豈-﫿"
HALF_PUNCT = re.compile(rf"[{CJK}]\s*([,.;:!?])")
HALF_PAREN = re.compile(rf"(?:[{CJK}]\s*\()|(?:\([^)]*[{CJK}][^)]*\))")
DASH = re.compile(r"—|–|―|(?<![-|:\s])--(?!-)|(?<=\s)--(?=\s)")
PLACEHOLDER = re.compile(r"TODO|FIXME|TBD|XXX|Lorem ipsum|待補|待填|待確認內容|（略）|\?\?\?", re.I)
TABLE_SEP = re.compile(r"^\|[\s\-:|]+\|$")
HR_LINE = re.compile(r"^[-*_]{3,}$")
CODE_FENCE = re.compile(r"^\s*```")
INLINE_CODE = re.compile(r"`[^`]*`")
URL = re.compile(r"https?://\S+|mailto:\S+")
EXTERNAL_SCHEME = re.compile(r"^(?:https?:)?//", re.I)

REQUIRED_SITE_KEYS = ("name", "kb_name", "base_url", "locale", "version")
REQUIRED_CONTACT_KEYS = ("hours", "email", "report_url", "note")
EXPECTED_FILES = ("index.html", "products.html", "faq.html", "policy.html", "about.html",
                  "404.html", "search-index.json", "sitemap.xml", "robots.txt")
MAX_PAGE_KB = 120


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def gate(self, rule: str, message: str) -> None:
        self.errors.append(f"[{rule}] {message}")

    def review(self, rule: str, message: str) -> None:
        self.warnings.append(f"[{rule}] {message}")


class PageParser(HTMLParser):
    """抽出結構檢查需要的資訊。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: list[tuple[int, str]] = []
        self.ids: set[str] = set()
        self.classes: set[str] = set()
        self.anchors: list[str] = []
        self.tags: list[str] = []
        self.external_assets: list[str] = []
        self.meta_description: str | None = None
        self.canonical: str | None = None
        self.title: str = ""
        self._in_title = False
        self._heading: int | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append(tag)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        for cls in (attrs.get("class") or "").split():
            self.classes.add(cls)
        if tag == "title":
            self._in_title = True
        if tag == "meta" and attrs.get("name") == "description":
            self.meta_description = attrs.get("content", "")
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href", "")
        if tag == "a" and attrs.get("href"):
            self.anchors.append(attrs["href"])
        if tag == "script" and EXTERNAL_SCHEME.match(attrs.get("src") or ""):
            self.external_assets.append(attrs["src"])
        if tag == "link" and attrs.get("rel") in ("stylesheet", "preload", "modulepreload"):
            if EXTERNAL_SCHEME.match(attrs.get("href") or ""):
                self.external_assets.append(attrs["href"])
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._heading = int(tag[1])
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self._heading:
            self.headings.append((self._heading, "".join(self._buf).strip()))
            self._heading = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._heading:
            self._buf.append(data)


def main() -> int:
    parser = argparse.ArgumentParser(description="檢查客服知識頁的內容與版型契約")
    parser.add_argument("--strict", action="store_true", help="把 REVIEW 提醒視為失敗")
    args = parser.parse_args()

    content_files = sorted((ROOT / "content").glob("*.md"))
    if content_files and all(not f.read_text(encoding="utf-8").strip() for f in content_files):
        print("目前是 L0 空殼：content/ 底下的內容檔都還沒填寫。")
        print("骨架與引擎已就緒，填入內容後再執行一次即可進行完整檢查。")
        print(f"待填檔案：{', '.join(f.name for f in content_files)}")
        return 2

    report = Report()
    ks = model.load(ROOT)
    for err in ks.errors:
        report.gate("內容", err)

    if not ks.errors:
        check_site_config(ks, report)
        for page in ks.pages:
            check_content(page, report)
    check_output(ks, report)
    check_style(report)
    check_no_hardcoded_contact(ks, report)

    print("驗證結果")
    print("=" * 60)
    if report.errors:
        print(f"GATE 失敗 {len(report.errors)} 項：")
        for item in report.errors:
            print(f"  ✗ {item}")
    if report.warnings:
        print(f"REVIEW 提醒 {len(report.warnings)} 項：")
        for item in report.warnings:
            print(f"  ! {item}")
    if not report.errors and not report.warnings:
        print("全部通過，內容契約與版型契約皆無違反。")
    elif not report.errors:
        print("GATE 全部通過，上列提醒需人工判斷。")

    if report.errors:
        return 1
    if args.strict and report.warnings:
        print("strict 模式下 REVIEW 提醒視為失敗。")
        return 1
    return 0


def check_site_config(ks, report: Report) -> None:
    for key in REQUIRED_SITE_KEYS:
        if not ks.site.get(key):
            report.gate("5.5", f"站台設定缺少 site.{key}")
    contact = ks.site.get("contact") or {}
    for key in REQUIRED_CONTACT_KEYS:
        if not contact.get(key):
            report.gate("5.5", f"站台設定缺少 site.contact.{key}")

    orders = [p.nav_order for p in ks.pages]
    if len(set(orders)) != len(orders):
        report.gate("3", f"nav_order 重複：{sorted(orders)}，主導覽順序必須唯一")


def check_content(page, report: Report) -> None:
    rel = page.source.relative_to(ROOT).as_posix()

    if not model.SLUG_RE.match(page.slug):
        report.gate("內容", f"{rel}: slug「{page.slug}」必須是小寫英數與連字號")
    if not model.DATE_RE.match(page.updated):
        report.gate("內容", f"{rel}: updated「{page.updated}」必須是 YYYY-MM-DD")
    else:
        if dt.date.fromisoformat(page.updated) > dt.date.today():
            report.gate("內容", f"{rel}: updated「{page.updated}」是未來日期")

    if len(page.sections) < 2:
        report.gate("4.3", f"{rel}: 至少需要兩個 ## 區塊，目前只有 {len(page.sections)} 個")

    if page.is_qa:
        for section in page.sections:
            if not section.items:
                report.gate("4.2", f"{rel}: 分類「{section.title}」底下沒有任何 ### 問題")
            for item in section.items:
                if not item.title.endswith(("？", "?")) and "怎麼" not in item.title:
                    report.review("4.2", f"{rel}: 「{item.title}」建議寫成問句，貼近使用者搜尋字詞")
                if len(item.text) < 30:
                    report.gate("4.2", f"{rel}: 「{item.title}」的答案過短，至少要能獨立說明一件事")

    check_prose(rel, page.raw_body, report)
    check_headings_markdown(rel, page.raw_body, report)


def check_prose(rel: str, body: str, report: Report) -> None:
    in_code = False
    for lineno, raw in enumerate(body.split("\n"), start=1):
        stripped = raw.strip()
        if CODE_FENCE.match(raw):
            in_code = not in_code
            continue
        if in_code or not stripped:
            continue
        if TABLE_SEP.match(stripped) or HR_LINE.match(stripped):
            continue

        text = INLINE_CODE.sub(" ", stripped)
        text = URL.sub(" ", text)

        if PLACEHOLDER.search(text):
            report.gate("內容", f"{rel}:{lineno} 出現佔位符或未完成標記：{stripped[:40]}")
        if DASH.search(text):
            report.gate("7", f"{rel}:{lineno} 出現破折號，全站禁用：{stripped[:40]}")
        match = HALF_PUNCT.search(text)
        if match:
            report.gate("7", f"{rel}:{lineno} 中文後接半形標點「{match.group(1)}」：{stripped[:40]}")
        if HALF_PAREN.search(text):
            report.gate("7", f"{rel}:{lineno} 中文語句使用半形括號，請改用全形：{stripped[:40]}")


def check_headings_markdown(rel: str, body: str, report: Report) -> None:
    in_code = False
    previous = 2
    for lineno, raw in enumerate(body.split("\n"), start=1):
        if CODE_FENCE.match(raw):
            in_code = not in_code
            continue
        if in_code:
            continue
        match = re.match(r"^(#{1,6})\s", raw)
        if not match:
            continue
        level = len(match.group(1))
        if level == 1:
            report.gate("9", f"{rel}:{lineno} 正文不得使用 #，h1 由頁面標題產生")
        elif level > previous + 1:
            report.gate("9", f"{rel}:{lineno} 標題階層跳級，h{previous} 之後不能直接出現 h{level}")
        previous = level


def check_output(ks, report: Report) -> None:
    if not OUT.exists():
        report.gate("2", "找不到 site/，請先執行 python3 scripts/build.py")
        return

    for name in EXPECTED_FILES:
        if not (OUT / name).exists():
            report.gate("2", f"缺少產出檔 site/{name}")

    extra = {p.name for p in OUT.glob("*.html")} - set(EXPECTED_FILES)
    if extra:
        report.gate("2", f"site/ 出現契約以外的頁面：{', '.join(sorted(extra))}")

    for path in sorted(OUT.glob("*.html")):
        check_page_structure(path, ks, report)


def check_page_structure(path: Path, ks, report: Report) -> None:
    name = path.name
    html = path.read_text(encoding="utf-8")
    parser = PageParser()
    parser.feed(html)

    for cls in ("skip-link", "site-header", "site-footer"):
        if cls not in parser.classes:
            report.gate("3", f"site/{name} 缺少必要結構節點 .{cls}")
    if "main" not in parser.ids:
        report.gate("3", f"site/{name} 缺少 main#main")
    if not parser.title.strip():
        report.gate("3", f"site/{name} 缺少 <title>")
    if not parser.meta_description:
        report.gate("3", f"site/{name} 缺少 meta description")
    if not parser.canonical:
        report.gate("3", f"site/{name} 缺少 canonical")

    h1s = [text for level, text in parser.headings if level == 1]
    if len(h1s) != 1:
        report.gate("9", f"site/{name} 應該剛好有一個 h1，目前有 {len(h1s)} 個")

    previous = 1
    for level, text in parser.headings:
        if level > previous + 1:
            report.gate("9", f"site/{name} 標題階層跳級：h{previous} 之後出現 h{level}「{text[:20]}」")
        previous = level

    if name in ("index.html", "404.html"):
        if "kb-search" not in parser.ids:
            report.gate("4.1", f"site/{name} 缺少搜尋列 #kb-search")
    if "contact-cta" not in parser.classes:
        report.gate("5.5", f"site/{name} 缺少聯絡客服區塊 .contact-cta")

    page = next((p for p in ks.pages if p.filename == name), None)
    if page:
        for cls in ("breadcrumb", "page-title", "page-meta"):
            if cls not in parser.classes:
                report.gate("4.3", f"site/{name} 缺少 .{cls}")
        if len(page.sections) >= 2 and "toc" not in parser.classes:
            report.gate("5.2", f"site/{name} 有 {len(page.sections)} 個區塊，必須輸出 nav.toc")
        if page.is_qa and "qa-item" not in parser.classes:
            report.gate("4.2", f"site/{name} 缺少 details.qa-item")

    for href in parser.anchors:
        if href.startswith("#") and href[1:] and href[1:] not in parser.ids:
            report.gate("內容", f"site/{name} 錨點 {href} 指向不存在的區塊")

    if parser.external_assets:
        report.gate(
            "11",
            f"site/{name} 引用了外部資源 {', '.join(parser.external_assets)}，"
            "所有 CSS 與 JS 必須同源自帶",
        )

    size_kb = path.stat().st_size / 1024
    if size_kb > MAX_PAGE_KB:
        report.review("11", f"site/{name} 大小 {size_kb:.1f}KB 超過建議的 {MAX_PAGE_KB}KB")


def check_style(report: Report) -> None:
    css_path = OUT / "assets" / "style.css"
    if not css_path.exists():
        report.gate("6", "缺少 site/assets/style.css")
        return
    css = css_path.read_text(encoding="utf-8")

    body = re.sub(r":root[^{]*\{[^}]*\}", "", css)
    leaks = re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)", body)
    if leaks:
        report.gate("6", f"style.css 的 token 區塊之外出現色碼字面值：{', '.join(sorted(set(leaks))[:5])}")

    if "@media print" not in css:
        report.gate("10", "style.css 缺少列印樣式")
    if 'data-theme="dark"' not in css or "prefers-color-scheme: dark" not in css:
        report.gate("6", "style.css 缺少深色主題的三態支援")

    js_path = OUT / "assets" / "app.js"
    if not js_path.exists():
        report.gate("11", "缺少 site/assets/app.js")
    elif "beforeprint" not in js_path.read_text(encoding="utf-8"):
        report.gate("10", "app.js 缺少 beforeprint 處理，列印時問答不會展開")


def check_no_hardcoded_contact(ks, report: Report) -> None:
    """聯絡資訊只能來自內容檔，不得寫死在樣板或樣式表。"""
    contact = ks.site.get("contact") or {}
    needles = [str(v) for v in (contact.get("email"), contact.get("report_url"), contact.get("hours")) if v]
    if not needles:
        return
    for path in list((ROOT / "templates").rglob("*.html")) + [ROOT / "assets" / "style.css", ROOT / "assets" / "app.js"]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle in text:
                rel = path.relative_to(ROOT).as_posix()
                report.gate("5.5", f"{rel} 寫死了聯絡資訊「{needle}」，必須改由 content/ 提供")


if __name__ == "__main__":
    raise SystemExit(main())
