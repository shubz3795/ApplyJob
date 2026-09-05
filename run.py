#!/usr/bin/env python3
import sys
import os
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
    console.print("\n[bold cyan]🔍 Starting Multi-Platform Job Search (< 24 Hours Only)[/bold cyan]")
    queries = settings.get("search_queries", {}).get("linkedin", [
        "Senior SDET C#", "Senior SDET Playwright", "Senior QA Automation C#", "SDET C# Selenium", "SDET Azure DevOps", "Senior SDET Banking"
    ])
    
    matcher = JobMatcher(resume_mgr.get_profile())
    li_scraper = LinkedInScraper()

    total_discovered = 0
    strong_matches = 0

    # 1. Search LinkedIn
    console.print(f"[bold yellow]▶ Searching LinkedIn across {len(queries)} queries (f_TPR=r86400 / <24h)...[/bold yellow]")
    for q in queries:
        console.print(f"  • Query: [green]{q}[/green] in India (<24h)...")
        jobs = li_scraper.search_jobs(q, location="India", max_results=args.limit_per_query)
        
        # Filter unseen jobs
        unseen_jobs = []
        for job in jobs:
            temp_id = db.generate_job_id(job["platform"], job["url"], job["title"], job["company"])
            if not db.is_job_seen(temp_id):
                unseen_jobs.append(job)

        if not unseen_jobs:
            continue

        # Fetch JDs concurrently
        li_scraper.fetch_descriptions_concurrently(unseen_jobs)

        for job in unseen_jobs:
            if not job.get("description"):
                continue

            # Evaluate with 6-factor Matcher
            eval_result = matcher.evaluate(job)
            job["match_score"] = eval_result["total_score_pct"]
            job["priority_tier"] = eval_result["priority"]
            job["skip_reason"] = eval_result["summary_reason"]
            job["status"] = "discovered"

            # Save to SQLite
            db.upsert_job(job)
            total_discovered += 1

            if eval_result["total_score_pct"] >= 70.0:
                strong_matches += 1
                console.print(f"    [bold green]{eval_result['priority']}[/bold green] [bold white]{job['title']}[/bold white] at [cyan]{job['company']}[/cyan] ({eval_result['total_score_pct']}%) - [italic]{job['location']}[/italic]")
            elif eval_result["total_score_pct"] >= 50.0:
                console.print(f"    [yellow]{eval_result['priority']}[/yellow] {job['title']} at {job['company']} ({eval_result['total_score_pct']}%)")

    # 2. Search Naukri (if browser flag enabled or naukri requested)
    if args.naukri:
        console.print("\n[bold yellow]▶ Searching Naukri in Headed Browser (<24h)...[/bold yellow]")
        try:
            from src.applier.browser_manager import BrowserManager
            from src.scrapers.naukri_scraper import NaukriScraper
            bm = BrowserManager(headless=False)
            naukri_scraper = NaukriScraper(browser_manager=bm)
            n_queries = settings.get("search_queries", {}).get("naukri", ["Senior SDET", "SDET C#"])[:2]
            for nq in n_queries:
                n_jobs = naukri_scraper.search_jobs(nq, experience_years=8, max_results=10)
                for job in n_jobs:
                    temp_id = db.generate_job_id(job["platform"], job["url"], job["title"], job["company"])
                    if db.is_job_seen(temp_id):
                        continue
                    eval_result = matcher.evaluate(job)
                    job["match_score"] = eval_result["total_score_pct"]
                    job["priority_tier"] = eval_result["priority"]
                    job["skip_reason"] = eval_result["summary_reason"]
                    job["status"] = "discovered"
                    db.upsert_job(job)
                    total_discovered += 1
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
    done = [j for j in all_jobs if j.get("status") == "applied"]
    todo = [j for j in all_jobs if j.get("status") in ["discovered", "queued_external"] and j.get("match_score", 0) >= 70.0]
    excluded = [j for j in all_jobs if j.get("status") == "skipped" or j.get("match_score", 0) < 70.0]

    console.print("\n" + "="*70)
    console.print(f"🎯 [bold cyan]APPLICATION TRACKER STATUS[/bold cyan] (Total Tracked: {len(all_jobs)})")
    console.print("="*70)

    # 1. Done
    console.print(f"\n[bold green]✅ 1. APPLIED (DONE): {len(done)} jobs[/bold green]")
    if done:
        t_done = Table(show_lines=True)
        t_done.add_column("Applied Date & Time", style="cyan")
        t_done.add_column("Company", style="bold white")
        t_done.add_column("Title")
        t_done.add_column("Location")
        t_done.add_column("Match %", justify="right", style="green")
        for j in done:
            t_done.add_row(j.get("applied_at", ""), j.get("company", ""), j.get("title", ""), j.get("location", ""), f"{j.get('match_score', 0):.1f}%")
        console.print(t_done)
    else:
        console.print("  [dim]No jobs submitted yet.[/dim]")

    # 2. To Do
    console.print(f"\n[bold yellow]⏳ 2. READY TO APPLY (WHAT'S LEFT): {len(todo)} jobs[/bold yellow]")
    if todo:
        t_todo = Table(show_lines=True)
        t_todo.add_column("Priority")
        t_todo.add_column("Company", style="bold white")
        t_todo.add_column("Title")
        t_todo.add_column("Location")
        t_todo.add_column("Match %", justify="right", style="green")
        for j in sorted(todo, key=lambda x: x.get("match_score", 0), reverse=True)[:10]:
            t_todo.add_row(j.get("priority_tier", ""), j.get("company", ""), j.get("title", ""), j.get("location", ""), f"{j.get('match_score', 0):.1f}%")
        console.print(t_todo)
        if len(todo) > 10:
            console.print(f"  [italic dim]...and {len(todo)-10} more high-match jobs ready in APPLICATIONS.md[/italic dim]")

    # 3. Excluded
    console.print(f"\n[bold red]🚫 3. EXCLUDED / SKIPPED: {len(excluded)} jobs[/bold red]")
    console.print(f"  [dim]Filtered out low matches or non-target stacks (see APPLICATIONS.md for full list).[/dim]\n")

