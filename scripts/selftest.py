#!/usr/bin/env python3
"""驗證器的自我測試。

閘門若從不觸發就沒有意義，因此這裡對每一條規則同時測兩件事：
1. 違規內容一定被擋（規則有效）。
2. 合法內容一定不被擋（沒有誤殺）。

用法：python3 scripts/selftest.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate as V  # noqa: E402
from lib import markdown, model, template  # noqa: E402

PASSED = 0
FAILED: list[str] = []

FIXTURE_ABOUT = """---
title: 關於我們
slug: about
description: 測試用說明。
updated: 2020-01-01
owner: 測試組
nav_order: 1
nav_label: 關於
site:
  name: 測試品牌
  kb_name: 知識中心
  base_url: https://example.test
  locale: zh-Hant-TW
  version: 1.0
  contact:
    hours: 平日九點到六點
    email: a@example.test
    report_url: https://example.test/r
    note: 一個工作日內回覆。
---

## 第一節

第一節的內容。

## 第二節

第二節的內容。
"""

FIXTURE_FAQ = """---
title: 常見問題
slug: faq
description: 測試用問答。
updated: 2020-01-01
owner: 測試組
nav_order: 2
nav_label: 問答
---

## 分類一

### 這是一個問題嗎？

這是答案，長度足夠讓驗證器認為它有說明一件事情，並且使用全形標點。

## 分類二

### 另一個問題怎麼處理？

