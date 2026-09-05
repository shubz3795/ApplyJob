import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

class JobDatabase:
    """
    SQLite persistence layer for discovered, applied, and skipped jobs.
    Ensures zero duplicate applications and persistent tracking across sessions.
    """

    def __init__(self, db_path: Optional[str] = None):
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.db_path = Path(db_path) if db_path else base_dir / "job_tracker.db"
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT,
                    url TEXT NOT NULL,
                    posted_date_str TEXT,
                    hours_ago REAL,
                    salary TEXT,
                    is_easy_apply INTEGER DEFAULT 0,
                    match_score REAL,
                    priority_tier TEXT,
                    status TEXT DEFAULT 'discovered',
                    skip_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    applied_at TIMESTAMP
                );
            """)
            conn.commit()

    @staticmethod
    def generate_job_id(platform: str, url: str, title: str, company: str) -> str:
        unique_str = f"{platform}:{url}:{title.lower()}:{company.lower()}"
        return hashlib.sha256(unique_str.encode("utf-8")).hexdigest()[:16]

    def is_job_seen(self, job_id: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM jobs WHERE job_id = ?", (job_id,))
            return cur.fetchone() is not None

    def upsert_job(self, job: Dict[str, Any]) -> str:
        job_id = job.get("job_id") or self.generate_job_id(
            job.get("platform", "web"),
            job.get("url", ""),
            job.get("title", ""),
            job.get("company", "")
        )
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO jobs (
                    job_id, platform, title, company, location, url,
                    posted_date_str, hours_ago, salary, is_easy_apply,
                    match_score, priority_tier, status, skip_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    match_score = excluded.match_score,
                    priority_tier = excluded.priority_tier,
                    status = CASE WHEN jobs.status = 'applied' THEN 'applied' ELSE excluded.status END,
                    skip_reason = excluded.skip_reason
            """, (
                job_id,
                job.get("platform", "unknown"),
                job.get("title", "Untitled"),
                job.get("company", "Unknown"),
                job.get("location", ""),
                job.get("url", ""),
                job.get("posted_date_str", ""),
                job.get("hours_ago", 0.0),
                job.get("salary", "Not Disclosed"),
                1 if job.get("is_easy_apply") else 0,
                job.get("match_score", 0.0),
                job.get("priority_tier", "🟡 POSSIBLE MATCH"),
                job.get("status", "discovered"),
                job.get("skip_reason", "")
            ))
            conn.commit()
        return job_id

    def mark_applied(self, job_id: str, status_msg: str = "applied"):
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE jobs 
                SET status = ?, applied_at = CURRENT_TIMESTAMP
                WHERE job_id = ?
            """, (status_msg, job_id))
            conn.commit()

    def mark_skipped(self, job_id: str, reason: str):
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE jobs 
                SET status = 'skipped', skip_reason = ?
                WHERE job_id = ?
            """, (reason, job_id))
            conn.commit()

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM jobs ORDER BY match_score DESC, hours_ago ASC")
            return [dict(row) for row in cur.fetchall()]

    def get_summary_stats(self) -> Dict[str, Any]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM jobs WHERE platform = 'linkedin'")
            linkedin_count = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM jobs WHERE platform = 'naukri'")
            naukri_count = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM jobs WHERE priority_tier IN ('🔥 HIGH PRIORITY', '🟢 GOOD MATCH')")
            strong_matches = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM jobs WHERE status = 'applied'")
            applied_count = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM jobs WHERE status = 'skipped'")
            skipped_count = cur.fetchone()[0]

            # Best paying
            cur.execute("SELECT company, salary, match_score FROM jobs WHERE salary != 'Not Disclosed' ORDER BY match_score DESC LIMIT 1")
            best_paying_row = cur.fetchone()
            best_paying = f"{best_paying_row['company']} ({best_paying_row['salary']})" if best_paying_row else "Competitive (MNC Standard)"

            # Best overall
            cur.execute("SELECT title, company, match_score FROM jobs ORDER BY match_score DESC LIMIT 1")
            best_overall_row = cur.fetchone()
            best_overall = f"{best_overall_row['title']} at {best_overall_row['company']} ({best_overall_row['match_score']}%)" if best_overall_row else "None"

            return {
                "linkedin_count": linkedin_count,
                "naukri_count": naukri_count,
                "strong_matches": strong_matches,
                "applied_count": applied_count,
                "skipped_count": skipped_count,
                "best_paying": best_paying,
                "best_overall": best_overall
            }
