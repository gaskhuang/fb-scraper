"""
FastAPI 後端 — Facebook Group Scraper Web UI
啟動: uvicorn app.main:app --port 9558
"""

import asyncio
import json
import os
import queue
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 讓 scripts/ 可以被 import
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.fb_group_scraper import scrape_group, parse_within
from scripts.generate import generate_unified_html
from scripts.config_loader import load_config, save_config
from scripts.notify import notify_scrape_done, detect_chat_id

app = FastAPI(title="FB Group Scraper")

# 靜態檔案
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ──────────────────────────────────────────────
# 資料模型
# ──────────────────────────────────────────────

class GroupConfig(BaseModel):
    group_url: str
    top_n: int = 0
    min_likes: int = 0
    min_comments: int = 0
    min_shares: int = 0
    within: str = ""        # 如 "24h", "3d", "1w"


class BatchScrapeParams(BaseModel):
    groups: List[GroupConfig]
    max_rounds: int = 200
    auto_publish: bool = False   # 爬完自動推送到 GitHub Pages


# ──────────────────────────────────────────────
# Job 管理
# ──────────────────────────────────────────────

MAX_JOB_HOURS = 4  # 超過此時間視為卡住，強制標記失敗


class ScrapeJob:
    def __init__(self, job_id: str, params: BatchScrapeParams):
        self.job_id = job_id
        self.params = params
        self.status = "pending"
        self.log_queue: queue.Queue = queue.Queue()
        self.thread: threading.Thread | None = None
        self.stop_flag = threading.Event()
        self.started_at = datetime.now()
        self.base_output_dir = ""
        self.unified_html_path = ""
        self.report_url = ""
        self.results: list[dict] = []   # 每個社團的結果摘要

    def log(self, message: str):
        self.log_queue.put(message)

    def run(self):
        self.status = "running"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.base_output_dir = str(PROJECT_ROOT / f"output_{ts}")
        groups = self.params.groups
        total = len(groups)

        for idx, group in enumerate(groups, 1):
            if self.stop_flag.is_set():
                self.log(f"\n⛔ 已手動停止，跳過剩餘 {total - idx + 1} 個社團")
                break

            self.log(f"\n{'─'*40}")
            self.log(f"▶ [{idx}/{total}] 開始爬取: {group.group_url}")
            self.log(f"{'─'*40}")

            # 每個社團建立子資料夾
            safe_name = group.group_url.rstrip("/").split("/")[-1]
            output_dir = os.path.join(self.base_output_dir, f"{idx:02d}_{safe_name}")

            try:
                within_hours = parse_within(group.within) if group.within else None
                result = scrape_group(
                    group_url=group.group_url,
                    top_n=group.top_n,
                    min_likes=group.min_likes,
                    min_comments=group.min_comments,
                    min_shares=group.min_shares,
                    within_hours=within_hours,
                    max_rounds=self.params.max_rounds,
                    output_dir=output_dir,
                    log=self.log,
                    web_mode=True,
                    stop_flag=self.stop_flag,
                )
                count = len(result) if result else 0
                self.results.append({"url": group.group_url, "post_count": count, "output_dir": output_dir, "status": "completed"})
                self.log(f"✅ [{idx}/{total}] 完成，共 {count} 篇 → {output_dir}")
            except Exception as e:
                self.log(f"❌ [{idx}/{total}] 錯誤: {e}")
                self.results.append({"url": group.group_url, "post_count": 0, "output_dir": output_dir, "status": "failed"})

        # 所有社團爬完後，產生統一報告
        if self.results:
            try:
                html_path = generate_unified_html(self.base_output_dir)
                self.unified_html_path = str(html_path)
                self.log(f"\n🌐 統一報告已生成: {html_path}")
            except Exception as e:
                self.log(f"⚠️  統一報告產生失敗: {e}")

        # 自動推送到 GitHub Pages
        if self.unified_html_path and self.params.auto_publish:
            try:
                from scripts.publish_to_github import publish_report
                self.log("\n📤 正在推送到 GitHub Pages...")
                self.report_url = publish_report(self.unified_html_path, log=self.log)
            except Exception as e:
                self.log(f"⚠️  GitHub Pages 推送失敗: {e}")

        # Telegram 通知
        total_posts = sum(r["post_count"] for r in self.results)
        if total_posts > 0:
            try:
                notify_scrape_done(
                    group_count=len(self.results),
                    post_count=total_posts,
                    report_url=self.report_url,
                    log=self.log,
                )
            except Exception as e:
                self.log(f"⚠️  Telegram 通知失敗: {e}")

        self.status = "completed" if not self.stop_flag.is_set() else "stopped"
        self.log_queue.put(None)  # sentinel


