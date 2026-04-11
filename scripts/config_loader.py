"""統一設定讀取模組 — 所有腳本從 config.json 讀取設定"""

import json
from pathlib import Path

_config_path = Path(__file__).resolve().parent.parent / "config.json"

_defaults = {
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "github_repo": "",
    "github_token": "",
    "cdp_port": 9223,
    "web_port": 9558,
}


def load_config() -> dict:
    """讀取 config.json，缺少的欄位用預設值補齊"""
    try:
        with open(_config_path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = {}
    merged = {**_defaults, **cfg}
    return merged


def save_config(data: dict):
    """寫入 config.json"""
    with open(_config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    f.close()


def get_cdp_url() -> str:
    """回傳 CDP URL，例如 http://localhost:9223"""
    cfg = load_config()
    return f"http://localhost:{cfg['cdp_port']}"
