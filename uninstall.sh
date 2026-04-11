#!/bin/bash
# ═══════════════════════════════════════════════
# FB 社團爬蟲 — 移除排程服務
# 用法: bash uninstall.sh
# ═══════════════════════════════════════════════

echo "正在移除 FB 社團爬蟲服務..."

launchctl unload ~/Library/LaunchAgents/com.fb-scraper.web.plist 2>/dev/null && echo "✅ Web 服務已停止" || echo "⚠️  Web 服務未在執行"
launchctl unload ~/Library/LaunchAgents/com.fb-scraper.chrome.plist 2>/dev/null && echo "✅ Chrome CDP 服務已停止" || echo "⚠️  Chrome CDP 服務未在執行"

rm -f ~/Library/LaunchAgents/com.fb-scraper.web.plist
rm -f ~/Library/LaunchAgents/com.fb-scraper.chrome.plist

echo ""
echo "✅ 服務已移除"
echo "   專案檔案保留在原位，如需完全刪除請手動移除專案資料夾"
