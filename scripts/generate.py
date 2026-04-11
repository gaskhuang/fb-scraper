#!/usr/bin/env python3
"""讀取爬蟲資料，生成自包含的 FB 貼文瀏覽器 HTML。

用法:
    python3 generate.py <data_dir>
    python3 generate.py  # 自動找最新的 output 資料夾
"""

import json
import base64
import html
import os
import sys
from datetime import datetime
from pathlib import Path


def load_posts(data_dir: Path) -> list[dict]:
    json_path = data_dir / "all_posts.json"
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_local_images(data_dir: Path, post_index: int) -> list[str]:
    """找到對應資料夾的本地圖片，回傳 base64 data URI 列表"""
    folder = None
    for d in sorted(data_dir.iterdir()):
        if d.is_dir() and d.name.startswith(f"post{post_index + 1:02d}_"):
            folder = d
            break

    if not folder:
        return []

    images = []
    for img_path in sorted(folder.glob("image_*.jpg")):
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
            images.append(f"data:image/jpeg;base64,{b64}")
    return images


def escape(text: str) -> str:
    return html.escape(text)


def format_number(n: int) -> str:
    return f"{n:,}"


def build_post_html(index: int, post: dict, images: list[str]) -> str:
    author = escape(post["author"])
    first_char = post["author"][0] if post["author"] else "?"
    timestamp = escape(post.get("timestamp", "") or "")
    if timestamp and not timestamp.endswith("前"):
        timestamp += "前"
    text = escape(post.get("text", ""))
    likes = format_number(post.get("likes", 0))
    comments = format_number(post.get("comments", 0))
    shares = format_number(post.get("shares", 0))

    if len(images) == 0:
        img_html = ""
    elif len(images) == 1:
        img_html = f'''<div class="image-grid single">
      <img src="{images[0]}" alt="貼文圖片" onclick="openLightbox(this.src)" loading="lazy">
    </div>'''
    else:
        imgs = "\n      ".join(
            f'<img src="{src}" alt="貼文圖片" onclick="openLightbox(this.src)" loading="lazy">'
            for src in images
        )
        img_html = f'<div class="image-grid multi">\n      {imgs}\n    </div>'

    return f'''  <div class="card">
    <div class="card-header">
      <div class="avatar">{first_char}</div>
      <div class="author-info">
        <div class="author-name">{author}</div>
        <div class="post-time">{timestamp}</div>
      </div>
      <span class="post-number">#{index + 1}</span>
    </div>
    {img_html}
    <div class="card-body">
      <p>{text}</p>
    </div>
    <div class="card-stats">
      <span class="stat"><span class="stat-icon">&#x1F44D;</span> {likes}</span>
      <span class="stat"><span class="stat-icon">&#x1F4AC;</span> {comments}</span>
      <span class="stat"><span class="stat-icon">&#x1F504;</span> {shares}</span>
    </div>
  </div>'''


