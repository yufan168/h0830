#!/usr/bin/env python3
"""把 content/ 與 design/ 建置成 site/ 底下的靜態頁面。

用法：
    python3 scripts/build.py            建置到 site/
    python3 scripts/build.py --clean    先清空 site/ 再建置

建置流程刻意是純函式：同樣的 content 與 design 一定產出同樣的 HTML，
唯一會變動的是頁尾的建置時間。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import model  # noqa: E402
from lib.template import Engine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site"
TOKEN_MARKER = "/* @tokens */"
SNIPPET_LEN = 160


def main() -> int:
    parser = argparse.ArgumentParser(description="建置客服知識頁")
    parser.add_argument("--clean", action="store_true", help="建置前先清空 site/")
    args = parser.parse_args()

    ks = model.load(ROOT)
    if ks.errors:
        print("內容載入失敗，請先修正下列問題：", file=sys.stderr)
        for err in ks.errors:
            print(f"  ✗ {err}", file=sys.stderr)
        return 1

    if args.clean and OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True, exist_ok=True)
    # --clean 會連版控佔位檔一起刪掉，補回來，否則 git 會讓整個 site/ 消失。
    (OUT / ".gitkeep").touch()

    engine = Engine(ROOT / "templates")
    site = ks.site
    base_url = str(site.get("base_url", "")).rstrip("/")
    build_time = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    index = build_search_index(ks)

    (OUT / "assets" / "style.css").write_text(render_css(), encoding="utf-8")
    shutil.copyfile(ROOT / "assets" / "app.js", OUT / "assets" / "app.js")
    (OUT / "search-index.json").write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    shared = {
        "site": site,
        "build_time": build_time,
        "total_entries": len(index),
    }

    written = []
    for page in ks.pages:
        body = engine.render(
            "qa.html" if page.is_qa else "page.html",
            {
                **shared,
                "page": page_ctx(page),
                "sections": [section_ctx(s) for s in page.sections],
                "toc": toc_ctx(page),
                "canonical": f"{base_url}/{page.filename}",
            },
        )
        written.append(write_page(engine, ks, page.filename, page.title, page.description, body, shared, base_url))

    home = engine.render(
        "index.html",
        {
            **shared,
            "topics": [topic_ctx(p) for p in ks.nav],
            "popular": [
                {"title": q.title, "href": f"{model.QA_SLUG}.html#{q.id}"} for q in ks.popular()
            ],
        },
    )
    written.append(
        write_page(engine, ks, "index.html", site.get("kb_name", "知識中心"),
                   site.get("tagline", ""), home, shared, base_url)
    )

    notfound = engine.render("404.html", shared)
    written.append(
        write_page(engine, ks, "404.html", "找不到這一頁", "您要找的頁面不存在或已搬移。",
                   notfound, shared, base_url)
    )

    write_sitemap(ks, base_url)
    (OUT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n", encoding="utf-8"
    )

    total = sum(p.stat().st_size for p in written)
    print(f"建置完成，共 {len(written)} 頁，{len(index)} 筆搜尋索引，合計 {total / 1024:.1f}KB")
    for path in sorted(written):
        print(f"  · {path.relative_to(ROOT)}  {path.stat().st_size / 1024:.1f}KB")
    return 0


def write_page(engine, ks, filename, title, description, content, shared, base_url) -> Path:
    site = ks.site
    full_title = title if filename == "index.html" else f"{title}｜{site.get('kb_name', '')}"
    html = engine.render(
        "base.html",
        {
            **shared,
            "page_title": full_title,
            "page_description": description,
            "canonical": f"{base_url}/{filename}",
            "content": content,
            "nav": [
                {
                    "label": p.nav_label,
                    "href": p.filename,
                    "active": p.filename == filename,
                }
                for p in ks.nav
            ],
        },
    )
    path = OUT / filename
    path.write_text(html, encoding="utf-8")
    return path


def page_ctx(page) -> dict:
    return {
        "slug": page.slug,
        "title": page.title,
        "description": page.description,
        "updated": page.updated,
        "owner": page.owner,
        "icon": page.icon,
        "intro_html": page.intro_html,
    }


def section_ctx(section) -> dict:
    return {
        "id": section.id,
        "title": section.title,
        "html": section.html,
        "items": [{"id": i.id, "title": i.title, "html": i.html} for i in section.items],
    }


def toc_ctx(page):
    """目錄項目少於兩項時不輸出，對應 design/brief.md 5.2。"""
    items = [{"id": s.id, "title": s.title} for s in page.sections]
    return {"items": items} if len(items) >= 2 else None


def topic_ctx(page) -> dict:
    count = len(page.questions) if page.is_qa else len(page.sections)
    return {
        "title": page.title,
        "description": page.description,
        "href": page.filename,
        "icon": page.icon,
        "count": count,
        "unit": "問題" if page.is_qa else "章節",
    }


def build_search_index(ks) -> list:
    entries = []
    for page in ks.pages:
        entries.append(
            {
                "t": page.title,
                "u": page.filename,
                "p": page.nav_label,
                "s": page.description,
            }
        )
        for section in page.sections:
            if page.is_qa:
                for item in section.items:
                    entries.append(
                        {
                            "t": item.title,
                            "u": f"{page.filename}#{item.id}",
                            "p": f"{page.nav_label} · {section.title}",
                            "s": snippet(item.text),
                        }
                    )
            else:
                entries.append(
                    {
                        "t": section.title,
                        "u": f"{page.filename}#{section.id}",
                        "p": page.nav_label,
                        "s": snippet(section.text),
                    }
                )
    return entries


def snippet(text: str) -> str:
    return text[:SNIPPET_LEN] + ("…" if len(text) > SNIPPET_LEN else "")


def render_css() -> str:
    """把 design/tokens.json 注入 assets/style.css 的 token 標記處。"""
    tokens = json.loads((ROOT / "design" / "tokens.json").read_text(encoding="utf-8"))
    css = (ROOT / "assets" / "style.css").read_text(encoding="utf-8")
    if TOKEN_MARKER not in css:
        raise SystemExit(f"assets/style.css 缺少 token 插入標記 {TOKEN_MARKER}")

    light = _decls(tokens["color"]["light"], "color")
    light += _decls(tokens["shadow"]["light"], "shadow")
    for group in ("font", "size", "leading", "space", "radius", "layout"):
        light += _decls(tokens[group], group)

    dark = _decls(tokens["color"]["dark"], "color") + _decls(tokens["shadow"]["dark"], "shadow")

    block = "\n".join(
        [
            "/* 以下由 scripts/build.py 依 design/tokens.json 產生，請勿手動編輯。 */",
            ":root {",
            "  color-scheme: light dark;",
            *light,
            "}",
            "",
            "@media (prefers-color-scheme: dark) {",
            '  :root:not([data-theme="light"]) {',
            *[f"  {line}" for line in dark],
            "  }",
            "}",
            "",
            ':root[data-theme="dark"] {',
            *dark,
            "}",
        ]
    )
    return css.replace(TOKEN_MARKER, block, 1)


def _decls(group: dict, prefix: str) -> list:
    return [f"  --{prefix}-{key}: {value};" for key, value in group.items()]


def write_sitemap(ks, base_url: str) -> None:
    today = dt.date.today().isoformat()
    urls = [("index.html", today)] + [(p.filename, p.updated) for p in ks.nav]
    body = "\n".join(
        f"  <url><loc>{base_url}/{name}</loc><lastmod>{mod}</lastmod></url>" for name, mod in urls
    )
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n</urlset>\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
