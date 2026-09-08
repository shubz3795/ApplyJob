import csv
import json
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime

class ReportGenerator:
    """
    Generates clean, structured application records:
    1. Master Dashboard: APPLICATIONS.md (root)
    2. Per-Run Output: reports/runs/run_YYYY-MM-DD_HH-MM-SS.md
    3. Run History Index: reports/run_history.json
    4. Excel / Sheets Export: data/applications.csv
    """

    def __init__(self, jobs: List[Dict[str, Any]], stats: Dict[str, Any]):
        self.jobs = jobs
        self.stats = stats

    def generate_markdown(self) -> str:
        return self.generate_applications_markdown()

    def generate_applications_markdown(self, recent_runs: Optional[List[Dict[str, Any]]] = None) -> str:
        lines = []
        now_str = datetime.now().strftime('%A, %d %b %Y, %I:%M %p')
        lines.append("# 🎯 Senior SDET Job Application Tracker\n")
        lines.append(f"**Last Updated:** {now_str} | **Candidate:** Shubham Kulkarni (9 YOE, C#, Playwright, Azure DevOps)\n")

        # Partition jobs
        done_jobs = [j for j in self.jobs if j.get("status") == "applied"]
        todo_jobs = [j for j in self.jobs if j.get("status") in ["discovered", "queued_external"] and j.get("match_score", 0) >= 70.0]
        excluded_jobs = [j for j in self.jobs if j.get("status") == "skipped" or j.get("match_score", 0) < 70.0]

        # -------------------------------------------------------------
        # RECENT RUNS (AUDIT TRAIL)
        # -------------------------------------------------------------
        if recent_runs:
            lines.append("## 📜 Recent Autonomous Runs")
            lines.append("| Run Timestamp | Mode | Applied This Run | Remaining To-Do | Status | Detailed Run Log |")
            lines.append("|---|---|---:|---:|---|---|")
            for r in recent_runs[:5]:
                slug = r.get("report_file", "")
                status_icon = "⏱️ Timed Out" if r.get("timed_out") else "✅ Completed"
                lines.append(f"| {r.get('timestamp', '')} | `{r.get('mode', 'auto')}` | **{r.get('applied_count', 0)}** | {r.get('remaining_count', 0)} | {status_icon} | [{slug}](file://{r.get('report_path', '')}) |")
            lines.append("\n---\n")

        # -------------------------------------------------------------
        # 1. WHAT WAS DONE (APPLIED)
        # -------------------------------------------------------------
        lines.append("## ✅ 1. APPLIED (DONE)")
        if done_jobs:
            lines.append("| Date & Time Applied | Platform | Company | Job Title | Location | Match % | Direct Link |")
            lines.append("|---|---|---|---|---|---:|---|")
            for j in done_jobs:
                applied_time = j.get("applied_at") or now_str
                platform = j.get("platform", "linkedin").capitalize()
                lines.append(f"| {applied_time} | **{platform}** | **{j.get('company')}** | {j.get('title')} | {j.get('location')} | **{j.get('match_score', 0):.1f}%** | [View Listing]({j.get('url')}) |")
        else:
            lines.append("*No jobs applied yet in current session.*")

        lines.append("\n---\n")

        # -------------------------------------------------------------
        # 2. WHAT IS LEFT (READY TO APPLY)
        # -------------------------------------------------------------
        lines.append("## ⏳ 2. READY TO APPLY (WHAT'S LEFT / TO-DO)")
        lines.append("> 🎯 **Location Priority:** Roles in **Pune** and **Remote / WFH** are listed first, followed by other locations. Filtered strictly for fresh postings (<24h) with match score >= 70%.\n")
        if todo_jobs:
            lines.append("| Priority | Platform | Company | Job Title | Location | Match % | Direct Apply URL |")
            lines.append("|---|---|---|---|---|---:|---|")
            
            def _is_pune_or_remote(j: Dict[str, Any]) -> bool:
                loc_txt = f"{j.get('location', '')} {j.get('title', '')}".lower()
                return any(p in loc_txt for p in ["pune", "remote", "work from home", "wfh"])

            sorted_todo = sorted(
                todo_jobs,
                key=lambda x: (
                    1 if _is_pune_or_remote(x) else 0,
                    x.get("match_score", 0),
                    -x.get("hours_ago", 999.0)
                ),
                reverse=True
            )

            for j in sorted_todo:
                priority = j.get("priority_tier", "🟢 GOOD MATCH")
                platform = j.get("platform", "linkedin").capitalize()
                loc = j.get("location", "")
                loc_lower = loc.lower()
                if "pune" in loc_lower:
                    loc_display = f"📍 **{loc}**"
                elif any(r in loc_lower for r in ["remote", "work from home", "wfh"]):
                    loc_display = f"🏡 **{loc}**"
                else:
                    loc_display = loc
                lines.append(f"| {priority} | **{platform}** | **{j.get('company')}** | {j.get('title')} | {loc_display} | **{j.get('match_score', 0):.1f}%** | [Apply Now]({j.get('url')}) |")
        else:
            lines.append("*All high-priority jobs have been applied! Run 'python run.py search' to find new postings.*")

        lines.append("\n---\n")

        # -------------------------------------------------------------
        # 3. WHAT WAS EXCLUDED (SKIPPED)
        # -------------------------------------------------------------
        lines.append("## 🚫 3. EXCLUDED / SKIPPED")
        lines.append("> Filtered out automatically to prevent bad-fit applications (e.g. non-target tech stacks like Java/Appium, junior roles, or low match scores).\n")
        if excluded_jobs:
            lines.append("| Company | Job Title | Platform | Match % | Reason Excluded |")
            lines.append("|---|---|---|---:|---|")
            for j in sorted(excluded_jobs, key=lambda x: x.get("match_score", 0)):
                reason = j.get("skip_reason") or "Match score below 70% threshold"
                lines.append(f"| {j.get('company')} | {j.get('title')} | {j.get('platform', '').capitalize()} | {j.get('match_score', 0):.1f}% | {reason} |")
        else:
            lines.append("*No jobs excluded.*")

        lines.append("\n---\n")

        # -------------------------------------------------------------
        # 4. SUMMARY AT A GLANCE
        # -------------------------------------------------------------
        lines.append("## 📊 Summary at a Glance")
        lines.append(f"- **✅ Applied (Done):** {len(done_jobs)}")
        lines.append(f"- **⏳ Left to Apply (High Matches):** {len(todo_jobs)}")
        lines.append(f"- **🚫 Excluded (Low Match / Non-Target):** {len(excluded_jobs)}")
        lines.append(f"- **📁 Total Tracked:** {len(self.jobs)}\n")

        # Daily Platform Quota Status
        li_today = self.stats.get("linkedin_today", 0)
        li_limit = self.stats.get("linkedin_limit", 50)
        nk_today = self.stats.get("naukri_today", 0)
        nk_limit = self.stats.get("naukri_limit", 50)
        lines.append("### 🛡️ Daily Application Safety Quotas")
        lines.append(f"- **LinkedIn Today:** {li_today} / {li_limit} applied ({max(0, li_limit - li_today)} remaining)")
        lines.append(f"- **Naukri Today:** {nk_today} / {nk_limit} applied ({max(0, nk_limit - nk_today)} remaining)")

        return "\n".join(lines)

    def generate_external_jobs_markdown(self) -> str:
        """
        Generates a dedicated, clean markdown file for high-match external portal jobs
        (Workday, Taleo, Greenhouse, iCIMS) filtered STRICTLY for Pune & Remote roles.
        """
        lines = []
        now_str = datetime.now().strftime('%A, %d %b %Y, %I:%M %p')
        lines.append("# 🌐 High-Match External Portal Jobs (1-Click Manual Apply)\n")
        lines.append(f"**Last Updated:** {now_str} | **Candidate:** Shubham Kulkarni (9 YOE Senior SDET)\n")
        lines.append("> 🎯 **Location Filter:** Showing **STRICTLY 📍 Pune and 🏡 Remote / WFH** opportunities with **≥70% match score**.\n")
        lines.append("> 💡 **How to use:** Click **[Apply on Company Portal]** to open and submit directly on company career portals (Workday, Taleo, Greenhouse).\n")

        def _is_pune_or_remote(j: Dict[str, Any]) -> bool:
            loc_txt = f"{j.get('location', '')} {j.get('title', '')}".lower()
            return any(p in loc_txt for p in ["pune", "remote", "work from home", "wfh"])

        external_jobs = [
            j for j in self.jobs 
            if j.get("status") == "queued_external" 
            and j.get("match_score", 0) >= 70.0
            and _is_pune_or_remote(j)
        ]

        external_jobs.sort(key=lambda x: (x.get("match_score", 0), -x.get("hours_ago", 999.0)), reverse=True)

        lines.append(f"### 📍 Available Opportunities: **{len(external_jobs)} High-Match Roles (Pune & Remote Only)**\n")

        if external_jobs:
            lines.append("| Match % | Company | Job Title | Location | Key Technical Match | Direct Portal Link |")
            lines.append("|---:|---|---|---|---|---|")
            for j in external_jobs:
                score = j.get("match_score", 0)
                company = j.get("company", "")
                title = j.get("title", "")
                loc = j.get("location", "")
                url = j.get("url", "")
                notes = j.get("skip_reason", "")
                loc_badge = f"📍 **{loc}**" if "pune" in loc.lower() else f"🏡 **{loc}**"
                lines.append(f"| **{score:.1f}%** | **{company}** | {title} | {loc_badge} | `{notes[:55]}` | [Apply on Company Portal]({url}) |")
        else:
            lines.append("*No Pune or Remote external roles currently queued. Run search to discover new postings.*")

        lines.append("\n---\n")
        lines.append("*Note: All non-Pune and non-Remote external jobs are filtered out to keep this dashboard clean and actionable.*")
        return "\n".join(lines)


    def generate_run_markdown(self, run_meta: Dict[str, Any], applied_in_this_run: List[Dict[str, Any]]) -> str:
        """
        Generates a dedicated audit log for a single execution run.
        """
        lines = []
        ts = run_meta.get("timestamp_str", datetime.now().strftime('%A, %d %b %Y, %I:%M %p'))
        mode = run_meta.get("mode", "Autonomous Cycle").upper()
        runtime_min = run_meta.get("runtime_minutes", 0.0)
        timed_out = run_meta.get("timed_out", False)
        status_banner = "⏱️ HALTED (PRECAUTIONARY TIMEOUT REACHED)" if timed_out else "✅ COMPLETED SUCCESSFULLY"

        lines.append(f"# 🚀 Run Audit Report: {mode}\n")
        lines.append(f"- **Status:** **{status_banner}**")
        lines.append(f"- **Executed At:** {ts}")
        lines.append(f"- **Duration:** {runtime_min:.1f} minutes (Max Limit: {run_meta.get('timeout_minutes', 30.0)}m)")
        lines.append(f"- **New Discovered:** {run_meta.get('discovered', 0)}")
        lines.append(f"- **Applied in this run:** {len(applied_in_this_run)}")
        lines.append(f"- **Daily Limits:** LinkedIn: {run_meta.get('li_today', 0)}/50 | Naukri: {run_meta.get('nk_today', 0)}/50\n")
        lines.append("---\n")

        # 1. Applied in this run
        lines.append("## ✅ 1. Applied in This Run")
        if applied_in_this_run:
            lines.append("| Time | Platform | Company | Title | Location | Match % | Outcome | Direct Link |")
            lines.append("|---|---|---|---|---|---:|---|---|")
            for item in applied_in_this_run:
                platform = item.get("platform", "").capitalize()
                time_str = item.get("time", "")
                company = item.get("company", "")
                title = item.get("title", "")
                loc = item.get("location", "")
                score = item.get("match_score", 0)
                outcome = item.get("outcome", "Applied")
                url = item.get("url", "#")
                lines.append(f"| {time_str} | **{platform}** | **{company}** | {title} | {loc} | **{score:.1f}%** | {outcome} | [View Listing]({url}) |")
        else:
            lines.append("*No new applications were submitted in this run.*")
        lines.append("\n---\n")

        # 2. What's left right now
        todo_jobs = [j for j in self.jobs if j.get("status") in ["discovered", "queued_external"] and j.get("match_score", 0) >= 70.0]
        def _is_pune_or_remote(j: Dict[str, Any]) -> bool:
            loc_txt = f"{j.get('location', '')} {j.get('title', '')}".lower()
            return any(p in loc_txt for p in ["pune", "remote", "work from home", "wfh"])

        sorted_todo = sorted(
            todo_jobs,
            key=lambda x: (
                1 if _is_pune_or_remote(x) else 0,
                x.get("match_score", 0),
                -x.get("hours_ago", 999.0)
            ),
            reverse=True
        )

        lines.append(f"## ⏳ 2. Remaining Ready to Apply ({len(sorted_todo)} Roles in Queue)")
        lines.append("> 🎯 **Location Priority:** Roles in **Pune** and **Remote / WFH** are listed first.\n")
        if sorted_todo:
            lines.append("| Priority | Platform | Company | Job Title | Location | Match % | Direct Apply Link |")
            lines.append("|---|---|---|---|---|---:|---|")
            for j in sorted_todo[:15]:
                priority = j.get("priority_tier", "🟢 GOOD MATCH")
                platform = j.get("platform", "linkedin").capitalize()
                loc = j.get("location", "")
                loc_lower = loc.lower()
                loc_display = f"📍 **{loc}**" if "pune" in loc_lower else (f"🏡 **{loc}**" if any(r in loc_lower for r in ["remote", "work from home", "wfh"]) else loc)
                lines.append(f"| {priority} | **{platform}** | **{j.get('company')}** | {j.get('title')} | {loc_display} | **{j.get('match_score', 0):.1f}%** | [Apply Now]({j.get('url')}) |")
            if len(sorted_todo) > 15:
                lines.append(f"\n*...and {len(sorted_todo) - 15} more roles listed in APPLICATIONS.md*")
        else:
            lines.append("*All high priority jobs have been applied.*")

        return "\n".join(lines)

    def save_run_report(self, run_meta: Dict[str, Any], applied_in_this_run: List[Dict[str, Any]], base_dir: Optional[Path] = None) -> Path:
        """
        Saves a timestamped run report in reports/runs/ and logs to reports/run_history.json.
        """
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent.parent

        runs_dir = base_dir / "reports" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        slug = now.strftime("run_%Y-%m-%d_%H-%M-%S")
        report_file = runs_dir / f"{slug}.md"

        content = self.generate_run_markdown(run_meta, applied_in_this_run)
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(content)

        # Update run_history.json
        history_file = base_dir / "reports" / "run_history.json"
        history = []
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as hf:
                    history = json.load(hf)
            except Exception:
                history = []

        todo_jobs = [j for j in self.jobs if j.get("status") in ["discovered", "queued_external"] and j.get("match_score", 0) >= 70.0]

        entry = {
            "run_id": slug,
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": run_meta.get("mode", "auto"),
            "runtime_minutes": round(run_meta.get("runtime_minutes", 0.0), 2),
            "timed_out": run_meta.get("timed_out", False),
            "discovered_count": run_meta.get("discovered", 0),
            "applied_count": len(applied_in_this_run),
            "remaining_count": len(todo_jobs),
            "report_file": f"{slug}.md",
            "report_path": str(report_file)
        }
        history.insert(0, entry)
        # Keep last 50 runs in history
        history = history[:50]

        try:
            with open(history_file, "w", encoding="utf-8") as hf:
                json.dump(history, hf, indent=2)
        except Exception:
            pass

        return report_file

    def get_recent_runs(self, base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
        history_file = base_dir / "reports" / "run_history.json"
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as hf:
                    return json.load(hf)
            except Exception:
                return []
        return []

    def save_all_records(self, base_dir: Optional[Path] = None) -> Tuple[Path, Path]:
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent.parent

        recent_runs = self.get_recent_runs(base_dir)

        # 1. Save APPLICATIONS.md
        md_content = self.generate_applications_markdown(recent_runs=recent_runs)
        md_file = base_dir / "APPLICATIONS.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(md_content)

        # 2. Also save legacy job_report.md for compatibility
        legacy_file = base_dir / "job_report.md"
        with open(legacy_file, "w", encoding="utf-8") as f:
            f.write(md_content)

        # 3. Save dedicated EXTERNAL_JOBS.md for 1-click manual apply
        ext_content = self.generate_external_jobs_markdown()
        ext_file = base_dir / "EXTERNAL_JOBS.md"
        with open(ext_file, "w", encoding="utf-8") as f:
            f.write(ext_content)

        # 4. Save applications.csv in data/ and root for convenience
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        csv_file = data_dir / "applications.csv"
        root_csv = base_dir / "applications.csv"

        for target_csv in [csv_file, root_csv]:
            with open(target_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Applied_At", "Status", "Priority", "Company", "Job_Title", "Location", "Match_Pct", "Platform", "URL", "Notes"])
                for j in self.jobs:
                    writer.writerow([
                        j.get("applied_at", ""),
                        j.get("status", "discovered"),
                        j.get("priority_tier", ""),
                        j.get("company", ""),
                        j.get("title", ""),
                        j.get("location", ""),
                        f"{j.get('match_score', 0):.1f}%",
                        j.get("platform", ""),
                        j.get("url", ""),
                        j.get("skip_reason", "")
                    ])

        return md_file, csv_file