CSS = """
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f0f2f5;
    color: #1c1e21;
    line-height: 1.6;
  }
  .header {
    background: #fff;
    border-bottom: 1px solid #ddd;
    padding: 16px 0;
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: 0 2px 4px rgba(0,0,0,0.08);
  }
  .header-inner {
    max-width: 680px;
    margin: 0 auto;
    padding: 0 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .header h1 {
    font-size: 20px;
    font-weight: 700;
    color: #1877f2;
  }
  .header h1 .timestamp {
    font-weight: 400;
    font-size: 14px;
    color: #65676b;
  }
  .header .post-count {
    font-size: 14px;
    color: #65676b;
  }
  .container {
    max-width: 680px;
    margin: 0 auto;
    padding: 16px;
  }
  .card {
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    margin-bottom: 20px;
    overflow: hidden;
  }
  .card-header {
    display: flex;
    align-items: center;
    padding: 16px 16px 12px;
    gap: 12px;
  }
  .avatar {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: #1877f2;
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    font-weight: 700;
    flex-shrink: 0;
  }
  .author-info .author-name {
    font-weight: 600;
    font-size: 15px;
    color: #050505;
  }
  .author-info .post-time {
    font-size: 13px;
    color: #65676b;
  }
  .post-number {
    margin-left: auto;
    background: #e4e6eb;
    color: #65676b;
    font-size: 12px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 16px;
  }
  .card-body {
    padding: 0 16px 12px;
  }
  .card-body p {
    font-size: 15px;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .card-stats {
    display: flex;
    gap: 16px;
    padding: 8px 16px;
    border-top: 1px solid #e4e6eb;
    font-size: 14px;
    color: #65676b;
  }
  .stat {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .stat-icon {
    font-size: 16px;
  }
  .image-grid {
    padding: 0;
  }
  .image-grid img {
    width: 100%;
    display: block;
    cursor: pointer;
    transition: opacity 0.2s;
  }
  .image-grid img:hover {
    opacity: 0.92;
  }
  .image-grid.multi {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 2px;
  }
  .image-grid.multi img {
    aspect-ratio: 1;
    object-fit: cover;
  }
  .image-grid.single img {
    max-height: 500px;
    object-fit: contain;
    background: #f0f2f5;
  }
  .lightbox {
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.9);
    z-index: 1000;
    align-items: center;
    justify-content: center;
    cursor: pointer;
  }
  .lightbox.active { display: flex; }
  .lightbox img {
    max-width: 95vw;
    max-height: 95vh;
    object-fit: contain;
    border-radius: 4px;
  }
  .back-top {
    position: fixed;
    bottom: 24px;
    right: 24px;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: #1877f2;
    color: #fff;
    border: none;
    font-size: 20px;
    cursor: pointer;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    display: none;
    align-items: center;
    justify-content: center;
  }
  .back-top.visible { display: flex; }
  @media (max-width: 480px) {
    .container { padding: 8px; }
    .card { border-radius: 8px; margin-bottom: 12px; }
    .card-header { padding: 12px 12px 8px; }
    .card-body { padding: 0 12px 8px; }
    .card-stats { padding: 8px 12px; }
  }
"""

JS = """
function openLightbox(src) {
  document.getElementById('lightbox-img').src = src;
  document.getElementById('lightbox').classList.add('active');
}
function closeLightbox() {
  document.getElementById('lightbox').classList.remove('active');
}
window.addEventListener('scroll', () => {
  document.getElementById('backTop').classList.toggle('visible', window.scrollY > 400);
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLightbox(); });
"""


def generate_html(data_dir: str | Path, output_path: str | Path | None = None) -> Path:
    """從 data_dir 讀取爬蟲資料，生成 HTML 檔案。

    Args:
        data_dir: 包含 all_posts.json 和 post 資料夾的目錄
        output_path: HTML 輸出路徑，預設為 data_dir/index.html

    Returns:
        生成的 HTML 檔案路徑
    """
    data_dir = Path(data_dir)
    if output_path is None:
        output_path = data_dir / "index.html"
    else:
        output_path = Path(output_path)

    posts = load_posts(data_dir)
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    post_count = len(posts)

    cards = []
    for i, post in enumerate(posts):
        images = get_local_images(data_dir, i)
        cards.append(build_post_html(i, post, images))

    cards_html = "\n\n".join(cards)

    html_content = f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FB 貼文瀏覽器</title>
<style>{CSS}</style>
</head>
<body>

<div class="header">
  <div class="header-inner">
    <h1>FB 貼文瀏覽器 <span class="timestamp">{now}</span></h1>
    <span class="post-count">共 {post_count} 篇貼文</span>
  </div>
</div>

<div class="container">

{cards_html}

</div>

<div class="lightbox" id="lightbox" onclick="closeLightbox()">
  <img id="lightbox-img" src="" alt="放大圖片">
</div>

<button class="back-top" id="backTop" onclick="window.scrollTo({{top:0,behavior:'smooth'}})">&#8593;</button>

