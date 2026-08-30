# service-hub：星光家電客服知識中心

## Capability
AI 能夠在維護官網客服知識頁的情境下，
使用 content/ 的內容與 design/brief.md 的版型規範，
遵守 CLAUDE.md 的規則，完成靜態頁面的生成與更新。

## Boundary
AI 做：讀 content/ 生成頁面、套用版型、指出 content/ 的缺漏與矛盾。
人做：決定政策內容、核准對外文案、決定某個品項是否上架、處理客訴。

## 今日暫行規則
現在是架構建立階段。未經我明確指示，不得生成 site/ 底下的任何檔案，
不得讀取 source/ 的內容，不得填寫 content/ 的任何內容。
本段優先於上方 Capability 與 Boundary，於 source/ 放入原始資料後自動失效。