# 全域 job 列表
_jobs: dict[str, ScrapeJob] = {}
_active_job_id: str | None = None


def _get_active_job() -> Optional[ScrapeJob]:
    """回傳真正還在執行中的 job；若 thread 已死或超時則自動標記失敗。"""
    global _active_job_id
    if not _active_job_id:
        return None
    job = _jobs.get(_active_job_id)
    if not job or job.status != "running":
        return None
    # thread 已結束但沒更新 status → 標記失敗
    if job.thread and not job.thread.is_alive():
        job.status = "failed"
        return None
    # 超過最大時限 → 視為卡住，強制標記失敗並設 stop_flag
    elapsed_hours = (datetime.now() - job.started_at).total_seconds() / 3600
    if elapsed_hours > MAX_JOB_HOURS:
        job.status = "failed"
        job.stop_flag.set()
        return None
    return job


# ──────────────────────────────────────────────
# API 路由
# ──────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/api/scrape")
async def start_scrape(params: BatchScrapeParams):
    global _active_job_id

    if _get_active_job():
        raise HTTPException(409, "已有正在執行的爬蟲任務，請等待完成或停止後再試。")

    if not params.groups:
        raise HTTPException(400, "請至少新增一個社團。")

    job_id = uuid.uuid4().hex[:12]
    job = ScrapeJob(job_id, params)
    _jobs[job_id] = job
    _active_job_id = job_id

    job.thread = threading.Thread(target=job.run, daemon=True)
    job.thread.start()

    return {"job_id": job_id, "output_dir": job.base_output_dir}


