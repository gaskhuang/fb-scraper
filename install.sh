#!/bin/bash
# ═══════════════════════════════════════════════
# FB 社團爬蟲 — 一鍵安裝腳本
# 用法: bash install.sh
# ═══════════════════════════════════════════════

set -e

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$INSTALL_DIR/config.json"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo "═══════════════════════════════════════════════"
echo " FB 社團爬蟲 安裝程式"
echo " 安裝目錄: $INSTALL_DIR"
echo "═══════════════════════════════════════════════"
echo ""

# ── 1. 確認 macOS ──
if [ "$(uname -s)" != "Darwin" ]; then
    echo "❌ 此腳本僅支援 macOS"
    exit 1
fi
echo "✅ macOS 確認"

# ── 2. 檢查/安裝 Homebrew ──
if ! command -v brew &>/dev/null; then
    echo "📦 正在安裝 Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # 載入 brew 到 PATH
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
else
    echo "✅ Homebrew 已安裝"
fi

# ── 3. 安裝 Python3, Node, gh ──
echo ""
echo "📦 安裝必要套件..."
for pkg in python3 node gh; do
    if ! command -v $pkg &>/dev/null; then
        echo "   安裝 $pkg..."
        brew install $pkg
    else
        echo "   ✅ $pkg 已安裝"
    fi
done

# ── 4. 安裝 cdp-cli ──
if ! command -v cdp-cli &>/dev/null; then
    echo "📦 安裝 cdp-cli..."
    npm install -g @myerscarpenter/cdp-cli
else
    echo "✅ cdp-cli 已安裝"
fi

# ── 5. 建立 Python 虛擬環境 ──
echo ""
if [ ! -d "$INSTALL_DIR/.venv" ]; then
    echo "🐍 建立 Python 虛擬環境..."
    python3 -m venv "$INSTALL_DIR/.venv"
else
    echo "✅ Python 虛擬環境已存在"
fi

echo "📦 安裝 Python 相依套件..."
"$INSTALL_DIR/.venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"
echo "✅ Python 套件安裝完成"

# ── 6. GitHub 認證 ──
echo ""
# 從 config.json 讀取 github_token
GH_TOKEN=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('github_token',''))" 2>/dev/null || echo "")
if [ -n "$GH_TOKEN" ] && [ "$GH_TOKEN" != "" ]; then
    echo "🔑 使用 config.json 中的 GitHub Token 認證..."
    echo "$GH_TOKEN" | gh auth login --with-token 2>/dev/null && echo "✅ GitHub 認證成功" || echo "⚠️  GitHub 認證失敗，請稍後在設定頁面重新填入 Token"
else
    echo "⚠️  未設定 GitHub Token，請安裝完成後在 Web UI 設定頁填入"
fi

# ── 7. 確認 Chrome ──
echo ""
if [ -d "/Applications/Google Chrome.app" ]; then
    echo "✅ Google Chrome 已安裝"
else
    echo "⚠️  未偵測到 Google Chrome，請先安裝 Chrome"
    echo "   下載: https://www.google.com/chrome/"
fi

# ── 8. 建立 logs 目錄 ──
mkdir -p "$INSTALL_DIR/logs"

# ── 9. 讀取 config 中的 port ──
CDP_PORT=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('cdp_port', 9223))" 2>/dev/null || echo "9223")
WEB_PORT=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('web_port', 9558))" 2>/dev/null || echo "9558")

# ── 10. 安裝 launchd 服務 ──
echo ""
echo "⚙️  安裝開機自啟服務..."
mkdir -p "$LAUNCH_AGENTS"

# FastAPI Web Server
sed -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    -e "s|__WEB_PORT__|$WEB_PORT|g" \
    "$INSTALL_DIR/launchd/com.fb-scraper.web.plist.template" \
    > "$LAUNCH_AGENTS/com.fb-scraper.web.plist"

# Chrome CDP
sed -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    -e "s|__CDP_PORT__|$CDP_PORT|g" \
    -e "s|__HOME__|$HOME|g" \
    "$INSTALL_DIR/launchd/com.fb-scraper.chrome.plist.template" \
    > "$LAUNCH_AGENTS/com.fb-scraper.chrome.plist"

# 載入服務
launchctl unload "$LAUNCH_AGENTS/com.fb-scraper.web.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS/com.fb-scraper.chrome.plist" 2>/dev/null || true
launchctl load "$LAUNCH_AGENTS/com.fb-scraper.web.plist"
launchctl load "$LAUNCH_AGENTS/com.fb-scraper.chrome.plist"

echo "✅ 服務已啟動"

# ── 完成 ──
echo ""
echo "═══════════════════════════════════════════════"
echo " ✅ 安裝完成！"
echo "═══════════════════════════════════════════════"
echo ""
echo "【重要】Chrome CDP 遠端偵錯模式說明"
echo "───────────────────────────────────────────────"
echo " 爬蟲需要操控一個「特殊的 Chrome 視窗」，"
echo " 這個視窗已由安裝程式自動開啟（遠端偵錯模式）。"
echo ""
echo " ⚠️  請注意："
echo "  • 不要用你平常的 Chrome 視窗操作 Facebook"
echo "  • 這個 Chrome 使用獨立的設定檔（~/.chrome-cdp）"
echo "    帳號/cookies 與平常的 Chrome 完全分開"
echo ""
echo " 如果 Chrome 沒有自動開啟，請手動執行："
echo "  \"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome\" --remote-debugging-port=$CDP_PORT --user-data-dir=$HOME/.chrome-cdp"
echo ""
echo " 驗證 CDP 是否正常：在瀏覽器開啟"
echo "  http://localhost:$CDP_PORT/json"
echo "  看到 JSON 列表代表 CDP 正常運作"
echo "───────────────────────────────────────────────"
echo ""
echo "【接下來的步驟】"
echo "  1. 在自動開啟的 Chrome 視窗中，登入 Facebook"
echo "     (第一次需要手動輸入帳號密碼)"
echo "  2. 開啟 Web 管理介面："
echo "     http://localhost:$WEB_PORT"
echo "  3. 點「設定」，填入："
echo "     - GitHub Token (repo 權限)"
echo "     - Telegram Bot Token"
echo "  4. 在 Telegram 對你的 Bot 發送 /start"
echo ""
echo "【服務管理指令】"
echo "  查看日誌: tail -f $INSTALL_DIR/logs/web.log"
echo "  停止服務: launchctl unload ~/Library/LaunchAgents/com.fb-scraper.*.plist"
echo "  啟動服務: launchctl load ~/Library/LaunchAgents/com.fb-scraper.*.plist"
echo "  移除服務: bash uninstall.sh"
echo ""
