import sqlite3
import hashlib
import re
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
        if db_path:
            self.db_path = Path(db_path)
        else:
            data_db = base_dir / "data" / "job_tracker.db"
            root_db = base_dir / "job_tracker.db"
            if data_db.exists():
                self.db_path = data_db
            elif root_db.exists():
                self.db_path = root_db
            else:
                data_db.parent.mkdir(parents=True, exist_ok=True)
                self.db_path = data_db
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
                    applied_at TIMESTAMP,
                    canonical_key TEXT
                );
            """)
            # Migration check: ensure canonical_key exists on older tables
            try:
                conn.execute("ALTER TABLE jobs ADD COLUMN canonical_key TEXT;")
            except Exception:
                pass
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_key ON jobs(canonical_key);")
            conn.commit()

    @staticmethod
    def generate_canonical_key(company: str, title: str, location: str = "") -> str:
        """
        Generates a cross-platform normalized identifier for a company + role.
        Normalizes company, title tokens, and primary metro location.
        """
        # 1. Normalize company
        c = (company or "").lower()
        c = re.sub(r'\b(pvt|ltd|limited|inc|incorporated|technologies|technology|solutions|services|group|llc|corp|corporation|consulting|consultancy|india)\b', '', c)
        c = re.sub(r'[^a-z0-9]', '', c).strip()

        # 2. Normalize title
        t = (title or "").lower()
        t = re.sub(r'\(.*?\)', '', t)
        t = re.sub(r'\[.*?\]', '', t)
        t = re.sub(r'[-–|].*$', '', t)
        t = re.sub(r'exp:.*$', '', t)
        t = re.sub(r'\bsr\.?\b', 'senior', t)
        t = re.sub(r'c#|csharp|\.net|dotnet|playwright|selenium|specflow', '', t)
        t = re.sub(r'[^a-z0-9]', '', t).strip()

        # 3. Normalize primary metro location
        loc = (location or "").lower()
        metro = "india"
        for m in ["pune", "remote", "wfh", "bengaluru", "bangalore", "hyderabad", "mumbai", "chennai", "noida", "gurgaon", "delhi"]:
            if m in loc:
                metro = "bengaluru" if m == "bangalore" else ("remote" if m == "wfh" else m)
                break

        key_str = f"{c}:{t}:{metro}"
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def generate_job_id(platform: str, url: str, title: str, company: str) -> str:
        unique_str = f"{platform}:{url}:{title.lower()}:{company.lower()}"
        return hashlib.sha256(unique_str.encode("utf-8")).hexdigest()[:16]

    def is_job_seen(self, job_id: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM jobs WHERE job_id = ?", (job_id,))
            return cur.fetchone() is not None

    def is_canonical_applied(self, canonical_key: str) -> bool:
        """Checks if this company + role was already applied on ANY platform."""
        if not canonical_key:
            return False
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM jobs WHERE canonical_key = ? AND status = 'applied'", (canonical_key,))
            return cur.fetchone() is not None

    def get_canonical_applied_job(self, canonical_key: str) -> Optional[Dict[str, Any]]:
        """Returns the applied job details for a canonical key if already applied."""
        if not canonical_key:
            return None
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM jobs WHERE canonical_key = ? AND status = 'applied' LIMIT 1", (canonical_key,))
            row = cur.fetchone()
            return dict(row) if row else None

    def upsert_job(self, job: Dict[str, Any]) -> str:
        job_id = job.get("job_id") or self.generate_job_id(
            job.get("platform", "web"),
            job.get("url", ""),
            job.get("title", ""),
            job.get("company", "")
        )
        canonical_key = job.get("canonical_key") or self.generate_canonical_key(
            job.get("company", ""),
            job.get("title", ""),
            job.get("location", "")
        )
        job["canonical_key"] = canonical_key

        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO jobs (
                    job_id, platform, title, company, location, url,
                    posted_date_str, hours_ago, salary, is_easy_apply,
                    match_score, priority_tier, status, skip_reason, canonical_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    match_score = excluded.match_score,
                    priority_tier = excluded.priority_tier,
                    status = CASE WHEN jobs.status = 'applied' THEN 'applied' ELSE excluded.status END,
                    skip_reason = excluded.skip_reason,
                    canonical_key = excluded.canonical_key
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
                job.get("skip_reason", ""),
                canonical_key
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

    def get_daily_applied_count(self, platform: str) -> int:
        """Returns the number of jobs successfully applied today on the specified platform."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT count(*) FROM jobs 
                WHERE lower(platform) = lower(?) 
                  AND status = 'applied' 
                  AND (date(applied_at) = date('now') OR date(applied_at, 'localtime') = date('now', 'localtime'))
            """, (platform,))
            row = cur.fetchone()
            return row[0] if row else 0

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

            # Daily applied count
            li_today = self.get_daily_applied_count("linkedin")
            nk_today = self.get_daily_applied_count("naukri")

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
                "linkedin_today": li_today,
                "naukri_today": nk_today,
                "linkedin_limit": 50,
                "naukri_limit": 50,
                "best_paying": best_paying,
                "best_overall": best_overall
            }
