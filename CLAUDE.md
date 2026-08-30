# CLAUDE.md｜客服知識頁維護規則

這個 repo 是一套讓 AI 維護官網客服知識頁的工作環境。你的工作是依 `content/` 的內容與 `design/brief.md` 的版型規範，產出並更新 `site/` 底下的靜態頁面。

開始任何工作之前先讀完本檔，以及 `design/brief.md`。

---

## 1. 三層架構與權責

| 層 | 路徑 | 你可以做什麼 |
| --- | --- | --- |
| 內容層 | `content/*.md` | **自由編輯**。新增問答、更新說明、調整章節都在這裡做 |
| 版型層 | `design/brief.md`、`design/tokens.json` | **唯讀**。這是凍結契約，要改必須由人類先修訂並升版號 |
| 引擎層 | `scripts/`、`templates/`、`assets/` | **謹慎修改**。只有在版型契約先變更後才動，且必須同步更新驗證器 |
| 產出層 | `site/` | **不得手動編輯**。一律由 `scripts/build.py` 產生 |
| 決策層 | `memory/decisions.md` | 每次做出非顯而易見的判斷時追加一筆 |

## 2. 標準工作流

```
1. 讀 CLAUDE.md 與 design/brief.md
2. 編輯 content/*.md
3. python3 scripts/build.py      產生 site/
4. python3 scripts/validate.py   閘門，必須全過
5. 在 memory/decisions.md 追加決策紀錄
6. commit
```

`scripts/validate.py` 回傳非 0 就是**不准交付**。不要為了讓它通過而放寬規則、跳過檢查或改寫驗證器，那是把閘門拆掉而不是把問題解決。修內容，不要修尺。

改動引擎層時另外跑 `python3 scripts/selftest.py`，確認驗證器本身仍然有效。

## 3. 內容契約

### 3.1 檔案與頁面的對應

`content/` 底下一個 `.md` 就是一個頁面，目前共四個：`products.md`、`faq.md`、`policy.md`、`about.md`。要新增頁面必須同時更新 `design/brief.md` 第 2 節的產出清單，否則驗證器會擋。

### 3.2 frontmatter 欄位

必填：

| 欄位 | 說明 |
| --- | --- |
| `title` | 頁面標題，會成為 h1 |
| `slug` | 產出檔名，小寫英數與連字號 |
| `description` | 一句話說明，會成為 meta description |
| `updated` | 最後更新日期，`YYYY-MM-DD`，不得填未來日期 |
| `owner` | 負責窗口，出現在頁面上 |
| `nav_order` | 主導覽順序，全站不得重複 |
| `nav_label` | 主導覽顯示文字 |

選填：`icon`、`site`、`noindex`。`site` 區塊全站只能有一個檔案帶（目前在 `about.md`），裡面是品牌名稱、版本與聯絡資訊。

**不得自行新增未定義的欄位。** 真的需要新欄位時，先更新本節與 `scripts/lib/model.py` 的 `REQUIRED_FIELDS` 或 `OPTIONAL_FIELDS`。

### 3.3 正文結構

- `##` 是區塊。在 `faq.md` 代表問題分類，在其他頁代表章節。每頁至少兩個。
- `###` 在 `faq.md` 代表一個問題，標題直接寫成使用者會問的句子。其他頁代表子節。
- 正文不得使用 `#`，h1 由 `title` 產生。
- 標題階層不得跳級。
- 每個問題的第一段就是直球答案，先講結論再講步驟。

## 4. 寫作規則

1. **全形標點。** 中文語句一律使用全形逗號、句號、問號、冒號與括號。純英數的片段（`99.5%`、`09:00`、`.csv`）維持半形。
2. **禁用破折號。** 全站不得出現 `—`、`–` 或 `--`。要停頓就斷句。
3. **繁體中文、台灣用語。**
4. **先給答案再給步驟。** 客服頁的讀者正在焦慮，不要用三段鋪陳才進入正題。
5. **可執行。** 寫「到『帳單設定 > 發票資訊』修改」，不要寫「可於系統中進行相關設定」。

## 5. 紅線

以下情況一律不做，寧可停下來問人：

1. **不得虛構事實。** 金額、天數、期限、SLA、法規依據、聯絡方式，只要來源沒有明確講，就不要寫。
2. **缺資料時不要塞佔位符。** 驗證器會擋 `TODO`、`待補`、`XXX`、`（略）` 等標記，因為客服頁不該帶著空洞上線。正確做法是：把該段落整段留白不寫，並在 `memory/decisions.md` 與交付說明裡列出待確認清單交給人類補齊。
3. **不得手動編輯 `site/`。** 任何產出的修改都要回到 `content/` 或引擎層。
4. **不得改 `design/brief.md` 來讓自己的產出過關。**
5. **不得引入外部 CDN 的 JS、CSS 或字型。**
6. **不得把聯絡資訊寫死在樣板。** 一律從 `content/about.md` 的 `site.contact` 取。
7. **刪除既有問答前先確認。** 客服知識常被外部連結直接引用，移除等於製造死連結。要下架請改寫內容並在決策紀錄說明。

## 6. 指令速查

| 指令 | 用途 |
| --- | --- |
| `python3 scripts/build.py` | 建置到 `site/` |
| `python3 scripts/build.py --clean` | 清空後重建 |
| `python3 scripts/validate.py` | 交付閘門 |
| `python3 scripts/validate.py --strict` | 連 REVIEW 提醒也視為失敗 |
| `python3 scripts/selftest.py` | 驗證器自我測試 |
| `python3 -m http.server -d site 8000` | 本機預覽 |

## 7. 驗證器會擋什麼

`scripts/validate.py` 的每條規則都對應 `design/brief.md` 的編號。它會擋：

- frontmatter 缺欄位、多欄位、日期格式錯誤或填未來日期
- 半形標點、破折號、佔位符
- 正文出現 `#`、標題跳級
- 問答分類底下沒有問題、答案過短
- 產出頁面缺 skip link、`main#main`、`title`、`canonical`、聯絡區塊
- 一頁多個 h1、產出的標題階層跳級、失效的頁內錨點
- `site/` 出現契約以外的頁面
- 樣式表在 token 區塊之外出現色碼字面值
- 引用外部資源、聯絡資訊被寫死在樣板
- 列印樣式或 `beforeprint` 處理缺失

REVIEW 等級的提醒不會擋交付，但要在交付說明中主動提出。

## 8. 決策紀錄

在 `memory/decisions.md` 追加一筆的時機：

- 改寫或刪除既有問答
- 對版型契約提出修訂建議
- 遇到來源不明確而選擇留白的欄位
- 任何下一個接手的人會問「為什麼這樣做」的判斷

格式見該檔開頭的說明。
