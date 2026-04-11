"""Telegram 通知模組 — 爬取完成後發送報告連結"""

import json
import urllib.request
import urllib.error

try:
    from scripts.config_loader import load_config
except ImportError:
    from config_loader import load_config


def send_telegram(message: str, log=print) -> bool:
    """發送 Telegram 訊息。

    Args:
        message: 要發送的文字訊息
        log: 日誌函式

    Returns:
        是否成功
    """
    cfg = load_config()
    token = cfg.get("telegram_bot_token", "")
    chat_id = cfg.get("telegram_chat_id", "")

    if not token or not chat_id:
        log("⚠️  Telegram 未設定（缺少 bot token 或 chat_id），跳過通知")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                log("📨 Telegram 通知已發送")
                return True
            else:
                log(f"⚠️  Telegram 發送失敗: HTTP {resp.status}")
                return False
    except urllib.error.URLError as e:
        log(f"⚠️  Telegram 發送失敗: {e}")
        return False
    except Exception as e:
        log(f"⚠️  Telegram 發送失敗: {e}")
        return False


def notify_scrape_done(group_count: int, post_count: int, report_url: str = "", log=print):
    """爬取完成後發送通知摘要"""
    lines = [
        "<b>📊 FB 社團爬蟲完成</b>",
        f"社團數: {group_count} | 貼文數: {post_count}",
    ]
    if report_url:
        lines.append(f'📄 <a href="{report_url}">查看報告</a>')
    message = "\n".join(lines)
    send_telegram(message, log=log)


def detect_chat_id(bot_token: str) -> str | None:
    """用 getUpdates API 偵測最近對 bot 發訊息的 chat_id。

    Returns:
        chat_id 字串，或 None（如果沒有訊息）
    """
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates?limit=10&offset=-10"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok") and data.get("result"):
                # 取最新的 private message chat_id
                for update in reversed(data["result"]):
                    msg = update.get("message", {})
                    chat = msg.get("chat", {})
                    if chat.get("type") == "private":
                        return str(chat["id"])
                # 如果沒有 private，取任何 chat
                for update in reversed(data["result"]):
                    msg = update.get("message", {})
                    chat = msg.get("chat", {})
                    if chat.get("id"):
                        return str(chat["id"])
    except Exception:
        pass
    return None