def run_apply(args, resume_mgr, settings, db):
    console.print("\n[bold cyan]🚀 Starting Job Application Workflow[/bold cyan]")
    from src.applier.browser_manager import BrowserManager
    from src.applier.linkedin_applier import LinkedInApplier

    min_score = args.min_score
    all_jobs = db.get_all_jobs()
    candidates = [j for j in all_jobs if j.get("match_score", 0) >= min_score and j.get("status") != "applied"]

    if not candidates:
        console.print(f"[yellow]No unapplied jobs found with match score >= {min_score}%. Run 'search' first![/yellow]")
        return

    console.print(f"Found [bold green]{len(candidates)}[/bold green] high-match opportunities ready for application.")
    review_mode = settings.get("application", {}).get("review_mode", True)
    if args.auto:
        review_mode = False

    screener = ScreeningEngine(resume_mgr.get_profile(), settings)
    li_applier = LinkedInApplier(screener, review_mode=review_mode)

    bm = BrowserManager(headless=False)
    page = bm.new_page()

    for idx, job in enumerate(candidates, 1):
        console.print(f"\n[bold yellow][{idx}/{len(candidates)}] Processing:[/bold yellow] {job['title']} at {job['company']} ({job['match_score']}%)")
        console.print(f"Direct Link: {job['url']}")

        if job.get("platform") == "linkedin":
            success, msg = li_applier.apply(page, job)
            if success:
                db.mark_applied(job["job_id"], status_msg="applied")
                console.print(f"[bold green]✓ Status:[/bold green] {msg}")
            else:
                if "external" in msg.lower():
                    db.mark_applied(job["job_id"], status_msg="queued_external")
                    console.print(f"[bold blue]ℹ Action:[/bold blue] {msg}. Retained in external priority queue.")
                else:
                    console.print(f"[yellow]Skipped/Failed:[/yellow] {msg}")
                    db.mark_skipped(job["job_id"], reason=msg)

    bm.close()
    console.print("\n[bold green]✓ Application batch completed![/bold green]")

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
    search_p.add_argument("--naukri", action="store_true", help="Include headed Naukri search (requires browser)")

    # Report
    report_p = subparsers.add_parser("report", help="Generate the comprehensive markdown job report")
    report_p.add_argument("--output", default="job_report.md", help="Output markdown path")

    # Apply
    apply_p = subparsers.add_parser("apply", help="Apply to High Priority and Good Match jobs")
    apply_p.add_argument("--min-score", type=float, default=70.0, help="Minimum match score to apply (default: 70.0)")
    apply_p.add_argument("--auto", action="store_true", help="Auto-submit without pausing for review")

    # Setup
    subparsers.add_parser("setup", help="Open browser to log in and save session cookies")

    # Status
    subparsers.add_parser("status", help="Print simple Done, Left, and Excluded tracker status")

    # All
    all_p = subparsers.add_parser("all", help="Search, score, and generate report")
    all_p.add_argument("--limit-per-query", type=int, default=10)
    all_p.add_argument("--output", default="job_report.md")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    resume_mgr = ResumeManager()
    settings = load_settings()
    db = JobDatabase()

    if args.command == "setup":
        run_setup()
    elif args.command == "status":
        run_status(db)
    elif args.command == "search":
        run_search(args, resume_mgr, settings, db)
        run_report(argparse.Namespace(output="job_report.md"), db)
    elif args.command == "report":
        run_report(args, db)
    elif args.command == "apply":
        run_apply(args, resume_mgr, settings, db)
        run_report(argparse.Namespace(output="job_report.md"), db)
    elif args.command == "all":
        args.naukri = False
        run_search(args, resume_mgr, settings, db)
        run_report(args, db)

if __name__ == "__main__":
    main()
