import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from rich.console import Console
from rich.panel import Panel

from src.engine.resume_parser import ResumeManager
from src.engine.matcher import JobMatcher
from src.engine.screener import ScreeningEngine
from src.storage.db import JobDatabase
from src.reporter.report_generator import ReportGenerator
from src.scrapers.linkedin_scraper import LinkedInScraper
from src.applier.browser_manager import BrowserManager
from src.utils.logger import get_logger

logger = get_logger("AutonomousJobAgent")
console = Console()

class AutonomousJobAgent:
    """
    Autonomous Job Hunting & Application Agent for Shubham Kulkarni.
    Runs continuous or scheduled cycles to:
    1. Search LinkedIn & Naukri for fresh (<24h) postings
    2. Score & prioritize Pune and Remote opportunities first
    3. Auto-apply to top matching roles respecting strict 50/day platform limits
    4. Maintain simple 3-section records in APPLICATIONS.md
    """

    def __init__(self, settings: Dict[str, Any], db: Optional[JobDatabase] = None, base_dir: Optional[Path] = None):
        self.settings = settings
        self.db = db or JobDatabase()
        self.base_dir = Path(base_dir) if base_dir else None
        self.resume_mgr = ResumeManager()
        self.matcher = JobMatcher(self.resume_mgr.get_profile())
        self.screener = ScreeningEngine(self.resume_mgr.get_profile(), settings)

        limits = settings.get("application_limits", {})
        self.daily_max_linkedin = limits.get("daily_max_linkedin", 50)
        self.daily_max_naukri = limits.get("daily_max_naukri", 50)

        safety = settings.get("safety_guards", {})
        self.max_runtime_minutes = float(safety.get("max_runtime_minutes", 30.0))
        self.daemon_interval_hours = float(safety.get("daemon_interval_hours", 10.0))

        from src.notifier.telegram_notifier import TelegramNotifier
        self.notifier = TelegramNotifier(settings)

    def run_single_cycle(
        self,
        min_score: float = 75.0,
        search_limit: int = 10,
        auto_apply: bool = True,
        max_runtime_minutes: Optional[float] = None,
        easy_apply_only: Optional[bool] = None,
        trigger_type: Optional[str] = None
    ) -> Dict[str, Any]:
        cycle_start = datetime.now()
        start_ts = time.time()
        start_str = cycle_start.strftime("%Y-%m-%d %H:%M:%S")
        runtime_limit = float(max_runtime_minutes if max_runtime_minutes is not None else self.max_runtime_minutes)
        console.print(Panel(
            f"[bold cyan]🤖 Autonomous Agent Cycle Started at {start_str}[/bold cyan]\n"
            f"[dim]Precautionary Cycle Timeout: {runtime_limit:.1f} minutes maximum[/dim]",
            border_style="cyan"
        ))

        timed_out = False

        def is_timed_out() -> bool:
            return (time.time() - start_ts) >= (runtime_limit * 60.0)

        # Determine active mode & trigger type
        if easy_apply_only is not None:
            is_easy = easy_apply_only
        else:
            is_easy = self.settings.get("search_filters", {}).get("linkedin", {}).get("easy_apply_only", True)
        effective_trigger_type = trigger_type or ("Easy Apply" if is_easy else "External Jobs")

        # Step 1: Check Current Quota Usage
        li_today = self.db.get_daily_applied_count("linkedin")
        nk_today = self.db.get_daily_applied_count("naukri")
        console.print(f"📊 [bold]Daily Applied Quotas:[/bold] LinkedIn: {li_today}/{self.daily_max_linkedin} | Naukri: {nk_today}/{self.daily_max_naukri}")

        # Step 2: Search LinkedIn (with configured multi-filters)
        total_discovered = 0
        search_filters = self.settings.get("search_filters", {})
        li_filters = dict(search_filters.get("linkedin", {}))
        if "freshness_hours" not in li_filters and "freshness_hours" in search_filters:
            li_filters["freshness_hours"] = search_filters["freshness_hours"]
        if easy_apply_only is not None:
            li_filters["easy_apply_only"] = easy_apply_only
        li_scraper = LinkedInScraper(default_filters=li_filters)

        li_queries = self.settings.get("search_queries", {}).get("linkedin", [
            "Senior SDET C#", "Senior SDET Playwright", "Senior QA Automation C#", "SDET C# Selenium"
        ])[:4]
        freshness_label = f"<{li_filters.get('freshness_hours', 24)}h"
        console.print(f"\n[bold yellow]🔍 Step 1/3: Searching LinkedIn across {len(li_queries)} queries ({freshness_label}, Easy Apply)...[/bold yellow]")
        for q in li_queries:
            if is_timed_out():
                console.print(f"[bold yellow]⏱️ Precautionary timeout reached ({runtime_limit:.1f}m). Halting LinkedIn search.[/bold yellow]")
                timed_out = True
                break
            jobs = li_scraper.search_jobs(q, location="India", max_results=search_limit)
            unseen = []
            for job in jobs:
                temp_id = job.get("job_id") or self.db.generate_job_id(job["platform"], job["url"], job["title"], job["company"])
                job["job_id"] = temp_id
                if not self.db.is_job_seen(temp_id):
                    unseen.append(job)

            if unseen:
                li_scraper.fetch_descriptions_concurrently(unseen)
                for job in unseen:
                    if is_timed_out():
                        console.print(f"[bold yellow]⏱️ Precautionary timeout reached ({runtime_limit:.1f}m). Halting LinkedIn analysis.[/bold yellow]")
                        timed_out = True
                        break
                    if not job.get("description"):
                        continue
                    res = self.matcher.evaluate(job)
                    job["match_score"] = res["total_score_pct"]
                    job["priority_tier"] = res["priority"]
                    job["skip_reason"] = res["summary_reason"]
                    job["status"] = "discovered"
                    self.db.upsert_job(job)
                    total_discovered += 1

        # Step 3: Search Naukri (with configured multi-filters)
        if not timed_out and not is_timed_out():
            nk_queries = self.settings.get("search_queries", {}).get("naukri", [
                "Senior SDET C#", "Senior SDET", "Senior Automation Engineer C#", "SDET C#"
            ])[:3]
            nk_filters = dict(search_filters.get("naukri", {}))
            console.print(f"\n[bold yellow]🔍 Step 2/3: Searching Naukri across {len(nk_queries)} queries (postDate={nk_filters.get('post_date_days', 1)})...[/bold yellow]")
            bm_search = None
            try:
                from src.scrapers.naukri_scraper import NaukriScraper
                bm_search = BrowserManager(headless=False)
                nk_scraper = NaukriScraper(browser_manager=bm_search, default_filters=nk_filters)
                for nq in nk_queries:
                    if is_timed_out():
                        console.print(f"[bold yellow]⏱️ Precautionary timeout reached ({runtime_limit:.1f}m). Halting Naukri search.[/bold yellow]")
                        timed_out = True
                        break
                    n_jobs = nk_scraper.search_jobs(nq, experience_years=8, max_results=search_limit)
                    for job in n_jobs:
                        temp_id = job.get("job_id") or self.db.generate_job_id(job["platform"], job["url"], job["title"], job["company"])
                        job["job_id"] = temp_id
                        if not self.db.is_job_seen(temp_id):
                            res = self.matcher.evaluate(job)
                            job["match_score"] = res["total_score_pct"]
                            job["priority_tier"] = res["priority"]
                            job["skip_reason"] = res["summary_reason"]
                            job["status"] = "discovered"
                            self.db.upsert_job(job)
                            total_discovered += 1
            except Exception as e:
                logger.error(f"Error during autonomous Naukri search: {e}")
            finally:
                if bm_search:
                    bm_search.close()
        elif is_timed_out():
            console.print(f"[bold yellow]⏱️ Precautionary timeout reached ({runtime_limit:.1f}m). Skipping Step 2/3 Naukri search.[/bold yellow]")
            timed_out = True

        console.print(f"[bold green]✓ Discovered {total_discovered} new opportunities in this cycle.[/bold green]")

        # Step 4: Autonomous Applications (Prioritizing Pune & Remote first)
        applied_in_cycle = 0
        applied_in_this_run = []
        if auto_apply:
            if is_timed_out():
                console.print(f"\n[bold yellow]⏱️ Precautionary timeout reached ({runtime_limit:.1f}m). Skipping auto-apply phase.[/bold yellow]")
                timed_out = True
            else:
                console.print(f"\n[bold yellow]🚀 Step 3/3: Auto-Applying to Top Matches (Score >= {min_score}%, 📍 Pune & 🏡 Remote prioritized)...[/bold yellow]")
                all_jobs = self.db.get_all_jobs()
                candidates = [
                    j for j in all_jobs 
                    if j.get("match_score", 0) >= min_score 
                    and j.get("status") == "discovered"
                    and (not is_easy or j.get("is_easy_apply", True) is not False)
                ]

                # Priority Sort: 1) Pune & Remote first, 2) Match score descending
                def _is_pune_or_remote(j):
                    loc_txt = f"{j.get('location', '')} {j.get('title', '')}".lower()
                    return any(p in loc_txt for p in ["pune", "remote", "work from home", "wfh"])

                candidates.sort(
                    key=lambda x: (
                        1 if _is_pune_or_remote(x) else 0,
                        x.get("match_score", 0),
                        -x.get("hours_ago", 999.0)
                    ),
                    reverse=True
                )

                if candidates:
                    from src.applier.linkedin_applier import LinkedInApplier
                    from src.applier.naukri_applier import NaukriApplier
                    li_applier = LinkedInApplier(self.screener, review_mode=False)
                    nk_applier = NaukriApplier(self.screener, review_mode=False)

                    bm_apply = BrowserManager(headless=False)
                    try:
                        page = bm_apply.new_page()

                        for job in candidates:
                            if is_timed_out():
                                console.print(f"\n[bold yellow]⏱️ Precautionary timeout reached ({runtime_limit:.1f}m). Halting applications cleanly.[/bold yellow]")
                                timed_out = True
                                break

                            platform = job.get("platform", "").lower()
                            canonical_key = job.get("canonical_key") or self.db.generate_canonical_key(
                                job.get("company", ""), job.get("title", ""), job.get("location", "")
                            )
                            prior_applied = self.db.get_canonical_applied_job(canonical_key)
                            if prior_applied:
                                prior_plat = prior_applied.get("platform", "other platform").capitalize()
                                msg = f"Already applied on {prior_plat} ({prior_applied.get('company')} - {prior_applied.get('title')})"
                                self.db.mark_skipped(job["job_id"], reason=msg)
                                console.print(f"  • [yellow]Skipping duplicate across platforms: {msg}[/yellow]")
                                continue

                            current_today = self.db.get_daily_applied_count(platform)
                            platform_limit = self.daily_max_linkedin if platform == "linkedin" else self.daily_max_naukri

                            if current_today >= platform_limit:
                                console.print(f"  • [yellow]{platform.upper()} daily cap reached ({current_today}/{platform_limit}). Skipping {job['company']}.[/yellow]")
                                continue

                            console.print(f"  • Applying to [bold white]{job['company']}[/bold white] - {job['title']} ({job['match_score']}%) [{job.get('location', '')}] on [magenta]{platform.upper()}[/magenta]")
                            if platform == "linkedin":
                                success, msg = li_applier.apply(page, job)
                            elif platform == "naukri":
                                success, msg = nk_applier.apply(page, job)
                            else:
                                success, msg = False, "Unknown platform"

                            if success:
                                self.db.mark_applied(job["job_id"], status_msg="applied")
                                applied_in_cycle += 1
                                applied_in_this_run.append({
                                    "time": datetime.now().strftime("%I:%M %p"),
                                    "platform": platform,
                                    "company": job.get("company", ""),
                                    "title": job.get("title", ""),
                                    "location": job.get("location", ""),
                                    "match_score": job.get("match_score", 0),
                                    "outcome": "✅ Applied Successfully",
                                    "url": job.get("url", "")
                                })
                                new_count = self.db.get_daily_applied_count(platform)
                                console.print(f"    [green]✓ {msg} ({platform.capitalize()} Today: {new_count}/{platform_limit})[/green]")
                            else:
                                if "external" in msg.lower():
                                    self.db.mark_applied(job["job_id"], status_msg="queued_external")
                                    console.print(f"    [blue]ℹ {msg} (Queued in APPLICATIONS.md)[/blue]")
                                else:
                                    is_browser_closed = any(err in msg.lower() for err in ["closed", "target page", "context destroyed"])
                                    if is_browser_closed:
                                        console.print(f"    [bold red]⚠️ Browser/Page was closed unexpectedly: {msg}. Halting apply loop cleanly.[/bold red]")
                                        break
                                    self.db.mark_skipped(job["job_id"], reason=msg)
                                    console.print(f"    [dim]{msg}[/dim]")
                    finally:
                        bm_apply.close()

        # Step 5: Update Markdown & CSV Records & Save Run Report
        reporter = ReportGenerator(self.db.get_all_jobs(), self.db.get_summary_stats())
        elapsed_min = (time.time() - start_ts) / 60.0
        run_meta = {
            "mode": "auto",
            "trigger_type": effective_trigger_type,
            "timestamp_str": cycle_start.strftime('%A, %d %b %Y, %I:%M %p'),
            "runtime_minutes": elapsed_min,
            "timeout_minutes": runtime_limit,
            "timed_out": timed_out,
            "discovered": total_discovered,
            "li_today": self.db.get_daily_applied_count("linkedin"),
            "nk_today": self.db.get_daily_applied_count("naukri")
        }
        run_report_path = reporter.save_run_report(run_meta, applied_in_this_run, base_dir=self.base_dir)
        md_path, csv_path = reporter.save_all_records(base_dir=self.base_dir)

        # Telegram Notification
        if self.notifier.is_configured():
            def _is_pune_or_remote(j):
                loc_txt = f"{j.get('location', '')} {j.get('title', '')}".lower()
                return any(p in loc_txt for p in ["pune", "remote", "work from home", "wfh"])

            if is_easy:
                # Strictly Easy Apply only: only discovered direct jobs, zero external jobs
                top_todo = [
                    j for j in self.db.get_all_jobs()
                    if j.get("status") == "discovered"
                    and j.get("is_easy_apply", True) is not False
                    and j.get("match_score", 0) >= 70.0
                ]
                top_todo.sort(key=lambda x: (1 if _is_pune_or_remote(x) else 0, x.get("match_score", 0)), reverse=True)
                ext_jobs_to_send = None
                send_ext = False
            else:
                top_todo = [
                    j for j in self.db.get_all_jobs()
                    if j.get("status") in ["discovered", "queued_external"]
                    and j.get("match_score", 0) >= 70.0
                ]
                top_todo.sort(key=lambda x: (1 if _is_pune_or_remote(x) else 0, x.get("match_score", 0)), reverse=True)
                external_pune_remote = [
                    j for j in self.db.get_all_jobs()
                    if j.get("status") == "queued_external"
                    and j.get("match_score", 0) >= 70.0
                    and _is_pune_or_remote(j)
                ]
                external_pune_remote.sort(key=lambda x: x.get("match_score", 0), reverse=True)
                ext_jobs_to_send = external_pune_remote[:6]
                send_ext = True

            sent, tg_msg = self.notifier.send_run_summary(
                run_meta,
                applied_in_this_run,
                top_todo[:8],
                external_jobs=ext_jobs_to_send,
                send_external_template=send_ext
            )
            if sent:
                console.print(f"📱 [bold green]Telegram Alert:[/bold green] Posted trigger-wise summary ({effective_trigger_type}) to your channel.")
            else:
                console.print(f"📱 [yellow]Telegram Notice:[/yellow] {tg_msg}")

        status_msg = "[bold yellow]⚠️ Cycle Halted (Precautionary Timeout)[/bold yellow]" if timed_out else "[bold green]✓ Cycle Finished Successfully![/bold green]"
        console.print(f"\n{status_msg} Runtime: [bold]{elapsed_min:.1f}m / {runtime_limit:.1f}m[/bold] | Applied: [bold]{applied_in_cycle}[/bold]")
        console.print(f"📄 [bold cyan]Detailed Run Report:[/bold cyan] [underline]{run_report_path}[/underline]")
        console.print(f"📊 [bold green]Master Tracker:[/bold green] [underline]{md_path.name}[/underline]\n")

        return {
            "discovered": total_discovered,
            "applied": applied_in_cycle,
            "linkedin_today": self.db.get_daily_applied_count("linkedin"),
            "naukri_today": self.db.get_daily_applied_count("naukri"),
            "timed_out": timed_out,
            "runtime_seconds": round(time.time() - start_ts, 2),
            "run_report": str(run_report_path)
        }

    def run_daemon(self, interval_hours: Optional[float] = None, min_score: float = 75.0, max_runtime_minutes: Optional[float] = None):
        interval = float(interval_hours if interval_hours is not None else self.daemon_interval_hours)
        runtime_limit = float(max_runtime_minutes if max_runtime_minutes is not None else self.max_runtime_minutes)
        console.print(Panel(
            f"[bold green]🚀 Autonomous Job Hunting Daemon Activated[/bold green]\n"
            f"Interval: Every [bold]{interval:.1f}[/bold] hours | Minimum Match Score: [bold]{min_score}%[/bold]\n"
            f"Precautionary Timeout: [bold]{runtime_limit:.1f}[/bold] minutes per cycle\n"
            f"Daily Limits: LinkedIn [bold]{self.daily_max_linkedin}[/bold] | Naukri [bold]{self.daily_max_naukri}[/bold]\n"
            f"Press [bold red]Ctrl+C[/bold red] to gracefully stop anytime.",
            title="Antigravity Autonomous Agent",
            border_style="green"
        ))

        listener = None
        if self.notifier.is_configured():
            import threading
            from src.notifier.telegram_listener import TelegramListener
            listener = TelegramListener(
                self.settings,
                self.db,
                run_agent_callback=lambda: self.run_single_cycle(min_score=min_score, auto_apply=True, max_runtime_minutes=runtime_limit),
                run_apply_callback=lambda: self.run_single_cycle(min_score=70.0, auto_apply=True, max_runtime_minutes=runtime_limit),
                run_search_callback=lambda: self.run_single_cycle(min_score=min_score, auto_apply=False, max_runtime_minutes=20.0)
            )
            t = threading.Thread(target=listener.start_polling, kwargs={"poll_interval": 3.0}, daemon=True, name="TelegramDaemonListener")
            t.start()
            console.print("📱 [bold cyan]Telegram Remote Control Active:[/bold cyan] Listening for commands (/status, /run, /apply) from your channel.\n")

        try:
            while True:
                try:
                    self.run_single_cycle(min_score=min_score, auto_apply=True, max_runtime_minutes=runtime_limit)
                    sleep_secs = int(interval * 3600)
                    next_run = datetime.fromtimestamp(time.time() + sleep_secs).strftime("%I:%M %p")
                    console.print(f"[dim]Agent sleeping. Next scheduled autonomous run at {next_run}... (Telegram commands active)[/dim]")
                    
                    # Sleep in small increments for responsive Ctrl+C
                    wake_time = time.time() + sleep_secs
                    while time.time() < wake_time:
                        time.sleep(2)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.error(f"Unexpected error in agent cycle: {e}")
                    time.sleep(300) # retry after 5 mins
        except KeyboardInterrupt:
            console.print("\n[yellow]Autonomous Agent stopped by user (Ctrl+C).[/yellow]")
        finally:
            if listener:
                listener.stop()
