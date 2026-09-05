import csv
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime

class ReportGenerator:
    """
    Generates a clean, simple, easy-to-maintain application record:
    1. APPLICATIONS.md (What is Done, What is Left, What is Excluded)
    2. applications.csv (Excel / Sheets exportable)
    """

    def __init__(self, jobs: List[Dict[str, Any]], stats: Dict[str, Any]):
        self.jobs = jobs
        self.stats = stats

    def generate_markdown(self) -> str:
        return self.generate_applications_markdown()

    def generate_applications_markdown(self) -> str:
        lines = []
        now_str = datetime.now().strftime('%A, %d %b %Y, %I:%M %p')
        lines.append("# 🎯 Senior SDET Job Application Tracker\n")
        lines.append(f"**Last Updated:** {now_str} | **Candidate:** Shubham Kulkarni (9 YOE, C#, Playwright, Azure DevOps)\n")

        # Partition jobs
        done_jobs = [j for j in self.jobs if j.get("status") == "applied"]
        todo_jobs = [j for j in self.jobs if j.get("status") in ["discovered", "queued_external"] and j.get("match_score", 0) >= 70.0]
        excluded_jobs = [j for j in self.jobs if j.get("status") == "skipped" or j.get("match_score", 0) < 70.0]

        # -------------------------------------------------------------
        # 1. WHAT WAS DONE (APPLIED)
        # -------------------------------------------------------------
        lines.append("## ✅ 1. APPLIED (DONE)")
        if done_jobs:
            lines.append("| Date & Time Applied | Company | Job Title | Location | Match % | Direct Link |")
            lines.append("|---|---|---|---|---:|---|")
            for j in done_jobs:
                applied_time = j.get("applied_at") or now_str
                lines.append(f"| {applied_time} | **{j.get('company')}** | {j.get('title')} | {j.get('location')} | **{j.get('match_score', 0):.1f}%** | [View Listing]({j.get('url')}) |")
        else:
            lines.append("*No jobs applied yet in current session.*")

        lines.append("\n---\n")

        # -------------------------------------------------------------
        # 2. WHAT IS LEFT (READY TO APPLY)
        # -------------------------------------------------------------
        lines.append("## ⏳ 2. READY TO APPLY (WHAT'S LEFT / TO-DO)")
        lines.append("> These jobs are fresh (<24 hours) and scored >= 70% match against your resume, prioritized by score.\n")
        if todo_jobs:
            lines.append("| Priority | Company | Job Title | Location | Match % | Direct Apply URL |")
            lines.append("|---|---|---|---|---:|---|")
            for j in sorted(todo_jobs, key=lambda x: x.get("match_score", 0), reverse=True):
                priority = j.get("priority_tier", "🟢 GOOD MATCH")
                lines.append(f"| {priority} | **{j.get('company')}** | {j.get('title')} | {j.get('location')} | **{j.get('match_score', 0):.1f}%** | [Apply Now]({j.get('url')}) |")
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
        lines.append(f"- **📁 Total Tracked:** {len(self.jobs)}")

        return "\n".join(lines)

    def save_all_records(self, base_dir: Path = None):
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent.parent

        # 1. Save APPLICATIONS.md
        md_content = self.generate_applications_markdown()
        md_file = base_dir / "APPLICATIONS.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(md_content)

        # 2. Also save legacy job_report.md for compatibility
        legacy_file = base_dir / "job_report.md"
        with open(legacy_file, "w", encoding="utf-8") as f:
            f.write(md_content)

        # 3. Save applications.csv for Excel
        csv_file = base_dir / "applications.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
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