@app.post("/api/scrape/{job_id}/stop")
async def stop_scrape(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.stop_flag.set()
    return {"status": "stopping"}


@app.get("/api/scrape/{job_id}/logs")
async def stream_logs(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    async def event_generator():
        try:
            while True:
                try:
                    msg = job.log_queue.get_nowait()
                    if msg is None:
                        total_posts = sum(r["post_count"] for r in job.results)
                        data = json.dumps({
                            "type": "done",
                            "status": job.status,
                            "post_count": total_posts,
                            "output_dir": job.base_output_dir,
                            "report_url": job.report_url,
                            "results": job.results,
                        })
                        yield f"data: {data}\n\n"
                        break
                    data = json.dumps({"type": "log", "message": msg})
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    await asyncio.sleep(0.3)
                    if job.status in ("completed", "stopped", "failed") and job.log_queue.empty():
                        total_posts = sum(r["post_count"] for r in job.results)
                        data = json.dumps({
                            "type": "done",
                            "status": job.status,
                            "post_count": total_posts,
                            "output_dir": job.base_output_dir,
                            "report_url": job.report_url,
                            "results": job.results,
                        })
                        yield f"data: {data}\n\n"
                        break
        except GeneratorExit:
            # 瀏覽器關閉 / 頁面離開 → 通知爬蟲停止
            if job.status == "running":
                job.stop_flag.set()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/scrape/{job_id}/publish")
async def publish_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if not job.unified_html_path:
        raise HTTPException(400, "統一報告尚未生成")

    try:
        from scripts.publish_to_github import publish_report
        url = publish_report(job.unified_html_path)
        job.report_url = url
        return {"report_url": url}
    except Exception as e:
        raise HTTPException(500, f"推送失敗: {e}")


@app.get("/api/scrape/{job_id}/result")
async def get_result(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {"results": job.results, "status": job.status}


@app.get("/api/jobs")
async def list_jobs():
    return [
        {
            "job_id": j.job_id,
            "status": j.status,
            "group_count": len(j.params.groups),
            "output_dir": j.base_output_dir,
            "results": j.results,
        }
        for j in _jobs.values()
    ]


# ──────────────────────────────────────────────
# 排程系統（多排程架構）
# ──────────────────────────────────────────────

class ScheduleConfig(BaseModel):
    schedule_id: str = ""          # 空字串 = 新建排程
    name: str = ""                 # 排程名稱（選填）
    groups: List[GroupConfig]
    max_rounds: int = 20
    auto_publish: bool = True
    hours: List[int]               # 執行小時 (0-23)，可多選
    weekdays: List[int]            # 執行星期 (0=週一 … 6=週日)，空白=每天


SCHEDULE_FILE = PROJECT_ROOT / "schedule_config.json"


class _ScheduleEntry:
    """單一排程實例"""
    def __init__(self, schedule_id: str, config: ScheduleConfig):
        self.schedule_id = schedule_id
        self.config = config
        self.enabled = True
        self.last_run: Optional[datetime] = None
        self.last_run_ok: Optional[bool] = None
        self.next_run: Optional[datetime] = None
        self._lock = threading.Lock()
        self._calc_next()

    def _calc_next(self):
        cfg = self.config
        now = datetime.now()
        candidate = now.replace(second=0, microsecond=0)
        for _ in range(8 * 24 * 60):
            candidate += timedelta(minutes=1)
            wd = candidate.weekday()
            hr = candidate.hour
            weekdays = cfg.weekdays if cfg.weekdays else list(range(7))
            if wd in weekdays and hr in cfg.hours and candidate.minute == 0:
                self.next_run = candidate
                return
        self.next_run = None

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "schedule_id": self.schedule_id,
                "name": self.config.name or "",
                "enabled": self.enabled,
                "groups": [g.model_dump() for g in self.config.groups],
                "hours": self.config.hours,
                "weekdays": self.config.weekdays,
                "max_rounds": self.config.max_rounds,
                "auto_publish": self.config.auto_publish,
                "last_run": self.last_run.strftime("%Y/%m/%d %H:%M") if self.last_run else None,
                "last_run_ok": self.last_run_ok,
                "next_run": self.next_run.strftime("%Y/%m/%d %H:%M") if self.next_run else None,
            }


class _SchedulerManager:
    """管理多個排程"""
    def __init__(self):
        self._schedules: dict[str, _ScheduleEntry] = {}
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def _ensure_loop(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def add_or_update(self, config: ScheduleConfig) -> _ScheduleEntry:
        sid = config.schedule_id or uuid.uuid4().hex[:12]
        config.schedule_id = sid
        with self._lock:
            if sid in self._schedules:
                entry = self._schedules[sid]
                entry.config = config
                entry.enabled = True
                entry._calc_next()
            else:
                entry = _ScheduleEntry(sid, config)
                self._schedules[sid] = entry
            self._save_to_disk()
        self._ensure_loop()
        return entry

    def delete(self, schedule_id: str) -> bool:
        with self._lock:
            if schedule_id not in self._schedules:
                return False
            self._schedules.pop(schedule_id)
            self._save_to_disk()
            return True

    def disable(self, schedule_id: str):
        with self._lock:
            entry = self._schedules.get(schedule_id)
            if entry:
                entry.enabled = False
                entry.next_run = None
            self._save_to_disk()

    def enable(self, schedule_id: str):
        with self._lock:
            entry = self._schedules.get(schedule_id)
            if entry:
                entry.enabled = True
                entry._calc_next()
            self._save_to_disk()
        self._ensure_loop()

    def get(self, schedule_id: str) -> Optional[_ScheduleEntry]:
        return self._schedules.get(schedule_id)

    def list_all(self) -> list[dict]:
        with self._lock:
            return [e.to_dict() for e in self._schedules.values()]

    def _save_to_disk(self):
        data = []
        for entry in self._schedules.values():
            d = entry.to_dict()
            d["config"] = entry.config.model_dump()
            data.append(d)
        with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def restore(self):
        if not SCHEDULE_FILE.exists():
            return
        try:
            with open(SCHEDULE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            # 支援舊格式（單一排程 dict）
            if isinstance(data, dict):
                if data.get("enabled") and data.get("config"):
                    config = ScheduleConfig(**data["config"])
                    config.schedule_id = uuid.uuid4().hex[:12]
                    entry = _ScheduleEntry(config.schedule_id, config)
                    self._schedules[config.schedule_id] = entry
            elif isinstance(data, list):
                for item in data:
                    cfg_data = item.get("config", item)
                    config = ScheduleConfig(**cfg_data)
                    sid = item.get("schedule_id") or config.schedule_id or uuid.uuid4().hex[:12]
                    config.schedule_id = sid
                    entry = _ScheduleEntry(sid, config)
                    entry.enabled = item.get("enabled", True)
                    if not entry.enabled:
                        entry.next_run = None
                    last_run_str = item.get("last_run")
                    if last_run_str:
                        try:
                            entry.last_run = datetime.strptime(last_run_str, "%Y/%m/%d %H:%M")
                        except Exception:
                            pass
                    entry.last_run_ok = item.get("last_run_ok")
                    self._schedules[sid] = entry
            if self._schedules:
                self._ensure_loop()
        except Exception:
            pass

    def _loop(self):
        while True:
            time.sleep(30)
            now = datetime.now()
            to_run = []
            with self._lock:
                for entry in self._schedules.values():
                    if entry.enabled and entry.next_run and now >= entry.next_run:
                        entry.last_run = now
                        entry._calc_next()
                        to_run.append(entry)
                if to_run:
                    self._save_to_disk()
            for entry in to_run:
                threading.Thread(target=self._run_job, args=(entry,), daemon=True).start()

    def _run_job(self, entry: _ScheduleEntry):
        if _get_active_job():
            return
        params = BatchScrapeParams(
            groups=entry.config.groups,
            max_rounds=entry.config.max_rounds,
            auto_publish=entry.config.auto_publish,
        )
        job_id = uuid.uuid4().hex[:12]
        job = ScrapeJob(job_id, params)
        _jobs[job_id] = job
        _active_job_id = job_id
        job.thread = threading.Thread(target=job.run, daemon=True)
        job.thread.start()
        # 等任務結束，回寫 last_run_ok
        job.thread.join()
        with self._lock:
            entry.last_run_ok = job.status == "completed"
            self._save_to_disk()


_scheduler_mgr = _SchedulerManager()


@app.get("/scheduler")
async def scheduler_page():
    return FileResponse(str(STATIC_DIR / "scheduler.html"))


@app.get("/api/schedules")
async def list_schedules():
    return _scheduler_mgr.list_all()


@app.post("/api/schedules")
async def save_schedule(config: ScheduleConfig):
    if not config.groups:
        raise HTTPException(400, "請至少新增一個社團。")
    if not config.hours:
        raise HTTPException(400, "請至少選擇一個執行小時。")
    entry = _scheduler_mgr.add_or_update(config)
    return entry.to_dict()


@app.delete("/api/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    ok = _scheduler_mgr.delete(schedule_id)
    if not ok:
        raise HTTPException(404, detail=f"排程 {schedule_id} 不存在")
    return {"deleted": schedule_id, "ok": True}


@app.post("/api/schedules/{schedule_id}/disable")
async def disable_schedule(schedule_id: str):
    _scheduler_mgr.disable(schedule_id)
    entry = _scheduler_mgr.get(schedule_id)
    return entry.to_dict() if entry else {"schedule_id": schedule_id, "enabled": False}


@app.post("/api/schedules/{schedule_id}/enable")
async def enable_schedule(schedule_id: str):
    _scheduler_mgr.enable(schedule_id)
    entry = _scheduler_mgr.get(schedule_id)
    return entry.to_dict() if entry else {"schedule_id": schedule_id, "enabled": True}


@app.post("/api/schedules/{schedule_id}/run-now")
async def run_schedule_now(schedule_id: str):
    """立即執行指定排程"""
    entry = _scheduler_mgr.get(schedule_id)
    if not entry:
        raise HTTPException(404, "排程不存在")
    global _active_job_id
    if _get_active_job():
        raise HTTPException(409, "已有正在執行的爬蟲任務")
    params = BatchScrapeParams(
        groups=entry.config.groups,
        max_rounds=entry.config.max_rounds,
        auto_publish=entry.config.auto_publish,
    )
    job_id = uuid.uuid4().hex[:12]
    job = ScrapeJob(job_id, params)
    _jobs[job_id] = job
    _active_job_id = job_id
    job.thread = threading.Thread(target=job.run, daemon=True)
    job.thread.start()
    return {"job_id": job_id, "schedule_id": schedule_id}


# 舊版相容（for 任何還在使用 /api/schedule 的地方）
@app.get("/api/schedule")
async def get_schedule_compat():
    schedules = _scheduler_mgr.list_all()
    return schedules[0] if schedules else {"enabled": False, "groups": []}


# ──────────────────────────────────────────────
# 設定 API
# ──────────────────────────────────────────────

class ConfigUpdate(BaseModel):
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    github_repo: str = ""
    github_token: str = ""
    cdp_port: int = 9223
    web_port: int = 9558


@app.get("/settings")
async def settings_page():
    return FileResponse(str(STATIC_DIR / "settings.html"))


@app.get("/api/config")
async def get_config():
    cfg = load_config()
    # 遮罩 token，只顯示後 4 碼
    masked = dict(cfg)
    for key in ("telegram_bot_token", "github_token"):
        val = masked.get(key, "")
        if val and len(val) > 4:
            masked[key] = "•" * (len(val) - 4) + val[-4:]
    return masked


@app.post("/api/config")
async def update_config(data: ConfigUpdate):
    current = load_config()
    updates = data.model_dump()

    # 如果前端送回遮罩值，保留原本的 token
    for key in ("telegram_bot_token", "github_token"):
        if updates[key].startswith("•"):
            updates[key] = current.get(key, "")

    save_config(updates)
    result = {"status": "ok", "config": updates}

    # 自動偵測 GitHub 用戶名和建立 repo
    if updates["github_token"] and not updates["github_repo"]:
        try:
            detected = await _detect_github_repo(updates["github_token"])
            if detected:
                updates["github_repo"] = detected
                save_config(updates)
                result["github_repo_detected"] = detected
        except Exception as e:
            result["github_error"] = str(e)

    # 自動偵測 Telegram chat_id
    if updates["telegram_bot_token"] and not updates["telegram_chat_id"]:
        try:
            chat_id = detect_chat_id(updates["telegram_bot_token"])
            if chat_id:
                updates["telegram_chat_id"] = chat_id
                save_config(updates)
                result["telegram_chat_id_detected"] = chat_id
            else:
                result["telegram_warning"] = "找不到 chat_id，請先對 bot 發送 /start"
        except Exception as e:
            result["telegram_error"] = str(e)

    # 遮罩回傳
    for key in ("telegram_bot_token", "github_token"):
        val = updates.get(key, "")
        if val and len(val) > 4:
            result["config"][key] = "•" * (len(val) - 4) + val[-4:]

    return result


async def _detect_github_repo(token: str) -> str:
    """用 GitHub token 偵測用戶名，回傳 {username}/fb-reports"""
    import urllib.request
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        username = data["login"]

    repo = f"{username}/fb-reports"

    # 檢查 repo 是否存在，不存在就建立
    import os
    os.environ["GH_TOKEN"] = token
    import subprocess
    check = subprocess.run(
        ["gh", "repo", "view", repo],
        capture_output=True, text=True,
    )
    if check.returncode != 0:
        subprocess.run(
            ["gh", "repo", "create", repo, "--public", "--description", "FB 社團爬蟲報告"],
            check=True, capture_output=True, text=True,
        )
        # 啟用 GitHub Pages
        from scripts.publish_to_github import ensure_pages_enabled
        ensure_pages_enabled(repo)

    return repo


@app.post("/api/config/test-telegram")
async def test_telegram():
    """發送測試訊息到 Telegram"""
    from scripts.notify import send_telegram
    cfg = load_config()
    if not cfg.get("telegram_bot_token") or not cfg.get("telegram_chat_id"):
        return {"ok": False, "error": "Telegram 未設定（缺少 Bot Token 或 Chat ID）"}
    try:
        ok = send_telegram("✅ FB 社團爬蟲 Telegram 通知測試成功！")
        return {"ok": ok}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ──────────────────────────────────────────────
# 啟動事件
# ──────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    """啟動時恢復排程"""
    _scheduler_mgr.restore()
