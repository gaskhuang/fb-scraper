# FB 社團爬蟲

自動爬取 Facebook 社團熱門貼文，產生統一 HTML 報告並推送到 GitHub Pages，支援多排程管理與 Telegram 通知。

## 功能特色

- **多社團批次爬取** — 一次設定多個社團，依序爬取後產生單一統一報告
- **模擬真人行為** — 隨機滾動速度、停頓時間，降低 Facebook 偵測風險
- **Web 管理介面** — 瀏覽器操作，無需命令列
- **多排程系統** — 可設定多組排程（不同社團、不同時段），各自獨立運作
- **GitHub Pages 自動發布** — 每次爬完自動推送報告，隨時從外部瀏覽
- **Telegram 通知** — 報告完成後自動傳送連結到 Telegram
- **開機自啟** — macOS launchd 管理，重開機自動恢復

## 系統需求

- macOS（Intel 或 Apple Silicon）
- Google Chrome
- 網路連線

## 快速安裝

```bash
tar -xzf fb-scraper.tar.gz
cd cdp抓網頁
bash install.sh
```

安裝腳本會自動完成：
- Homebrew、Python 3、Node.js、gh CLI
- cdp-cli（Chrome DevTools Protocol 工具）
- Python 虛擬環境與相依套件
- macOS launchd 開機自啟服務（FastAPI + Chrome CDP）

## 首次設定

1. 安裝完成後，用以下指令開啟 Chrome（CDP 模式）：
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
     --remote-debugging-port=9223 \
     --user-data-dir=/Users/你的用戶名/.chrome-cdp
   ```
2. 在該 Chrome 視窗登入 Facebook
3. 開啟管理介面：`http://localhost:9558`
4. 點「設定」，填入：
   - **GitHub Token**（需要 `repo` 權限）— 系統自動偵測用戶名並建立報告 repo
   - **Telegram Bot Token** — 系統自動偵測 Chat ID（需先對 bot 發送 `/start`）

## 目錄結構

```
fb-scraper/
├── app/
│   ├── main.py              # FastAPI 後端
│   └── static/
│       ├── index.html       # 一次性爬取頁面
│       ├── scheduler.html   # 多排程管理頁面
│       └── settings.html    # 設定頁面
├── scripts/
│   ├── fb_group_scraper.py  # 核心爬蟲（cdp-cli 操控 Chrome）
│   ├── generate.py          # HTML 報告產生器
│   ├── publish_to_github.py # GitHub Pages 發布
│   ├── notify.py            # Telegram 通知
│   └── config_loader.py     # 統一設定讀取模組
├── launchd/                 # macOS 開機自啟模板
├── config.json              # 設定檔（Token、Port 等）
├── requirements.txt
├── install.sh               # 一鍵安裝腳本
└── uninstall.sh             # 移除服務腳本
```

## 設定檔 config.json

```json
{
  "telegram_bot_token": "",
  "telegram_chat_id": "",
  "github_repo": "",
  "github_token": "",
  "cdp_port": 9223,
  "web_port": 9558
}
```

移機時只需更新此檔案（或透過 Web UI 設定頁修改），重啟服務即可。

## 使用方式

### 一次性爬取
開啟 `http://localhost:9558`，新增社團、設定篩選條件，按「開始爬取」。

### 排程爬取
開啟 `http://localhost:9558/scheduler`，建立排程：
- 選擇社團與篩選條件
- 設定執行星期與時段
- 每個排程顯示：下次執行時間、上次執行結果（✅/❌）

### 查看報告
- 本機：爬完後 Web UI 顯示報告連結
- 遠端：透過 GitHub Pages 連結，隨時在任何裝置瀏覽

## 服務管理

```bash
# 停止服務
launchctl unload ~/Library/LaunchAgents/com.fb-scraper.*.plist

# 啟動服務
launchctl load ~/Library/LaunchAgents/com.fb-scraper.*.plist

# 查看日誌
tail -f logs/web.log

# 移除服務
bash uninstall.sh
```

## 注意事項

- Chrome 必須以 GUI 模式運行（Facebook 偵測 headless 瀏覽器）
- CDP Chrome 使用獨立設定檔（`~/.chrome-cdp`），與一般 Chrome 帳號分開
- `config.json` 包含敏感資訊，已加入 `.gitignore`
