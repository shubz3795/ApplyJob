#!/usr/bin/env python3
import sys
import os
import time
from datetime import datetime
import argparse
import yaml
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.engine.resume_parser import ResumeManager
from src.engine.matcher import JobMatcher
from src.engine.screener import ScreeningEngine
from src.storage.db import JobDatabase
from src.reporter.report_generator import ReportGenerator
from src.scrapers.linkedin_scraper import LinkedInScraper

console = Console()

def load_settings():
    base_dir = Path(__file__).resolve().parent
    settings_file = base_dir / "config" / "settings.yaml"
    if not settings_file.exists():
        return {}
    with open(settings_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def run_search(args, resume_mgr, settings, db):
    platform_target = getattr(args, "platform", "all")
    console.print(f"\n[bold cyan]🔍 Starting Multi-Platform Job Search (< 24 Hours Only) [Target: {platform_target.upper()}][/bold cyan]")
    
    matcher = JobMatcher(resume_mgr.get_profile())
    total_discovered = 0
    strong_matches = 0

    # Extract configured filters with CLI overrides
    search_filters = settings.get("search_filters", {})
    li_filters = dict(search_filters.get("linkedin", {}))
    nk_filters = dict(search_filters.get("naukri", {}))

    # Apply CLI overrides if passed
    if getattr(args, "freshness_hours", None):
        li_filters["freshness_hours"] = args.freshness_hours
        nk_filters["post_date_days"] = max(1, int(args.freshness_hours / 24))
    elif "freshness_hours" in search_filters:
        li_filters.setdefault("freshness_hours", search_filters["freshness_hours"])

    if getattr(args, "under_10_applicants", False):
        li_filters["under_10_applicants"] = True
    if getattr(args, "include_external", False):
        li_filters["easy_apply_only"] = False
    if getattr(args, "experience_level", None) and args.experience_level != "all":
        li_filters["experience_levels"] = [args.experience_level]

    # 1. Search LinkedIn (if target is 'all' or 'linkedin')
    if platform_target in ["all", "linkedin"]:
        queries = settings.get("search_queries", {}).get("linkedin", [
            "Senior SDET C#", "Senior SDET Playwright", "Senior QA Automation C#", "SDET C# Selenium", "SDET Azure DevOps", "Senior SDET Banking"
        ])
        li_scraper = LinkedInScraper(default_filters=li_filters)
        freshness_txt = f"<{li_filters.get('freshness_hours', 24)}h"
        u10_txt = ", Under 10 applicants" if li_filters.get("under_10_applicants") else ""
        ea_txt = ", Easy Apply" if li_filters.get("easy_apply_only", True) else ""
        console.print(f"\n[bold yellow]▶ Searching LinkedIn across {len(queries)} queries ({freshness_txt}{ea_txt}{u10_txt})...[/bold yellow]")
        for q in queries:
            console.print(f"  • LinkedIn: [green]{q}[/green] in India ({freshness_txt})...")
            jobs = li_scraper.search_jobs(q, location="India", max_results=args.limit_per_query)
            
            # Filter unseen jobs
            unseen_jobs = []
            for job in jobs:
                temp_id = job.get("job_id") or db.generate_job_id(job["platform"], job["url"], job["title"], job["company"])
                job["job_id"] = temp_id
                if not db.is_job_seen(temp_id):
                    unseen_jobs.append(job)

            if not unseen_jobs:
                continue

            # Fetch JDs concurrently
            li_scraper.fetch_descriptions_concurrently(unseen_jobs)

            for job in unseen_jobs:
                if not job.get("description"):
                    continue

                eval_result = matcher.evaluate(job)
                job["match_score"] = eval_result["total_score_pct"]
                job["priority_tier"] = eval_result["priority"]
                job["skip_reason"] = eval_result["summary_reason"]
                job["status"] = "discovered"

                db.upsert_job(job)
                total_discovered += 1

                if eval_result["total_score_pct"] >= 70.0:
                    strong_matches += 1
                    console.print(f"    [bold green]{eval_result['priority']}[/bold green] [bold white]{job['title']}[/bold white] at [cyan]{job['company']}[/cyan] ({eval_result['total_score_pct']}%) - [italic]{job['location']}[/italic]")
                elif eval_result["total_score_pct"] >= 50.0:
                    console.print(f"    [yellow]{eval_result['priority']}[/yellow] {job['title']} at {job['company']} ({eval_result['total_score_pct']}%)")

    # 2. Search Naukri (if target is 'all' or 'naukri' or --naukri passed)
    if platform_target in ["all", "naukri"] or getattr(args, "naukri", False):
        p_days = nk_filters.get("post_date_days", 1)
        console.print(f"\n[bold yellow]▶ Searching Naukri in Authenticated Browser (postDate={p_days} / <{p_days*24}h)...[/bold yellow]")
        try:
            from src.applier.browser_manager import BrowserManager
            from src.scrapers.naukri_scraper import NaukriScraper
            bm = BrowserManager(headless=False)
            naukri_scraper = NaukriScraper(browser_manager=bm, default_filters=nk_filters)
            n_queries = settings.get("search_queries", {}).get("naukri", [
                "Senior SDET C#", "Senior SDET", "Senior Automation Engineer C#", "SDET C#"
            ])[:4]
            for nq in n_queries:
                console.print(f"  • Naukri: [green]{nq}[/green] in India (postDate={p_days})...")
                n_jobs = naukri_scraper.search_jobs(nq, max_results=args.limit_per_query)
                for job in n_jobs:
                    temp_id = job.get("job_id") or db.generate_job_id(job["platform"], job["url"], job["title"], job["company"])
                    job["job_id"] = temp_id
                    if db.is_job_seen(temp_id):
                        continue
                    eval_result = matcher.evaluate(job)
                    job["match_score"] = eval_result["total_score_pct"]
                    job["priority_tier"] = eval_result["priority"]
                    job["skip_reason"] = eval_result["summary_reason"]
                    job["status"] = "discovered"
                    db.upsert_job(job)
                    total_discovered += 1

                    if eval_result["total_score_pct"] >= 70.0:
                        strong_matches += 1
                        console.print(f"    [bold green]{eval_result['priority']}[/bold green] [bold white]{job['title']}[/bold white] at [cyan]{job['company']}[/cyan] ({eval_result['total_score_pct']}%) - [italic]{job['location']}[/italic]")
                    elif eval_result["total_score_pct"] >= 50.0:
                        console.print(f"    [yellow]{eval_result['priority']}[/yellow] {job['title']} at {job['company']} ({eval_result['total_score_pct']}%)")
            bm.close()
        except Exception as e:
            console.print(f"[red]Error during Naukri scrape: {e}[/red]")

    console.print(f"\n[bold green]✓ Search Complete![/bold green] Newly analyzed jobs: [bold]{total_discovered}[/bold] | Strong matches: [bold]{strong_matches}[/bold]")

def run_report(args, db):
    all_jobs = db.get_all_jobs()
    stats = db.get_summary_stats()
    reporter = ReportGenerator(all_jobs, stats)
    md_file, csv_file = reporter.save_all_records()
    console.print(f"\n📄 [bold green]Tracker file updated:[/bold green] [bold cyan]{md_file.name}[/bold cyan]")
    console.print(f"📊 [bold green]Excel export updated:[/bold green] [bold cyan]{csv_file.name}[/bold cyan]")
    run_status(db)

def run_status(db):
    all_jobs = db.get_all_jobs()
    stats = db.get_summary_stats()
    done = [j for j in all_jobs if j.get("status") == "applied"]
    todo = [j for j in all_jobs if j.get("status") in ["discovered", "queued_external"] and j.get("match_score", 0) >= 70.0]
    excluded = [j for j in all_jobs if j.get("status") == "skipped" or j.get("match_score", 0) < 70.0]

    li_today = stats.get("linkedin_today", 0)
    nk_today = stats.get("naukri_today", 0)
    li_limit = stats.get("linkedin_limit", 50)
    nk_limit = stats.get("naukri_limit", 50)

    console.print("\n" + "="*70)
    console.print(f"🎯 [bold cyan]APPLICATION TRACKER STATUS[/bold cyan] (Total Tracked: {len(all_jobs)})")
    console.print(f"🛡️  [bold green]Daily Safety Quotas:[/bold green] LinkedIn: [bold]{li_today}/{li_limit}[/bold] | Naukri: [bold]{nk_today}/{nk_limit}[/bold]")
    console.print("="*70)

    # 1. Done
    console.print(f"\n[bold green]✅ 1. APPLIED (DONE): {len(done)} jobs[/bold green]")
    if done:
        t_done = Table(show_lines=True)
        t_done.add_column("Applied Date & Time", style="cyan")
        t_done.add_column("Platform", style="magenta")
        t_done.add_column("Company", style="bold white")
        t_done.add_column("Title")
        t_done.add_column("Location")
        t_done.add_column("Match %", justify="right", style="green")
        for j in done:
            t_done.add_row(
                j.get("applied_at", ""),
                j.get("platform", "").upper(),
                j.get("company", ""),
                j.get("title", ""),
                j.get("location", ""),
                f"{j.get('match_score', 0):.1f}%"
            )
        console.print(t_done)
    else:
        console.print("  [dim]No jobs submitted yet.[/dim]")

    # 2. To Do (Prioritizing Pune & Remote first)
    console.print(f"\n[bold yellow]⏳ 2. READY TO APPLY (WHAT'S LEFT): {len(todo)} jobs[/bold yellow] (📍 Pune & 🏡 Remote prioritized first)")
    if todo:
        t_todo = Table(show_lines=True)
        t_todo.add_column("Priority")
        t_todo.add_column("Platform", style="magenta")
        t_todo.add_column("Company", style="bold white")
        t_todo.add_column("Title")
        t_todo.add_column("Location")
        t_todo.add_column("Match %", justify="right", style="green")

        def _is_pune_or_remote(j):
            loc_txt = f"{j.get('location', '')} {j.get('title', '')}".lower()
            return any(p in loc_txt for p in ["pune", "remote", "work from home", "wfh"])

        sorted_todo = sorted(
            todo,
            key=lambda x: (
                1 if _is_pune_or_remote(x) else 0,
                x.get("match_score", 0),
                -x.get("hours_ago", 999.0)
            ),
            reverse=True
        )

        for j in sorted_todo[:15]:
            loc = j.get("location", "")
            loc_lower = loc.lower()
            loc_style = f"📍 [bold cyan]{loc}[/bold cyan]" if "pune" in loc_lower else (f"🏡 [bold green]{loc}[/bold green]" if any(r in loc_lower for r in ["remote", "wfh"]) else loc)
            t_todo.add_row(
                j.get("priority_tier", ""),
                j.get("platform", "").upper(),
                j.get("company", ""),
                j.get("title", ""),
                loc_style,
                f"{j.get('match_score', 0):.1f}%"
            )
        console.print(t_todo)
        if len(todo) > 15:
            console.print(f"  [italic dim]...and {len(todo)-15} more high-match jobs ready in APPLICATIONS.md[/italic dim]")

    # 3. Excluded
    console.print(f"\n[bold red]🚫 3. EXCLUDED / SKIPPED: {len(excluded)} jobs[/bold red]")
def run_history(db):
    console.print("\n" + "="*70)
    console.print("📜 [bold cyan]AUTONOMOUS APPLICATION RUN HISTORY[/bold cyan]")
    console.print("="*70)
    reporter = ReportGenerator(db.get_all_jobs(), db.get_summary_stats())
    runs = reporter.get_recent_runs()
    if not runs:
        console.print("[yellow]No run history recorded yet. Run 'run.py auto' or 'run.py apply' to create your first run report.[/yellow]\n")
        return

    table = Table(show_lines=True)
    table.add_column("Run Timestamp", style="cyan")
    table.add_column("Mode", style="magenta")
    table.add_column("Duration", justify="right")
    table.add_column("New Discovered", justify="right")
    table.add_column("Applied", justify="right", style="green")
    table.add_column("Remaining To-Do", justify="right", style="yellow")
    table.add_column("Status")
    table.add_column("Detailed Run Audit File", style="bold white")

    for r in runs:
        status_str = "[bold red]⏱️ Timed Out[/bold red]" if r.get("timed_out") else "[bold green]✓ Completed[/bold green]"
        table.add_row(
            r.get("timestamp", ""),
            r.get("mode", "auto").upper(),
            f"{r.get('runtime_minutes', 0):.1f}m",
            str(r.get("discovered_count", 0)),
            str(r.get("applied_count", 0)),
            str(r.get("remaining_count", 0)),
            status_str,
            f"reports/runs/{r.get('report_file', '')}"
        )
    console.print(table)
    console.print(f"\n[dim]All individual run audit files are stored in [cyan]reports/runs/[/cyan][/dim]\n")

def run_apply(args, resume_mgr, settings, db):
    console.print("\n[bold cyan]🚀 Starting Job Application Workflow[/bold cyan]")
    from src.applier.browser_manager import BrowserManager
    from src.applier.linkedin_applier import LinkedInApplier

    min_score = args.min_score
    target_platform = getattr(args, "platform", "all")
    timeout_minutes = getattr(args, "timeout_minutes", None)
    if timeout_minutes is None:
        timeout_minutes = float(settings.get("safety_guards", {}).get("max_runtime_minutes", 30.0))
    start_ts = time.time()

    all_jobs = db.get_all_jobs()
    candidates = [
        j for j in all_jobs 
        if j.get("match_score", 0) >= min_score 
        and j.get("status") == "discovered"
        and j.get("is_easy_apply", True) is not False
        and (target_platform == "all" or j.get("platform") == target_platform)
    ]

    if not candidates:
        console.print(f"[yellow]No unapplied jobs found with match score >= {min_score}% on {target_platform.upper()}. Run 'search' first![/yellow]")
        return

    # Prioritize Pune & Remote first, then match score descending
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

    limits = settings.get("application_limits", {})
    max_li = limits.get("daily_max_linkedin", 50)
    max_nk = limits.get("daily_max_naukri", 50)

    li_today = db.get_daily_applied_count("linkedin")
    nk_today = db.get_daily_applied_count("naukri")

    console.print(f"Found [bold green]{len(candidates)}[/bold green] high-match opportunities ready on {target_platform.upper()} (📍 Pune & 🏡 Remote prioritized).")
    console.print(f"Daily Limits: LinkedIn [bold]{li_today}/{max_li}[/bold] | Naukri [bold]{nk_today}/{max_nk}[/bold]")
    console.print(f"Precautionary Timeout: [bold]{timeout_minutes:.1f}[/bold] minutes maximum")

    review_mode = settings.get("application", {}).get("review_mode", True)
    if args.auto:
        review_mode = False

    screener = ScreeningEngine(resume_mgr.get_profile(), settings)
    li_applier = LinkedInApplier(screener, review_mode=review_mode)
    from src.applier.naukri_applier import NaukriApplier
    nk_applier = NaukriApplier(screener, review_mode=review_mode)

    bm = BrowserManager(headless=False)
    applied_in_batch = 0
    applied_in_batch_list = []
    try:
        page = bm.new_page()

        for idx, job in enumerate(candidates, 1):
            if (time.time() - start_ts) >= (timeout_minutes * 60.0):
                console.print(f"\n[bold yellow]⏱️ Precautionary timeout reached ({timeout_minutes:.1f} mins). Halting application batch cleanly.[/bold yellow]")
                break

            platform = job.get("platform", "").lower()
            canonical_key = job.get("canonical_key") or db.generate_canonical_key(
                job.get("company", ""), job.get("title", ""), job.get("location", "")
            )
            prior_applied = db.get_canonical_applied_job(canonical_key)
            if prior_applied:
                prior_plat = prior_applied.get("platform", "other platform").capitalize()
                msg = f"Already applied on {prior_plat} ({prior_applied.get('company')} - {prior_applied.get('title')})"
                db.mark_skipped(job["job_id"], reason=msg)
                console.print(f"\n[bold yellow]⚠️ Skipping duplicate across platforms:[/bold yellow] {msg}")
                continue

            current_today = db.get_daily_applied_count(platform)
            limit_for_platform = max_li if platform == "linkedin" else max_nk

            # Check daily apply limits
            if current_today >= limit_for_platform:
                console.print(f"\n[bold yellow]⚠️  Daily apply limit reached for {platform.upper()} ({current_today}/{limit_for_platform}). Skipping to protect your account quota.[/bold yellow]")
                continue

            console.print(f"\n[bold yellow][{idx}/{len(candidates)}] Processing ({platform.upper()}):[/bold yellow] {job['title']} at {job['company']} ({job['match_score']}%) - [italic]{job.get('location', '')}[/italic]")
            console.print(f"Direct Link: {job['url']}")

            if platform == "linkedin":
                success, msg = li_applier.apply(page, job)
            elif platform == "naukri":
                success, msg = nk_applier.apply(page, job)
            else:
                success, msg = False, "Unknown platform"

            if success:
                db.mark_applied(job["job_id"], status_msg="applied")
                applied_in_batch += 1
                applied_in_batch_list.append({
                    "time": datetime.now().strftime("%I:%M %p"),
                    "platform": platform,
                    "company": job.get("company", ""),
                    "title": job.get("title", ""),
                    "location": job.get("location", ""),
                    "match_score": job.get("match_score", 0),
                    "outcome": "✅ Applied Successfully",
                    "url": job.get("url", "")
                })
                new_count = db.get_daily_applied_count(platform)
                console.print(f"[bold green]✓ Status:[/bold green] {msg} ({platform.capitalize()} Today: {new_count}/{limit_for_platform})")
            else:
                if "external" in msg.lower():
                    db.mark_applied(job["job_id"], status_msg="queued_external")
                    console.print(f"[bold blue]ℹ Action:[/bold blue] {msg}. Retained in external priority queue.")
                else:
                    is_browser_closed = any(err in msg.lower() for err in ["closed", "target page", "context destroyed"])
                    if is_browser_closed:
                        console.print(f"[bold red]⚠️ Browser/Page was closed unexpectedly: {msg}. Halting application batch cleanly.[/bold red]")
                        break
                    console.print(f"[yellow]Skipped/Failed:[/yellow] {msg}")
                    db.mark_skipped(job["job_id"], reason=msg)
    finally:
        bm.close()

    elapsed_m = (time.time() - start_ts) / 60.0
    console.print(f"\n[bold green]✓ Application batch completed in {elapsed_m:.1f}m! ({applied_in_batch} submitted in this run)[/bold green]")
    
    # Generate run report & update master tracker
    run_meta = {
        "mode": "apply",
        "trigger_type": "Easy Apply",
        "timestamp_str": datetime.now().strftime('%A, %d %b %Y, %I:%M %p'),
        "runtime_minutes": elapsed_m,
        "timeout_minutes": timeout_minutes,
        "timed_out": False,
        "discovered": 0,
        "li_today": db.get_daily_applied_count("linkedin"),
        "nk_today": db.get_daily_applied_count("naukri")
    }
    reporter = ReportGenerator(db.get_all_jobs(), db.get_summary_stats())
    run_report_path = reporter.save_run_report(run_meta, applied_in_batch_list)
    md_file, csv_file = reporter.save_all_records()
    console.print(f"📄 [bold cyan]Detailed Run Report:[/bold cyan] [underline]{run_report_path}[/underline]")
    console.print(f"📊 [bold green]Master Tracker Updated:[/bold green] [underline]{md_file.name}[/underline]")

    # Telegram Notification (if configured)
    from src.notifier.telegram_notifier import TelegramNotifier
    notifier = TelegramNotifier(settings)
    if notifier.is_configured():
        def _is_pune_or_remote(j):
            loc_txt = f"{j.get('location', '')} {j.get('title', '')}".lower()
            return any(p in loc_txt for p in ["pune", "remote", "work from home", "wfh"])

        # Strictly direct Easy Apply jobs only in queue
        top_todo = [
            j for j in db.get_all_jobs()
            if j.get("status") == "discovered"
            and j.get("is_easy_apply", True) is not False
            and j.get("match_score", 0) >= 70.0
        ]
        top_todo.sort(key=lambda x: (1 if _is_pune_or_remote(x) else 0, x.get("match_score", 0)), reverse=True)

        sent, tg_msg = notifier.send_run_summary(
            run_meta,
            applied_in_batch_list,
            top_todo[:8],
            external_jobs=None,
            send_external_template=False
        )
        if sent:
            console.print(f"📱 [bold green]Telegram Alert:[/bold green] Successfully posted trigger-wise summary (Easy Apply) to your channel.")
        else:
            console.print(f"📱 [yellow]Telegram Notice:[/yellow] {tg_msg}")

    run_status(db)

def run_telegram_test(settings):
    console.print("\n[bold cyan]📱 Testing Telegram Channel Notification[/bold cyan]")
    from src.notifier.telegram_notifier import TelegramNotifier
    notifier = TelegramNotifier(settings)
    if not notifier.bot_token or not notifier.chat_id:
        console.print("[bold red]❌ Telegram is not configured yet.[/bold red]")
        console.print("Run [cyan]./.venv/bin/python run.py telegram-setup[/cyan] or set [italic]telegram.bot_token[/italic] and [italic]telegram.chat_id[/italic] in [cyan]config/settings.yaml[/cyan].\n")
        return
    test_msg = (
        "🚀 <b>Antigravity SDET Job Agent: Telegram Connection Test</b>\n\n"
        "✅ Your Telegram private channel notification system is <b>active and working!</b>\n"
        "You will receive live application updates, match findings, and quota metrics here after every run."
    )
    success, msg = notifier.send_message(test_msg)
    if success:
        console.print(f"[bold green]✓ Success![/bold green] Test message delivered to your Telegram channel (Chat ID: {notifier.chat_id}).\n")
    else:
        console.print(f"[bold red]❌ Delivery Failed:[/bold red] {msg}\n")

def run_bot(settings, db):
    console.print("\n" + "="*70)
    console.print("🤖 [bold cyan]TELEGRAM INTERACTIVE COMMAND LISTENER[/bold cyan]")
    console.print("="*70)
    from src.notifier.telegram_listener import TelegramListener
    from src.agent.autonomous_runner import AutonomousJobAgent

    agent = AutonomousJobAgent(settings, db)
    listener = TelegramListener(
        settings,
        db,
        run_agent_callback=lambda: agent.run_single_cycle(min_score=75.0, auto_apply=True, max_runtime_minutes=30.0, easy_apply_only=True, trigger_type="Easy Apply"),
        run_apply_callback=lambda: agent.run_single_cycle(min_score=70.0, auto_apply=True, max_runtime_minutes=30.0, easy_apply_only=True, trigger_type="Easy Apply"),
        run_search_callback=lambda: agent.run_single_cycle(min_score=75.0, auto_apply=False, max_runtime_minutes=20.0, easy_apply_only=True, trigger_type="Search (<24h)")
    )
    if not listener.bot_token or not listener.target_chat_id:
        console.print("[bold red]❌ Telegram is not configured yet.[/bold red]")
        console.print("Run [cyan]./.venv/bin/python run.py telegram-setup[/cyan] first.\n")
        return

    console.print(f"✓ Connected to Telegram Bot: [bold green]{listener.notifier.bot_token[:10]}...[/bold green]")
    console.print(f"✓ Listening to Channel: [bold green]{listener.target_chat_id}[/bold green]")
    console.print("\n[bold]Supported Telegram Commands:[/bold]")
    console.print("  • [cyan]/status[/cyan]  - View real-time applied stats, Pune/Remote queue & daily quotas")
    console.print("  • [cyan]/run[/cyan]     - Start full autonomous cycle (Search, Score, Apply, Report)")
    console.print("  • [cyan]/apply[/cyan]   - Apply to top-scoring opportunities in queue")
    console.print("  • [cyan]/search[/cyan]  - Search fresh (<24h) postings without auto-applying")
    console.print("  • [cyan]/history[/cyan] - View historical run metrics")
    console.print("  • [cyan]/help[/cyan]    - Display help menu")
    console.print("\n[dim]Press Ctrl+C to stop the listener anytime.[/dim]\n")

    try:
        listener.start_polling(poll_interval=2.0)
    except KeyboardInterrupt:
        console.print("\n[yellow]Telegram listener stopped by user.[/yellow]")
    finally:
        listener.stop()

def run_service_install():
    import subprocess
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.shubham.applyjob.bot.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    base_dir = Path(__file__).resolve().parent
    python_path = base_dir / ".venv" / "bin" / "python"
    run_py_path = base_dir / "run.py"
    logs_dir = base_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.shubham.applyjob.bot</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{run_py_path}</string>
        <string>bot</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{base_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{logs_dir / "service_stdout.log"}</string>
    <key>StandardErrorPath</key>
    <string>{logs_dir / "service_stderr.log"}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:{base_dir / ".venv" / "bin"}</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>"""
    with open(plist_path, "w", encoding="utf-8") as f:
        f.write(plist_content)

    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    res = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True)
    if res.returncode == 0:
        console.print("[bold green]✓ macOS Background Service installed and active![/bold green]")
        console.print(f"Service definition: [cyan]{plist_path}[/cyan]")
        console.print("It will now run silently in the background whenever your Mac is on.\n")
    else:
        console.print(f"[bold red]❌ Failed to load service:[/bold red] {res.stderr}\n")

def run_service_uninstall():
    import subprocess
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.shubham.applyjob.bot.plist"
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        plist_path.unlink(missing_ok=True)
        console.print("[bold green]✓ macOS Background Service completely removed and stopped.[/bold green]")
        console.print("Zero remaining files or system processes.\n")
    else:
        console.print("[yellow]Service is not installed or already removed.[/yellow]\n")

def run_service_status():
    import subprocess
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.shubham.applyjob.bot.plist"
    res = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    is_loaded = "com.shubham.applyjob.bot" in res.stdout
    ps_res = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    is_running = "run.py bot" in ps_res.stdout

    console.print("\n" + "="*60)
    console.print("🍏 [bold cyan]macOS BACKGROUND SERVICE STATUS[/bold cyan]")
    console.print("="*60)
    console.print(f"Plist Installed: {'[bold green]✓ Yes[/bold green]' if plist_path.exists() else '[dim]No[/dim]'}")
    console.print(f"Service Loaded:  {'[bold green]✓ Active[/bold green]' if is_loaded else '[dim]Inactive[/dim]'}")
    console.print(f"Process Running: {'[bold green]✓ Running in background[/bold green]' if is_running else '[yellow]Stopped[/yellow]'}")
    if plist_path.exists():
        console.print(f"\nConfig Location: [dim]{plist_path}[/dim]")
        console.print("Logs: [dim]logs/service_stdout.log[/dim] and [dim]logs/applyjob.log[/dim]\n")

def run_telegram_setup(settings):
    console.print("\n[bold cyan]⚙️ Telegram Channel Notification Setup[/bold cyan]")
    console.print("Follow these 2 quick steps:")
    console.print("1. Open Telegram, search for [bold yellow]@BotFather[/bold yellow], and send [bold]/newbot[/bold] to get your Bot Token.")
    console.print("2. Open your channel (https://t.me/+cLQoQ9-VdvpmMzg1), go to Administrators -> Add Administrator, and add your bot with 'Post Messages' permission.")

    current_token = settings.get("telegram", {}).get("bot_token", "")
    current_chat_id = settings.get("telegram", {}).get("chat_id", "")

    token = input(f"\nEnter your Telegram Bot Token [{current_token or 'None'}]: ").strip() or current_token
    if not token:
        console.print("[red]Bot token cannot be empty.[/red]")
        return

    console.print("\nDetecting channel Chat ID from bot updates...")
    from src.notifier.telegram_notifier import TelegramNotifier
    chat_id, title = TelegramNotifier.detect_channel_chat_id(token)
    if chat_id:
        console.print(f"[bold green]✓ Detected Channel:[/bold green] {title} (Chat ID: {chat_id})")
    else:
        console.print("[yellow]Could not automatically detect channel ID (make sure your bot is an admin in the channel and a message was posted).[/yellow]")
        chat_id = input(f"Enter Channel Chat ID manually (e.g. -100xxxxxxxxxx) [{current_chat_id or 'None'}]: ").strip() or current_chat_id

    if not chat_id:
        console.print("[red]Chat ID is required.[/red]")
        return

    base_dir = Path(__file__).resolve().parent
    settings_file = base_dir / "config" / "settings.yaml"
    settings.setdefault("telegram", {})
    settings["telegram"]["enabled"] = True
    settings["telegram"]["bot_token"] = token
    settings["telegram"]["chat_id"] = chat_id
    with open(settings_file, "w", encoding="utf-8") as f:
        yaml.dump(settings, f, default_flow_style=False, sort_keys=False)
    console.print(f"[bold green]✓ Configuration saved to {settings_file.name}![/bold green]")
    run_telegram_test(settings)

def run_setup():
    console.print("\n[bold cyan]⚙️ Quick Setup Wizard[/bold cyan]")
    from src.applier.browser_manager import BrowserManager
    console.print("Launching visible browser so you can log into LinkedIn & Naukri...")
    console.print("Your session cookies will be stored locally in 'user_data/' for future automated runs.")
    bm = BrowserManager(headless=False)
    ctx = bm.start()
    
    # Tab 1: LinkedIn
    p_li = bm.new_page()
    p_li.goto("https://www.linkedin.com/login")

    # Tab 2: Naukri
    p_nk = ctx.new_page()
    p_nk.goto("https://www.naukri.com/nlogin/login")

    input("\n[Action Required] Once you have logged into LinkedIn and Naukri in the browser window, press ENTER here to save session...")
    bm.close()
    console.print("[bold green]✓ Session successfully saved! You are now ready to run searches and applications.[/bold green]")

def main():
    parser = argparse.ArgumentParser(description="Senior SDET Job Search & Application Automation Suite")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # Search
    search_p = subparsers.add_parser("search", help="Search jobs on LinkedIn & Naukri (<24h) and calculate match scores")
    search_p.add_argument("--limit-per-query", type=int, default=10, help="Max jobs to fetch per query (default: 10)")
    search_p.add_argument("--platform", choices=["all", "linkedin", "naukri"], default="all", help="Target platform: 'all', 'linkedin', or 'naukri' (default: all)")
    search_p.add_argument("--freshness-hours", type=int, default=None, help="Job freshness filter in hours (e.g. 24 or 48)")
    search_p.add_argument("--under-10-applicants", action="store_true", help="Filter for LinkedIn jobs with under 10 applicants (Early Applicant)")
    search_p.add_argument("--include-external", action="store_true", help="Include external corporate portal jobs (don't restrict to Easy Apply)")
    search_p.add_argument("--experience-level", choices=["entry", "associate", "mid_senior", "director", "all"], default=None, help="Filter by experience tier (default: from settings.yaml)")
    search_p.add_argument("--naukri", action="store_true", help="Include headed Naukri search (legacy alias)")

    # Report
    report_p = subparsers.add_parser("report", help="Generate the comprehensive markdown job report")
    report_p.add_argument("--output", default="APPLICATIONS.md", help="Output markdown path (default: APPLICATIONS.md)")

    # Apply
    apply_p = subparsers.add_parser("apply", help="Apply to High Priority and Good Match jobs")
    apply_p.add_argument("--min-score", type=float, default=70.0, help="Minimum match score to apply (default: 70.0)")
    apply_p.add_argument("--auto", action="store_true", help="Auto-submit without pausing for review")
    apply_p.add_argument("--platform", choices=["all", "linkedin", "naukri"], default="all", help="Platform to apply on: 'all', 'linkedin', or 'naukri' (default: all)")
    apply_p.add_argument("--timeout-minutes", type=float, default=30.0, help="Precautionary maximum runtime in minutes (default: 30.0)")

    # Auto / Autonomous Agent
    auto_p = subparsers.add_parser("auto", help="Run autonomous end-to-end job hunting agent")
    auto_p.add_argument("--daemon", action="store_true", help="Run continuously in background mode on a recurring schedule")
    auto_p.add_argument("--interval-hours", type=float, default=10.0, help="Interval between runs in hours (default: 10.0)")
    auto_p.add_argument("--min-score", type=float, default=75.0, help="Minimum match score to apply (default: 75.0)")
    auto_p.add_argument("--timeout-minutes", type=float, default=30.0, help="Precautionary cycle timeout in minutes (default: 30.0)")
    auto_p.add_argument("--no-apply", action="store_true", help="Only search and score without auto-applying")
    auto_p.add_argument("--include-external", action="store_true", help="Include external corporate portal jobs (runs in external/hybrid mode)")
    auto_p.add_argument("--easy-apply-only", action="store_true", default=None, help="Strictly target direct Easy Apply & Fast Apply jobs (default)")

    # Setup
    subparsers.add_parser("setup", help="Open browser to log in and save session cookies")

    # Status
    subparsers.add_parser("status", help="Print simple Done, Left, and Excluded tracker status")

    # History / Runs
    subparsers.add_parser("history", aliases=["runs"], help="Show history and audit logs of previous agent runs")

    # Telegram Setup & Test & Bot Listener
    subparsers.add_parser("telegram-setup", help="Interactive setup for Telegram channel notifications")
    subparsers.add_parser("telegram-test", help="Send a test ping message to your configured Telegram channel")
    subparsers.add_parser("bot", aliases=["listen"], help="Start interactive Telegram command listener (/run, /apply, /status)")

    # macOS Background Service
    subparsers.add_parser("service-install", help="Install & start native macOS background service (runs automatically on Mac startup)")
    subparsers.add_parser("service-uninstall", help="Completely uninstall & stop the macOS background service")
    subparsers.add_parser("service-status", help="Check status of the macOS background service")

    # All
    all_p = subparsers.add_parser("all", help="Search, score, and generate report")
    all_p.add_argument("--limit-per-query", type=int, default=10)
    all_p.add_argument("--output", default="APPLICATIONS.md")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    resume_mgr = ResumeManager()
    settings = load_settings()
    db = JobDatabase()

    if args.command == "auto":
        from src.agent.autonomous_runner import AutonomousJobAgent
        agent = AutonomousJobAgent(settings, db)
        if args.daemon:
            agent.run_daemon(interval_hours=args.interval_hours, min_score=args.min_score, max_runtime_minutes=args.timeout_minutes)
        else:
            easy_only = False if getattr(args, "include_external", False) else (True if getattr(args, "easy_apply_only", False) else None)
            trig_type = "External Jobs" if getattr(args, "include_external", False) else "Easy Apply"
            agent.run_single_cycle(
                min_score=args.min_score,
                auto_apply=not args.no_apply,
                max_runtime_minutes=args.timeout_minutes,
                easy_apply_only=easy_only,
                trigger_type=trig_type
            )
    elif args.command == "setup":
        run_setup()
    elif args.command == "status":
        run_status(db)
    elif args.command in ["history", "runs"]:
        run_history(db)
    elif args.command in ["bot", "listen"]:
        run_bot(settings, db)
    elif args.command == "service-install":
        run_service_install()
    elif args.command == "service-uninstall":
        run_service_uninstall()
    elif args.command == "service-status":
        run_service_status()
    elif args.command == "telegram-setup":
        run_telegram_setup(settings)
    elif args.command == "telegram-test":
        run_telegram_test(settings)
    elif args.command == "search":
        run_search(args, resume_mgr, settings, db)
        run_report(argparse.Namespace(output="APPLICATIONS.md"), db)
    elif args.command == "report":
        run_report(args, db)
    elif args.command == "apply":
        run_apply(args, resume_mgr, settings, db)
        run_report(argparse.Namespace(output="APPLICATIONS.md"), db)
    elif args.command == "all":
        args.naukri = False
        run_search(args, resume_mgr, settings, db)
        run_report(args, db)

if __name__ == "__main__":
    main()
