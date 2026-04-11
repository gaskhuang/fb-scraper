#!/usr/bin/env python3
"""
Facebook Group Scraper — 使用 cdp-cli 操控 Chrome，模擬真人行為爬取社團貼文。

用法（CLI）:
    python3 fb_group_scraper.py <group_url> [options]

也可透過 Web UI 呼叫 scrape_group() 函式。
"""

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path


# ──────────────────────────────────────────────
# 反偵測：模擬真人行為的參數
# ──────────────────────────────────────────────
HUMAN_SCROLL_MIN = 300
HUMAN_SCROLL_MAX = 900
HUMAN_SCROLL_PAUSE_MIN = 1.5
HUMAN_SCROLL_PAUSE_MAX = 4.0
HUMAN_JITTER = 0.3
PAGE_LOAD_WAIT = 3.0
try:
    from scripts.config_loader import get_cdp_url as _get_cdp_url
except ImportError:
    from config_loader import get_cdp_url as _get_cdp_url
_cdp_url = _get_cdp_url()


def _noop_log(msg):
    print(msg)


def human_sleep(base_min=1.0, base_max=2.0):
    """模擬真人的隨機等待時間"""
    base = random.uniform(base_min, base_max)
    jitter = base * random.uniform(-HUMAN_JITTER, HUMAN_JITTER)
    time.sleep(max(0.5, base + jitter))


def human_scroll_distance():
    return random.randint(HUMAN_SCROLL_MIN, HUMAN_SCROLL_MAX)


