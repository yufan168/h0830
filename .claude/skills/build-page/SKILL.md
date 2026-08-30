---
name: build-page
description: 依 content/ 的內容與 design/brief.md 的版型契約，產生或更新 site/ 底下的靜態客服知識頁。當使用者要新增或修改客服頁內容、要求重新產生網站、要求新增一個頁面，或說「更新知識頁」「重建網站」「加一頁」「把這段內容上架」時使用。
---

# build-page

客服知識頁的執行入口。你的產出是 `site/` 底下的靜態 HTML，來源只有兩個：`content/` 的內容與 `design/brief.md` 的版型契約。

## 開始之前

依序讀完這三份，不要跳過：

1. `CLAUDE.md`：分層權責、知識索引、邊界與紅線。
2. `design/brief.md`：版型契約。標記 `[GATE]` 的規則會被機器擋下。
3. `memory/decisions.md`：先前的決策與理由，避免推翻已經定案的判斷。

## 兩條建置路線

預設走路線 A。只有在明確符合路線 B 的條件時才切換，並在 `memory/decisions.md` 記錄原因。

### 路線 A：腳本產生（預設）

```
1. 編輯 content/*.md
2. python3 scripts/build.py
3. python3 scripts/validate.py     必須通過
4. 在 memory/decisions.md 追加決策
```

適用於絕大多數情況：改文字、增減問答、更新政策、調整章節。

**這條路線下你不要碰 `site/`。** 產出是腳本的責任，你的責任是內容。若產出不如預期，問題在 `content/` 或引擎層，不在 HTML。

### 路線 B：直接撰寫 HTML（退場機制）

在下列情況才使用：

- 需要一個現有樣板無法表達的頁型，而版型契約尚未涵蓋它。
- 引擎故障或環境缺少 Python，但頁面必須先產出。
- 課堂或示範需要展示「不靠腳本、只靠契約」也能做出一致的頁面。

步驟：

```
1. 讀 design/brief.md，逐條對照第 3 節的必要結構節點
2. 參考 templates/ 底下對應頁型的樣板結構
3. 直接寫出 site/<slug>.html
4. python3 scripts/validate.py     仍然必須通過
5. 在 memory/decisions.md 記錄為什麼走了路線 B
```

走路線 B 時的三個提醒：

1. **樣式不要另外寫。** 沿用 `site/assets/style.css` 既有的 class，不要在 HTML 裡加 `<style>` 或行內樣式，也不要自己挑顏色。需要新元件時，先在 `design/tokens.json` 定義 token。
2. **聯絡資訊從 `content/` 取**，不要照抄一份到 HTML 裡。
3. **路線 B 的產出是暫時的。** 只要引擎恢復或版型契約補上該頁型，就要回到路線 A 重新產生，否則下一次建置會把它覆蓋或遺漏。

## 新增一個頁面

新增頁面同時牽動三個地方，缺一驗證器就會擋：

1. `content/<slug>.md`：完整的 frontmatter，`nav_order` 不得與現有頁面重複。
2. `design/brief.md` 第 2 節的產出清單：加上新頁，否則會被判定為「契約以外的頁面」。
3. 若是全新頁型，`templates/` 需要新增對應樣板。

## 交付前的檢查

```
python3 scripts/build.py
python3 scripts/validate.py
```

驗證器離開碼的意義：

| 碼 | 意義 | 該做什麼 |
| --- | --- | --- |
| 0 | 全部通過 | 可以交付 |
| 1 | 有 GATE 違規 | 修內容，不要修驗證器 |
| 2 | 內容尚未填寫 | 目前是空殼，先填 `content/` |

改動了 `scripts/`、`templates/` 或 `assets/` 時，額外執行 `python3 scripts/selftest.py`，確認驗證器本身仍然有效。

**不要為了通過而放寬規則、註解掉檢查或改寫驗證器。** 那是把閘門拆掉，不是把問題解決。

## 交付說明要寫什麼

1. 改了哪些內容檔，以及為什麼。
2. `validate.py` 的結果，包含 REVIEW 等級的提醒。
3. **待確認清單**：來源沒講清楚而選擇留白的欄位，逐項列出交給人類補齊。這一項不可省略。