<script>{JS}</script>
</body>
</html>'''

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_path


UNIFIED_CSS_EXTRA = """
  .group-nav {
    position: sticky;
    top: 53px;
    z-index: 99;
    background: #fff;
    border-bottom: 1px solid #ddd;
    padding: 8px 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }
  .group-nav-inner {
    max-width: 680px;
    margin: 0 auto;
    padding: 4px 16px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .group-pill {
    flex-shrink: 0;
    padding: 6px 14px;
    border-radius: 20px;
    background: #e4e6eb;
    color: #050505;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    text-decoration: none;
    border: none;
    white-space: nowrap;
    transition: all 0.2s;
  }
  .group-pill:hover, .group-pill.active { background: #1877f2; color: #fff; }
  .group-section-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 24px 0 12px;
    border-bottom: 2px solid #1877f2;
    margin-bottom: 16px;
  }
  .group-section-header h2 {
    font-size: 18px;
    font-weight: 700;
    color: #050505;
  }
  .group-section-header .group-meta {
    font-size: 13px;
    color: #65676b;
  }
  .group-section-header a {
    margin-left: auto;
    font-size: 13px;
    color: #1877f2;
    text-decoration: none;
  }
  .group-section-header a:hover { text-decoration: underline; }
  .group-badge {
    display: inline-block;
    background: #e7f3ff;
    color: #1877f2;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 10px;
    margin-left: 8px;
  }
  .post-link {
    display: inline-block;
    margin-top: 8px;
    padding: 6px 14px;
    background: #e4e6eb;
    color: #050505;
    font-size: 13px;
    border-radius: 6px;
    text-decoration: none;
    transition: background 0.2s;
  }
  .post-link:hover { background: #d0d2d6; }
  .post-time a {
    color: #65676b;
    text-decoration: none;
  }
  .post-time a:hover { text-decoration: underline; }
"""

UNIFIED_JS_EXTRA = """
// Group nav active state
var pills = document.querySelectorAll('.group-pill');
var sections = document.querySelectorAll('.group-section');
function updateActivePill() {
  var scrollY = window.scrollY + 120;
  var active = null;
  sections.forEach(function(sec) {
    if (sec.offsetTop <= scrollY) active = sec.id;
  });
  pills.forEach(function(pill) {
    pill.classList.toggle('active', pill.getAttribute('href') === '#' + active);
  });
}
window.addEventListener('scroll', updateActivePill);
updateActivePill();
"""


def build_unified_post_html(index: int, post: dict, images: list[str], group_label: str) -> str:
    """建立帶社團標籤和原文連結的貼文卡片"""
    author = escape(post["author"])
    first_char = post["author"][0] if post["author"] else "?"
    timestamp = escape(post.get("timestamp", "") or "")
    if timestamp and not timestamp.endswith("前"):
        timestamp += "前"
    text = escape(post.get("text", ""))
    likes = format_number(post.get("likes", 0))
    comments = format_number(post.get("comments", 0))
    shares = format_number(post.get("shares", 0))
    post_url = post.get("post_url", "")

    # 時間戳記可點擊跳到原文
    if post_url:
        time_html = f'<a href="{escape(post_url)}" target="_blank" rel="noopener">{timestamp}</a>'
    else:
        time_html = timestamp

    if len(images) == 0:
        img_html = ""
    elif len(images) == 1:
        img_html = f'''<div class="image-grid single">
      <img src="{images[0]}" alt="貼文圖片" onclick="openLightbox(this.src)" loading="lazy">
    </div>'''
    else:
        imgs = "\n      ".join(
            f'<img src="{src}" alt="貼文圖片" onclick="openLightbox(this.src)" loading="lazy">'
            for src in images
        )
        img_html = f'<div class="image-grid multi">\n      {imgs}\n    </div>'

    # 原文連結按鈕
    link_html = ""
    if post_url:
        link_html = f'<a class="post-link" href="{escape(post_url)}" target="_blank" rel="noopener">前往原文 ↗</a>'

    return f'''  <div class="card">
    <div class="card-header">
      <div class="avatar">{first_char}</div>
      <div class="author-info">
        <div class="author-name">{author}<span class="group-badge">{escape(group_label)}</span></div>
        <div class="post-time">{time_html}</div>
      </div>
      <span class="post-number">#{index + 1}</span>
    </div>
    {img_html}
    <div class="card-body">
      <p>{text}</p>
      {link_html}
    </div>
    <div class="card-stats">
      <span class="stat"><span class="stat-icon">&#x1F44D;</span> {likes}</span>
      <span class="stat"><span class="stat-icon">&#x1F4AC;</span> {comments}</span>
      <span class="stat"><span class="stat-icon">&#x1F504;</span> {shares}</span>
    </div>
  </div>'''


def generate_unified_html(base_dir: str | Path, output_path: str | Path | None = None) -> Path:
    """從多個社團子目錄產生統一 HTML 報告。

    Args:
        base_dir: 包含 01_xxx/, 02_xxx/ 等子目錄的根目錄
        output_path: HTML 輸出路徑，預設為 base_dir/index.html

    Returns:
        生成的 HTML 檔案路徑
    """
    import re as _re
    base_dir = Path(base_dir)
    if output_path is None:
        output_path = base_dir / "index.html"
    else:
        output_path = Path(output_path)

    now = datetime.now().strftime("%Y/%m/%d %H:%M")

    # 掃描子目錄，收集所有社團資料
    groups = []
    for subdir in sorted(base_dir.iterdir()):
        if subdir.is_dir() and _re.match(r"\d{2}_", subdir.name):
            json_path = subdir / "all_posts.json"
            if not json_path.exists():
                continue
            with open(json_path, "r", encoding="utf-8") as f:
                posts = json.load(f)
            if not posts:
                continue
            group_name = posts[0].get("group_name", subdir.name.split("_", 1)[1])
            group_url = posts[0].get("group_url", "")
            groups.append({
                "name": group_name,
                "url": group_url,
                "data_dir": subdir,
                "posts": posts,
            })

    # 也支援單一目錄（不含子目錄）
    if not groups and (base_dir / "all_posts.json").exists():
        with open(base_dir / "all_posts.json", "r", encoding="utf-8") as f:
            posts = json.load(f)
        if posts:
            group_name = posts[0].get("group_name", base_dir.name)
            group_url = posts[0].get("group_url", "")
            groups.append({
                "name": group_name,
                "url": group_url,
                "data_dir": base_dir,
                "posts": posts,
            })

    total_posts = sum(len(g["posts"]) for g in groups)

    # 建立導航列
    nav_pills = []
    for i, g in enumerate(groups):
        nav_pills.append(
            f'<a class="group-pill" href="#group-{i+1}">{escape(g["name"])} ({len(g["posts"])})</a>'
        )
    nav_html = "\n      ".join(nav_pills)

    # 建立各社團區塊
    sections_html = []
    global_index = 0
    for i, g in enumerate(groups):
        group_link = ""
        if g["url"]:
            group_link = f'<a href="{escape(g["url"])}" target="_blank">前往社團 ↗</a>'

        section_header = f'''<div class="group-section-header">
      <h2>{escape(g["name"])}</h2>
      <span class="group-meta">{len(g["posts"])} 篇貼文</span>
      {group_link}
    </div>'''

        cards = []
        for j, post in enumerate(g["posts"]):
            images = get_local_images(g["data_dir"], j)
            cards.append(build_unified_post_html(global_index, post, images, g["name"]))
            global_index += 1

        cards_html = "\n\n".join(cards)
        sections_html.append(
            f'<section class="group-section" id="group-{i+1}">\n    {section_header}\n{cards_html}\n  </section>'
        )

    all_sections = "\n\n".join(sections_html)
    full_css = CSS + UNIFIED_CSS_EXTRA
    full_js = JS + UNIFIED_JS_EXTRA

    html_content = f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FB 社團爬蟲報告</title>
<style>{full_css}</style>
</head>
<body>

<div class="header">
  <div class="header-inner">
    <h1>FB 社團爬蟲報告 <span class="timestamp">{now}</span></h1>
    <span class="post-count">{len(groups)} 個社團 · 共 {total_posts} 篇貼文</span>
  </div>
</div>

<div class="group-nav">
  <div class="group-nav-inner">
      {nav_html}
  </div>
</div>

<div class="container">

{all_sections}

</div>

<div class="lightbox" id="lightbox" onclick="closeLightbox()">
  <img id="lightbox-img" src="" alt="放大圖片">
</div>

<button class="back-top" id="backTop" onclick="window.scrollTo({{top:0,behavior:'smooth'}})">&#8593;</button>

<script>{full_js}</script>
</body>
</html>'''

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_path


def find_latest_output() -> Path | None:
    """在爬蟲專案目錄中找到最新的 output 資料夾"""
    scraper_dir = Path(__file__).resolve().parent.parent
    if not scraper_dir.exists():
        return None

    candidates = []
    for d in scraper_dir.iterdir():
        if d.is_dir() and d.name.startswith("output") and (d / "all_posts.json").exists():
            candidates.append(d)

    if not candidates:
        return None

    return max(candidates, key=lambda d: d.stat().st_mtime)


def main():
    if len(sys.argv) > 1:
        data_dir = Path(sys.argv[1])
    else:
        data_dir = find_latest_output()
        if not data_dir:
            print("找不到 output 資料夾，請指定路徑: python3 generate.py <data_dir>")
            sys.exit(1)
        print(f"自動選取最新資料夾: {data_dir}")

    if not (data_dir / "all_posts.json").exists():
        print(f"錯誤: {data_dir}/all_posts.json 不存在")
        sys.exit(1)

    output = generate_html(data_dir)
    posts = load_posts(data_dir)
    print(f"已生成 {output}")
    print(f"共 {len(posts)} 篇貼文")


if __name__ == "__main__":
    main()