def cdp(cmd, timeout=15):
    full_cmd = f"cdp-cli --cdp-url {_cdp_url} {cmd}"
    try:
        result = subprocess.run(
            full_cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            try:
                return json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                return {"raw": result.stdout.strip()}
        else:
            stderr = result.stderr.strip() or result.stdout.strip()
            try:
                return json.loads(stderr)
            except Exception:
                return {"error": True, "message": stderr}
    except subprocess.TimeoutExpired:
        return {"error": True, "message": "timeout"}


def cdp_eval(page_match, js_code, timeout=20):
    escaped = js_code.replace("'", "'\\''")
    result = cdp(f"eval \"{page_match}\" '{escaped}'", timeout=timeout)
    if isinstance(result, dict) and result.get("success") and "value" in result:
        try:
            return json.loads(result["value"])
        except (json.JSONDecodeError, TypeError):
            return result["value"]
    return result


# ──────────────────────────────────────────────
# 核心爬蟲邏輯
# ──────────────────────────────────────────────

def ensure_chrome(log=_noop_log):
    tabs = cdp("tabs")
    if isinstance(tabs, dict) and tabs.get("error"):
        log("🚀 啟動 Chrome（debug 模式）...")
        result = cdp("launch", timeout=15)
        if isinstance(result, dict) and result.get("error"):
            log(f"❌ 無法啟動 Chrome: {result.get('message')}")
            raise RuntimeError("Chrome launch failed")
        time.sleep(2)
        tabs = cdp("tabs")

    if isinstance(tabs, list):
        log(f"✅ Chrome 已連接，{len(tabs)} 個分頁")
    elif isinstance(tabs, dict) and not tabs.get("error"):
        log("✅ Chrome 已連接")
    return tabs


def navigate_to_group(group_url, log=_noop_log):
    log(f"📍 導航到 {group_url}")

    tabs = cdp("tabs")
    page_id = None
    if isinstance(tabs, list):
        page_id = tabs[0].get("title", tabs[0].get("id", ""))
    elif isinstance(tabs, dict) and tabs.get("title"):
        page_id = tabs["title"]

    if not page_id:
        cdp(f'new "{group_url}"')
        time.sleep(PAGE_LOAD_WAIT)
        tabs = cdp("tabs")
        if isinstance(tabs, list):
            page_id = tabs[0].get("title", "")
        elif isinstance(tabs, dict):
            page_id = tabs.get("title", "")
    else:
        cdp(f'go "{page_id}" "{group_url}"')
        time.sleep(PAGE_LOAD_WAIT)
        tabs = cdp("tabs")
        if isinstance(tabs, list):
            page_id = tabs[0].get("title", "")
        elif isinstance(tabs, dict):
            page_id = tabs.get("title", "")

    human_sleep(2.0, 4.0)

    tabs = cdp("tabs")
    if isinstance(tabs, list) and tabs:
        for tab in tabs:
            if "facebook.com" in tab.get("url", ""):
                page_id = tab["title"]
                break
    elif isinstance(tabs, dict) and "facebook.com" in tabs.get("url", ""):
        page_id = tabs["title"]

    log(f"📄 頁面: {page_id}")
    return page_id


def check_login(page_match, log=_noop_log, web_mode=False):
    result = cdp_eval(page_match, """
    (function(){
        var loginModal = document.querySelector('[data-testid="royal_login_form"]');
        var loginBtn = document.querySelector('button[name="login"]');
        var hasLoginPrompt = document.body.innerText.includes('在 Facebook 查看更多');
        return JSON.stringify({needsLogin: !!(loginModal || loginBtn || hasLoginPrompt)});
    })()
    """)

    if isinstance(result, dict) and result.get("needsLogin"):
        log("⚠️  需要登入 Facebook！請在 Chrome 視窗中手動登入。")
        if web_mode:
            # 在 web 模式下輪詢等待登入（最多 2 分鐘）
            log("⏳ 等待登入中（最多 120 秒）...")
            for i in range(24):
                time.sleep(5)
                check = cdp_eval(page_match, """
                (function(){
                    var loginModal = document.querySelector('[data-testid="royal_login_form"]');
                    var loginBtn = document.querySelector('button[name="login"]');
                    var hasLoginPrompt = document.body.innerText.includes('在 Facebook 查看更多');
                    return JSON.stringify({needsLogin: !!(loginModal || loginBtn || hasLoginPrompt)});
                })()
                """)
                if isinstance(check, dict) and not check.get("needsLogin"):
                    log("✅ 登入成功！")
                    return True
                if i % 6 == 5:
                    log(f"   仍在等待登入... ({(i+1)*5}s)")
            log("❌ 等待登入逾時")
        else:
            log("   完成後按 Enter 繼續...")
            input()
        human_sleep(2.0, 3.0)
        return True
    return False


def human_scroll_down(page_match, times=1):
    for i in range(times):
        distance = human_scroll_distance()

        if random.random() < 0.1:
            distance = random.randint(100, 200)
        elif random.random() < 0.1:
            distance = random.randint(1200, 1800)

        cdp_eval(page_match, f"window.scrollBy(0, {distance})")
        human_sleep(HUMAN_SCROLL_PAUSE_MIN, HUMAN_SCROLL_PAUSE_MAX)

        if random.random() < 0.05:
            human_sleep(3.0, 6.0)

        if random.random() < 0.03:
            back_distance = random.randint(100, 300)
            cdp_eval(page_match, f"window.scrollBy(0, -{back_distance})")
            human_sleep(1.0, 2.0)
            cdp_eval(page_match, f"window.scrollBy(0, {back_distance + 100})")
            human_sleep(0.5, 1.0)


def click_see_more(page_match):
    result = cdp_eval(page_match, """
    (function(){
        var feed = document.querySelector('[role="feed"]');
        if (!feed) return JSON.stringify({clicked: 0});
        var clicked = 0;
        feed.querySelectorAll('div[role="button"], span[role="button"]').forEach(function(el) {
            var t = el.textContent.trim();
            if (t === '查看更多' || t === '顯示更多') {
                el.click();
                clicked++;
            }
        });
        return JSON.stringify({clicked: clicked});
    })()
    """)
    n = result.get("clicked", 0) if isinstance(result, dict) else 0
    if n > 0:
        human_sleep(1.0, 2.0)
    return n


def extract_posts(page_match):
    js = """
    (function(){
        var feed = document.querySelector('[role="feed"]');
        if (!feed) return JSON.stringify([]);
        var children = Array.from(feed.children);
        var posts = [];

        // 嘗試多種 aria-label 找 reaction bar（Facebook 會因語言/版本不同而改變）
        var REACTION_LABELS = [
            '看看誰對這個傳達了心情',
            '查看對此表情符號的回應',
            'See who reacted to this',
            'Reactions',
            '心情'
        ];

        function findReactionBar(el) {
            for (var i = 0; i < REACTION_LABELS.length; i++) {
                var bar = el.querySelector('[aria-label*="' + REACTION_LABELS[i] + '"]');
                if (bar) return bar;
            }
            return null;
        }

        function extractNumbers(el) {
            // 先嘗試從 reaction bar 往上找數字區域
            var area = el;
            for (var j = 0; j < 4; j++) {
                if (area.parentElement) area = area.parentElement;
            }
            var text = area.innerText.trim();
            var nums = text.split('\\n')
                .map(function(s){ return s.trim().replace(/,/g,'').replace(/[^0-9]/g,''); })
                .filter(function(s){ return /^\\d+$/.test(s) && s.length < 8; })
                .map(Number);
            return { likes: nums[0]||0, comments: nums[1]||0, shares: nums[2]||0 };
        }

        // 判斷 child 是否為貼文容器的備用方法：找 timestamp 連結
        var timePattern = /^\\d+\\s*(小時|分鐘|天|秒|週|hr|min|hours|minutes)/;
        var datePattern = /^\\d+月\\d+日/;

        function hasTimestamp(el) {
            var links = el.querySelectorAll('a');
            for (var k = 0; k < links.length; k++) {
                var lt = links[k].textContent.trim();
                if (timePattern.test(lt) || datePattern.test(lt) || lt === '昨天' || lt === 'Yesterday') {
                    return true;
                }
            }
            return false;
        }

        children.forEach(function(child) {
            // 方法一：找 reaction bar（最可靠）
            var reactionBar = findReactionBar(child);

            // 方法二：備用 — child 包含 timestamp 連結就視為貼文
            if (!reactionBar && !hasTimestamp(child)) return;

            var likes = 0, comments = 0, shares = 0;
            if (reactionBar) {
                var counts = extractNumbers(reactionBar);
                likes = counts.likes; comments = counts.comments; shares = counts.shares;
            }

            // 作者
            var author = '';
            var userLinks = child.querySelectorAll('a[href*="/user/"], a[href*="/profile.php"]');
            for (var k = 0; k < userLinks.length; k++) {
                var t = userLinks[k].textContent.trim();
                if (t.length > 1 && t.length < 60) { author = t; break; }
            }
            // 備用：找 strong 標籤
            if (!author) {
                var strong = child.querySelector('h2 a, h3 a, strong a');
                if (strong) author = strong.textContent.trim();
            }

            // 時間戳記 + 貼文連結
            var timestamp = '';
            var postUrl = '';
            var allLinks = child.querySelectorAll('a');
            for (var k = 0; k < allLinks.length; k++) {
                var lt = allLinks[k].textContent.trim();
                if (!timestamp && (timePattern.test(lt) || datePattern.test(lt) || lt === '昨天' || lt === 'Yesterday')) {
                    timestamp = lt;
                    var href = allLinks[k].href || '';
                    if (href.indexOf('facebook.com') !== -1) {
                        postUrl = href.split('?')[0];
                    }
                    break;
                }
            }

            // 貼文內容
            var msgText = '';
            var msgEl = child.querySelector('[data-ad-preview="message"]') ||
                        child.querySelector('[data-ad-comet-preview="message"]') ||
                        child.querySelector('[data-testid="post_message"]');
            if (msgEl) {
                msgText = msgEl.innerText.trim();
            }
            if (!msgText) {
                var dirAuto = child.querySelectorAll('div[dir="auto"]');
                var parts = [];
                var seen = new Set();
                dirAuto.forEach(function(d) {
                    var dt = d.innerText.trim();
                    if (dt.length > 15 &&
                        !seen.has(dt) &&
                        dt.indexOf('查看更多留言') === -1 &&
                        dt.indexOf('的身分留言') === -1 &&
                        dt.indexOf('社團動態') === -1 &&
                        dt.indexOf('Comment as') === -1) {
                        seen.add(dt);
                        parts.push(dt);
                    }
                });
                // 取最長的那段作為主要內容
                if (parts.length > 0) {
                    msgText = parts.sort(function(a,b){ return b.length - a.length; })[0];
                }
            }

            // 圖片
            var imgUrls = [];
            child.querySelectorAll('img').forEach(function(img) {
                var src = img.getAttribute('src') || '';
                if (src.indexOf('scontent') !== -1 && (img.naturalWidth > 100 || img.width > 100)) {
                    imgUrls.push(src);
                }
            });

            // 至少要有 author 或 text 才算有效貼文
            if (!author && !msgText) return;

            posts.push({
                author: author, timestamp: timestamp,
                likes: likes, comments: comments, shares: shares,
                text: msgText, images: imgUrls, post_url: postUrl
            });
        });

        return JSON.stringify(posts);
    })()
    """
    return cdp_eval(page_match, js) or []


def parse_time_ago(ts):
    if not ts:
        return float("inf")
    m = re.match(r"(\d+)\s*(秒)", ts)
    if m:
        return int(m.group(1)) / 3600
    m = re.match(r"(\d+)\s*(分鐘)", ts)
    if m:
        return int(m.group(1)) / 60
    m = re.match(r"(\d+)\s*(小時)", ts)
    if m:
        return int(m.group(1))
    m = re.match(r"(\d+)\s*(天)", ts)
    if m:
        return int(m.group(1)) * 24
    if ts == "昨天":
        return 24
    m = re.match(r"(\d+)\s*(週)", ts)
    if m:
        return int(m.group(1)) * 7 * 24
    m = re.match(r"(\d+)月(\d+)日", ts)
    if m:
        now = datetime.now()
        post_date = now.replace(month=int(m.group(1)), day=int(m.group(2)))
        if post_date > now:
            post_date = post_date.replace(year=now.year - 1)
        return (now - post_date).total_seconds() / 3600
    return float("inf")


def download_image(url, output_path, log=_noop_log, retries=2):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                "Referer": "https://www.facebook.com/",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                with open(output_path, "wb") as f:
                    f.write(data)
            return True
        except Exception as e:
            if attempt < retries:
                human_sleep(1.0, 3.0)
            else:
                log(f"    ⚠️  下載失敗: {output_path} ({e})")
                return False


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

def scrape_group(
    group_url,
    top_n=10,
    min_likes=0,
    min_comments=0,
    min_shares=0,
    within_hours=None,
    max_rounds=200,
    output_dir=None,
    log=None,
    web_mode=False,
    stop_flag=None,
):
    """
    爬取 Facebook 社團貼文主流程。

    Args:
        group_url: 社團 URL
        top_n: 抓取前 N 篇貼文（0 = 不限，全抓）
        min_likes: 最低讚數
        min_comments: 最低留言數
        min_shares: 最低分享數
        within_hours: 時間範圍（小時），None=不限
        max_rounds: 最大滾動輪數（預設 200）
        output_dir: 輸出目錄
        log: 日誌回呼函式（預設 print）
        web_mode: 是否為 Web 模式（不會呼叫 input()）
        stop_flag: threading.Event，設定時中止爬取
    """
    if log is None:
        log = _noop_log

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    if output_dir is None:
        output_dir = os.path.join(os.getcwd(), f"output_{timestamp_str}")

    os.makedirs(output_dir, exist_ok=True)

    # 1. 確保 Chrome 可用
    ensure_chrome(log=log)

    # 2. 導航到社團
    page_match = navigate_to_group(group_url, log=log)

    # 3. 檢查登入狀態
    human_sleep(1.0, 2.0)
    check_login(page_match, log=log, web_mode=web_mode)

    # 4. 重新取得 page match
    tabs = cdp("tabs")
    if isinstance(tabs, list):
        for tab in tabs:
            if "facebook.com" in tab.get("url", ""):
                page_match = tab["title"]
                break
    elif isinstance(tabs, dict):
        page_match = tabs.get("title", page_match)

    # 從 tab 標題取得社團名稱
    group_name = page_match.replace(" | Facebook", "").strip() if page_match else ""

    has_filter = min_likes > 0 or min_comments > 0 or min_shares > 0 or within_hours
    target_label = f"目標: {'符合條件的' if has_filter else ''}{top_n if top_n > 0 else '所有'} 篇"

    log(f"\n📊 開始爬取（{target_label}，最多滾動 {max_rounds} 輪）")
    if min_likes > 0:
        log(f"   篩選: ≥{min_likes} 讚")
    if min_comments > 0:
        log(f"   篩選: ≥{min_comments} 留言")
    if min_shares > 0:
        log(f"   篩選: ≥{min_shares} 分享")
    if within_hours:
        log(f"   篩選: {within_hours} 小時內")

    # 5. 滾動 + 擷取循環
    all_posts = []
    seen_texts = set()
    no_new_count = 0

    for round_num in range(1, max_rounds + 1):
        # 檢查停止信號
        if stop_flag and stop_flag.is_set():
            log("\n⏹️  收到停止信號，中止爬取")
            break

        scroll_times = random.randint(3, 6)
        log(f"\n🔄 第 {round_num}/{max_rounds} 輪滾動 ({scroll_times} 次)...")
        human_scroll_down(page_match, times=scroll_times)

        clicked = click_see_more(page_match)
        if clicked > 0:
            log(f"   📖 展開了 {clicked} 篇貼文")
            human_sleep(1.0, 2.0)

        posts = extract_posts(page_match)
        if not isinstance(posts, list):
            log("   ⚠️  提取失敗，重試...")
            human_sleep(2.0, 4.0)
            continue

        new_count = 0
        for p in posts:
            p["group_url"] = group_url
            p["group_name"] = group_name
            # 用 (作者 + 時間戳 + 文字前50字) 組合做唯一識別，避免過度去重
            author_sig = p.get("author", "")
            time_sig = p.get("timestamp", "")
            text_sig = (p.get("text", "") or "")[:50]
            post_url_sig = p.get("post_url", "")
            # 優先用 post_url，其次用 author+timestamp+text 組合
            if post_url_sig:
                sig = post_url_sig
            elif author_sig and time_sig:
                sig = f"{author_sig}|{time_sig}|{text_sig}"
            elif text_sig:
                sig = text_sig
            else:
                sig = author_sig
            if sig and sig not in seen_texts:
                seen_texts.add(sig)
                all_posts.append(p)
                new_count += 1

        log(f"   📝 發現 {len(posts)} 篇 (新增 {new_count}，累計 {len(all_posts)})")

        # 篩選
        qualified = _filter_posts(all_posts, min_likes, min_comments, min_shares, within_hours)

        if has_filter:
            log(f"   ✅ 符合篩選條件: {len(qualified)} 篇")
            if top_n > 0 and len(qualified) >= top_n:
                log(f"\n🎯 已蒐集到 {top_n} 篇符合條件的貼文！")
                break
        else:
            if top_n > 0 and len(all_posts) >= top_n:
                log(f"\n🎯 已蒐集到 {top_n} 篇貼文！")
                break

        if new_count == 0:
            no_new_count += 1
            log(f"   ⏳ 連續 {no_new_count} 輪無新貼文（上限 {max_rounds} 輪）")
        else:
            no_new_count = 0

        # 模擬真人：偶爾回到頂部
        if random.random() < 0.05 and round_num > 3:
            log("   ↩️  模擬回到頂部瀏覽...")
            cdp_eval(page_match, "window.scrollTo(0, 0)")
            human_sleep(2.0, 4.0)
            human_scroll_down(page_match, times=random.randint(2, 4))

    # 6. 篩選 & 排序
    if has_filter:
        final_posts = qualified
    else:
        final_posts = all_posts

    if top_n > 0:
        final_posts = final_posts[:top_n]

    log(f"\n📦 最終結果: {len(final_posts)} 篇貼文")

    # 7. 儲存結果
    save_results(final_posts, output_dir, log=log)

    # 8. 自動生成瀏覽器 HTML（僅 CLI 模式；web_mode 由 main.py 統一產生）
    if not web_mode:
        try:
            from scripts.generate import generate_html
        except ImportError:
            from generate import generate_html
        try:
            html_path = generate_html(output_dir)
            log(f"🌐 瀏覽器 HTML 已生成: {html_path}")
        except Exception as e:
            log(f"⚠️  HTML 產生失敗: {e}")

    return final_posts


def _filter_posts(posts, min_likes, min_comments, min_shares, within_hours):
    qualified = []
    for p in posts:
        hours = parse_time_ago(p.get("timestamp", ""))
        if within_hours and hours > within_hours:
            continue
        if p.get("likes", 0) < min_likes:
            continue
        if p.get("comments", 0) < min_comments:
            continue
        if p.get("shares", 0) < min_shares:
            continue
        qualified.append(p)
    return qualified


def save_results(posts, output_dir, log=_noop_log):
    json_path = os.path.join(output_dir, "all_posts.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    log(f"\n💾 JSON 已儲存: {json_path}")

    total_images = 0

    for i, post in enumerate(posts):
        num = i + 1
        author = post.get("author", "").replace("/", "_").replace(" ", "_") or f"unknown_{num}"
        dirname = f"post{num:02d}_{author}"
        postdir = os.path.join(output_dir, dirname)
        os.makedirs(postdir, exist_ok=True)

        content = f"""# 貼文 {num} — {post.get('author', '(未知)')}

**作者:** {post.get('author', '(未知)')}
**時間:** {post.get('timestamp', '(未知)')}
**讚:** {post.get('likes', 0):,} | **留言:** {post.get('comments', 0)} | **分享:** {post.get('shares', 0)}

---

## 內容

{post.get('text', '(無法提取文字)')}

---

## 圖片: {len(post.get('images', []))} 張
"""
        for j in range(len(post.get("images", []))):
            content += f"- image_{j+1}.jpg\n"

        with open(os.path.join(postdir, "content.md"), "w", encoding="utf-8") as f:
            f.write(content)

        images = post.get("images", [])
        for j, img_url in enumerate(images):
            img_path = os.path.join(postdir, f"image_{j+1}.jpg")
            download_image(img_url, img_path, log=log)
            total_images += 1
            if j < len(images) - 1:
                human_sleep(0.3, 1.0)

        log(f"  ✅ {dirname}: {len(post.get('text', ''))} 字, {len(images)} 張圖片")

        if i < len(posts) - 1:
            human_sleep(0.5, 1.5)

    log(f"\n🏁 完成！共 {len(posts)} 篇貼文, {total_images} 張圖片")
    log(f"📁 輸出目錄: {output_dir}")


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def parse_within(value):
    if not value:
        return None
    m = re.match(r"(\d+)\s*(h|d|w)", value.lower())
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit == "h":
            return n
        elif unit == "d":
            return n * 24
        elif unit == "w":
            return n * 7 * 24
    try:
        return int(value)
    except ValueError:
        return None


def main():
    global _cdp_url
    parser = argparse.ArgumentParser(description="Facebook Group Scraper")
    parser.add_argument("group_url", help="Facebook 社團 URL")
    parser.add_argument("--top", type=int, default=10, help="抓取前 N 篇 (預設 10, 0=不限)")
    parser.add_argument("--min-likes", type=int, default=0)
    parser.add_argument("--min-comments", type=int, default=0)
    parser.add_argument("--min-shares", type=int, default=0)
    parser.add_argument("--within", type=str, default=None, help="如 24h, 3d, 1w")
    parser.add_argument("--max-rounds", type=int, default=200, help="最大滾動輪數 (預設 200)")
    parser.add_argument("--output", "-o", type=str, default=None)
    parser.add_argument("--cdp-url", type=str, default=_cdp_url)

    args = parser.parse_args()
    _cdp_url = args.cdp_url

    scrape_group(
        group_url=args.group_url,
        top_n=args.top,
        min_likes=args.min_likes,
        min_comments=args.min_comments,
        min_shares=args.min_shares,
        within_hours=parse_within(args.within),
        max_rounds=args.max_rounds,
        output_dir=args.output,
    )


if __name__ == "__main__":
    main()