這是第二個答案，同樣寫得夠長，確保通過答案長度的檢查條件。
"""


def fixture_site(tmp: str):
    """建立一份與真實內容無關的最小內容集，讓測試不依賴 content/ 的現況。"""
    root = Path(tmp) / "fixture"
    (root / "content").mkdir(parents=True)
    (root / "content" / "about.md").write_text(FIXTURE_ABOUT, encoding="utf-8")
    (root / "content" / "faq.md").write_text(FIXTURE_FAQ, encoding="utf-8")
    return model.load(root)



def check(name: str, condition: bool) -> None:
    global PASSED
    if condition:
        PASSED += 1
    else:
        FAILED.append(name)


def prose_errors(text: str) -> list:
    report = V.Report()
    V.check_prose("t.md", text, report)
    return report.errors


def heading_errors(text: str) -> list:
    report = V.Report()
    V.check_headings_markdown("t.md", text, report)
    return report.errors


def test_prose_rules() -> None:
    # 應該被擋
    check("半形逗號被擋", prose_errors("這是中文, 後面接半形逗號。"))
    check("半形問號被擋", prose_errors("這樣可以嗎?"))
    check("半形句號被擋", prose_errors("這是一句話."))
    check("半形括號被擋", prose_errors("這是說明(補充內容)。"))
    check("破折號被擋", prose_errors("這是說明 — 補充內容。"))
    check("雙連字號被擋", prose_errors("這是說明 -- 補充內容。"))
    check("TODO 被擋", prose_errors("這段稍後補上 TODO。"))
    check("待補被擋", prose_errors("金額為 ［待補］ 元。"))

    # 不應該被擋
    check("全形標點放行", not prose_errors("這是中文，全部使用全形標點。這樣可以嗎？"))
    check("全形括號放行", not prose_errors("服務時間為平日（國定假日休息）。"))
    check("英數半形標點放行", not prose_errors("可用性目標為每月 99.5%，時間為 09:00 至 18:00。"))
    check("行內程式碼放行", not prose_errors("僅接受 `.csv`，不支援 `.xlsx` 直接上傳。"))
    check("網址放行", not prose_errors("請見 https://example.com/a.html 的說明。"))
    check("表格分隔線放行", not prose_errors("| --- | --- |"))
    check("清單項目放行", not prose_errors("- 這是清單項目。"))
    check("程式碼區塊放行", not prose_errors("```\nprint('a, b.')\n```"))
    check("英文句子放行", not prose_errors("Use UTF-8 encoding, then upload."))


def test_heading_rules() -> None:
    check("正文 h1 被擋", heading_errors("# 不該出現的一級標題"))
    check("跳級被擋", heading_errors("## 章節\n\n#### 跳級標題"))
    check("正常階層放行", not heading_errors("## 章節\n\n### 子節\n\n#### 更小的標題"))
    check("程式碼中的井號放行", not heading_errors("```\n# this is a shell comment\n```"))


def test_structure_rules() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ks = fixture_site(tmp)
        bad = Path(tmp) / "bad.html"
        bad.write_text(
            "<html><head></head><body><h1>一</h1><h1>二</h1><h3>跳級</h3></body></html>",
            encoding="utf-8",
        )
        report = V.Report()
        V.check_page_structure(bad, ks, report)
        joined = " ".join(report.errors)
        check("缺 skip-link 被擋", ".skip-link" in joined)
        check("缺 main#main 被擋", "main#main" in joined)
        check("缺 title 被擋", "<title>" in joined)
        check("缺 canonical 被擋", "canonical" in joined)
        check("多個 h1 被擋", "h1" in joined and "2 個" in joined)
        check("產出標題跳級被擋", "跳級" in joined or "h3" in joined)
        check("缺聯絡區塊被擋", "contact-cta" in joined)

        external = Path(tmp) / "ext.html"
        external.write_text(
            '<html><head><title>x</title>'
            '<link rel="canonical" href="https://example.com/x.html" />'
            '<meta name="description" content="x" />'
            '<script src="https://cdn.example.com/a.js"></script>'
            '</head><body><a class="skip-link" href="#main"></a>'
            '<header class="site-header"></header><main id="main"><h1>標題</h1>'
            '<section class="contact-cta"></section></main>'
            '<footer class="site-footer"></footer></body></html>',
            encoding="utf-8",
        )
        report = V.Report()
        V.check_page_structure(external, ks, report)
        joined = " ".join(report.errors)
        check("外部 script 被擋", "外部資源" in joined)
        check("canonical 不被誤判為外部資源", joined.count("外部資源") == 1)

        anchor = Path(tmp) / "anchor.html"
        anchor.write_text(
            '<html><head><title>x</title>'
            '<link rel="canonical" href="https://example.com/x.html" />'
            '<meta name="description" content="x" /></head>'
            '<body><a class="skip-link" href="#main"></a>'
            '<header class="site-header"></header><main id="main"><h1>標題</h1>'
            '<a href="#not-here">壞錨點</a>'
            '<section class="contact-cta"></section></main>'
            '<footer class="site-footer"></footer></body></html>',
            encoding="utf-8",
        )
        report = V.Report()
        V.check_page_structure(anchor, ks, report)
        check("失效錨點被擋", any("錨點" in e for e in report.errors))


def test_engine() -> None:
    html, headings = markdown.render("## 標題\n\n內文與 `程式碼`。\n\n| a | b |\n| --- | --- |\n| 1 | 2 |")
    check("markdown 產生標題", "<h2" in html and headings[0]["text"] == "標題")
    check("markdown 產生表格", "<table>" in html and "table-wrap" in html)
    check("markdown 逸出原始 HTML", "&lt;script&gt;" in markdown.render("<script>x</script>")[0])

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "partials").mkdir()
        (root / "a.html").write_text("{{#xs}}<i>{{n}}</i>{{/xs}}{{^xs}}空{{/xs}}", encoding="utf-8")
        engine = template.Engine(root)
        check("樣板迴圈", engine.render("a.html", {"xs": [{"n": 1}, {"n": 2}]}) == "<i>1</i><i>2</i>")
        check("樣板反向區塊", engine.render("a.html", {"xs": []}) == "空")

    with tempfile.TemporaryDirectory() as tmp:
        ks = fixture_site(tmp)
        check("內容模型無錯誤", not ks.errors)
        check("問答頁被辨識", ks.qa_page is not None and len(ks.qa_page.questions) == 2)
        check("站台設定被讀到", bool(ks.site.get("contact", {}).get("email")))
        check("導覽依 nav_order 排序", [p.slug for p in ks.nav] == ["about", "faq"])

        empty = Path(tmp) / "empty"
        (empty / "content").mkdir(parents=True)
        (empty / "content" / "faq.md").write_text("", encoding="utf-8")
        check("空內容檔被辨識為 L0 空殼",
              any("L0 空殼" in e for e in model.load(empty).errors))


def main() -> int:
    test_prose_rules()
    test_heading_rules()
    test_structure_rules()
    test_engine()

    total = PASSED + len(FAILED)
    print(f"自我測試：{PASSED}/{total} 通過")
    for name in FAILED:
        print(f"  ✗ {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
