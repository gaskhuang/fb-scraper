# FB 社團爬蟲專案 — Claude 工作規則

## 絕對不可覆蓋的檔案

- `config.json` — 系統設定（port、token 等），已加入 `.gitignore`
- `schedule_config.json` — 客戶排程設定，已加入 `.gitignore`

> 每次更新程式碼或 git 同步時，**絕對不可** 刪除或覆蓋這兩個檔案。
> Mac Mini 同步只用 `git pull`，不可用 `git reset --hard` 或 `git checkout .`。

---

## 版本號規則

每次有任何程式碼更新，**必須同步更新**以下三個檔案底部的版本號：

- `app/static/index.html`
- `app/static/scheduler.html`
- `app/static/settings.html`

格式：`v{年}.{月}.{日}.{時}{分}`，例如 `v2026.4.14.0951`

版本號位置：每個 HTML 最底部 `</body>` 之前的 `<div>` 標籤。

---

## 目前排程設定（備查）

### 排程 1（schedule_id: d87f5ef461b4）
- 名稱：（未命名）
- 社團：
  - https://www.facebook.com/groups/3238547836318385/
  - https://www.facebook.com/groups/366863238003058/
  - https://www.facebook.com/groups/uitaiwan.group/
- 執行時間：每小時（0–23 時）
- auto_publish: true

### 排程 2（schedule_id: 2f1a7357e079）
- 名稱：第二社團
- 社團：
  - https://www.facebook.com/groups/vibecodingtaiwan/
  - https://www.facebook.com/groups/238876003403930/
  - https://www.facebook.com/groups/2725975797677135/
  - https://www.facebook.com/groups/1577315533418837/
- 執行時間：每小時（0–23 時）
- auto_publish: false

### 排程 3（schedule_id: 89fae1e0ea93）
- 名稱：（未命名）
- 社團：
  - https://www.facebook.com/groups/uitaiwan.group
- 執行時間：每天 08:00
- max_rounds: 20
- auto_publish: true

---

## 系統設定（備查）

- `cdp_port`: 9223
- `web_port`: 9558
- Chrome profile: `~/.chrome-scraper`（持久化，重開機後不需重新登入 Facebook）

---

## Mac Mini 同步方式

```bash
git pull origin main
# 不要用 git reset --hard！config.json 和 schedule_config.json 會被保留
```
