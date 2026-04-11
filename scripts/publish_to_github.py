#!/usr/bin/env python3
"""將統一 HTML 報告推送到 GitHub Pages。

每次產生帶時間戳的 report_YYYYMMDD_HHMM.html，
並自動更新 index.html（歷史報告清單）。

用法:
    python3 publish_to_github.py <html_path> [--repo owner/repo]
"""

import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


try:
    from scripts.config_loader import load_config
except ImportError:
    from config_loader import load_config


def _get_repo() -> str:
    """從 config.json 讀取 github_repo"""
    cfg = load_config()
    return cfg.get("github_repo", "")


def _setup_gh_token():
    """設定 GH_TOKEN 環境變數讓 gh CLI 認證"""
    cfg = load_config()
    token = cfg.get("github_token", "")
    if token:
        os.environ["GH_TOKEN"] = token


def publish_report(
    html_path: str | Path,
    repo: str = "",
    log=print,
) -> str:
    """推送 HTML 報告到 GitHub Pages。

    Args:
        html_path: 統一報告的 HTML 檔案路徑
        repo: GitHub repo (owner/repo 格式)
        log: 日誌函式

    Returns:
        報告的 GitHub Pages URL
    """
    html_path = Path(html_path)
    if not html_path.exists():
        raise FileNotFoundError(f"找不到 HTML 檔案: {html_path}")

    # 從 config 讀取 repo 和設定 token
    if not repo:
        repo = _get_repo()
    if not repo:
        raise ValueError("未設定 github_repo，請在設定頁面填入 GitHub Token")
    _setup_gh_token()

    owner, repo_name = repo.split("/")
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    report_filename = f"report_{ts}.html"
    pages_url = f"https://{owner}.github.io/{repo_name}"
    report_url = f"{pages_url}/{report_filename}"

    with tempfile.TemporaryDirectory() as tmpdir:
        clone_dir = Path(tmpdir) / repo_name

        # 嘗試 clone；如果 repo 不存在就建立
        log("📦 正在同步 GitHub 倉庫...")
        result = subprocess.run(
            ["gh", "repo", "clone", repo, str(clone_dir), "--", "--depth", "1"],
            capture_output=True, text=True,
        )

        if result.returncode != 0:
            log(f"⚠️  Clone 失敗，嘗試建立新倉庫 {repo}...")
            subprocess.run(
                ["gh", "repo", "create", repo, "--public", "--clone", "--description", "FB 社團爬蟲報告"],
                cwd=tmpdir, check=True, capture_output=True, text=True,
            )
            clone_dir = Path(tmpdir) / repo_name
            if not clone_dir.exists():
                # gh repo create --clone 有時會用不同目錄名
                for d in Path(tmpdir).iterdir():
                    if d.is_dir() and d.name != ".git":
                        clone_dir = d
                        break

        # 複製報告
        log(f"📄 上傳報告: {report_filename}")
        shutil.copy2(html_path, clone_dir / report_filename)

        # 掃描所有 report_*.html，產生 index.html
        reports = sorted(
            [f.name for f in clone_dir.glob("report_*.html")],
            reverse=True,
        )
        log(f"📋 更新報告列表 ({len(reports)} 份報告)...")
        index_html = _build_index_html(reports, owner, repo_name)
        (clone_dir / "index.html").write_text(index_html, encoding="utf-8")

        # Git push
        env = {**os.environ, "GIT_AUTHOR_NAME": "fb-scraper", "GIT_COMMITTER_NAME": "fb-scraper",
               "GIT_AUTHOR_EMAIL": "noreply@github.com", "GIT_COMMITTER_EMAIL": "noreply@github.com"}
        subprocess.run(["git", "add", "-A"], cwd=clone_dir, check=True, capture_output=True, env=env)

        # 檢查是否有變更
        diff_result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=clone_dir, capture_output=True,
        )
        if diff_result.returncode == 0:
            log("ℹ️  無變更，跳過推送")
            return report_url

        subprocess.run(
            ["git", "commit", "-m", f"Add report {report_filename}"],
            cwd=clone_dir, check=True, capture_output=True, env=env,
        )
        log("🚀 推送到 GitHub...")
        subprocess.run(
            ["git", "push"],
            cwd=clone_dir, check=True, capture_output=True, env=env,
        )

    log(f"✅ 報告已發布: {report_url}")
    return report_url


def _build_index_html(report_files: list[str], owner: str, repo_name: str) -> str:
    """產生歷史報告列表的 index.html"""
    pages_url = f"https://{owner}.github.io/{repo_name}"

    rows = []
    for f in report_files:
        # report_20260410_1503.html → 2026/04/10 15:03
        m = re.match(r"report_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})\.html", f)
        if m:
            display_time = f"{m.group(1)}/{m.group(2)}/{m.group(3)} {m.group(4)}:{m.group(5)}"
        else:
            display_time = f
        rows.append(
            f'<tr><td>{display_time}</td><td><a href="{f}">{f}</a></td>'
            f'<td><a href="{f}" class="btn">開啟報告</a></td></tr>'
        )

    table_rows = "\n".join(rows) if rows else '<tr><td colspan="3" style="text-align:center;color:#999">尚無報告</td></tr>'

    return f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FB 社團爬蟲報告列表</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f0f2f5; color: #1c1e21; line-height: 1.6;
    padding: 40px 20px;
  }}
  .container {{ max-width: 700px; margin: 0 auto; }}
  h1 {{
    font-size: 24px; font-weight: 700; color: #1877f2;
    margin-bottom: 8px;
  }}
  .subtitle {{ font-size: 14px; color: #65676b; margin-bottom: 24px; }}
  table {{
    width: 100%; border-collapse: collapse;
    background: #fff; border-radius: 12px; overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }}
  th {{
    text-align: left; padding: 12px 16px;
    background: #f8f9fa; color: #65676b; font-size: 13px; font-weight: 600;
    border-bottom: 1px solid #e4e6eb;
  }}
  td {{
    padding: 12px 16px; border-bottom: 1px solid #f0f2f5;
    font-size: 14px;
  }}
  tr:last-child td {{ border-bottom: none; }}
  a {{ color: #1877f2; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .btn {{
    display: inline-block; padding: 6px 16px;
    background: #1877f2; color: #fff; border-radius: 6px;
    font-size: 13px; font-weight: 500; text-decoration: none;
  }}
  .btn:hover {{ background: #166fe5; text-decoration: none; }}
</style>
</head>
<body>
<div class="container">
  <h1>FB 社團爬蟲報告列表</h1>
  <p class="subtitle">共 {len(report_files)} 份報告 · {pages_url}</p>
  <table>
    <thead>
      <tr><th>時間</th><th>檔案</th><th></th></tr>
    </thead>
    <tbody>
      {table_rows}
    </tbody>
  </table>
</div>
</body>
</html>'''


def ensure_pages_enabled(repo: str):
    """確認 GitHub Pages 已啟用"""
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/pages"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"正在啟用 GitHub Pages for {repo}...")
        subprocess.run(
            ["gh", "api", f"repos/{repo}/pages", "-X", "POST",
             "-f", "source[branch]=main", "-f", "source[path]=/"],
            check=True, capture_output=True, text=True,
        )
        print("GitHub Pages 已啟用")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 publish_to_github.py <html_path> [--repo owner/repo]")
        sys.exit(1)

    html_file = sys.argv[1]
    repo = ""
    if "--repo" in sys.argv:
        idx = sys.argv.index("--repo")
        repo = sys.argv[idx + 1]

    if not repo:
        repo = _get_repo()
    if not repo:
        print("錯誤: 未設定 github_repo，請先在 config.json 或設定頁面填入")
        sys.exit(1)

    _setup_gh_token()
    ensure_pages_enabled(repo)
    url = publish_report(html_file, repo=repo)
    print(f"\n報告 URL: {url}")
