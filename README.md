# Senior SDET Job Search & Application Automation Suite

An enterprise-grade, automated job discovery, matching, and application system tailored for **Senior SDET / QA Automation Engineer** roles.

Built for **Shubham Kulkarni** (9 Years Experience; C#, Playwright, Selenium, Reqnroll/SpecFlow, Azure DevOps, Banking & Public Safety).

---

## Key Architecture Highlights

- **Single Source of Truth**: Evaluates jobs strictly against [`Shubham_Kulkarni_Resume.pdf`](Shubham_Kulkarni_Resume.pdf) and structured profile data.
- **Strict 24-Hour Freshness**: Filters listings to those posted strictly within the last 24 hours (`f_TPR=r86400` on LinkedIn, `postDate=1` on Naukri).
- **6-Factor Composite Scoring Engine**:
  - 30% Technical skills (C#, Playwright, Selenium, SpecFlow/Reqnroll, BDD, Azure DevOps, RestSharp)
  - 20% Seniority / experience (~9 years)
  - 15% Freshness (< 24 hours)
  - 15% Company & domain quality (Banking / Fintech, Product MNCs)
  - 10% Compensation potential (₹30L+, ₹35L+, ₹40L+)
  - 10% Location (Pune, Mumbai, Bengaluru, Hyderabad, Chennai, Remote/Hybrid)
- **Zero-Fabrication Screening Q&A**: Uses NLP semantic pattern matching to answer screening questions truthfully. If an unknown question arises, halts and prompts the user, permanently saving verified answers in `config/question_bank.json`.
- **Hybrid ATS Copilot**:
  - Auto-applies to LinkedIn Easy Apply & Naukri Direct Apply.
  - Detects external applicant tracking systems (**Workday, Greenhouse, Lever, SmartRecruiters**) and auto-fills personal info, skills, and resume attachments.
- **Persistent Anti-Bot Session**: Playwright session with stealth evasions (`playwright-stealth`) and persistent browser profiles (`user_data/`). Log in once; sessions remain active.
- **SQLite Deduplication**: Prevents duplicate applications and logs all actions in `job_tracker.db`.

---

## Project Structure

```
ApplyJob/
├── config/
│   ├── profile.json            # Parsed profile from resume
│   ├── settings.yaml           # User configuration (Notice period, CTC, Locations)
│   └── question_bank.json      # Persistent verified screening Q&A cache
├── src/
│   ├── engine/
│   │   ├── resume_parser.py    # Extracts and validates resume text
│   │   ├── matcher.py          # 6-factor composite scoring engine
│   │   └── screener.py         # Zero-fabrication NLP screening engine
│   ├── scrapers/
│   │   ├── linkedin_scraper.py # Concurrent <24h scraper with backoff & jitter
│   │   └── naukri_scraper.py   # Headed Naukri scraper with lazy scroll
│   ├── applier/
│   │   ├── browser_manager.py  # Persistent Playwright browser session
│   │   ├── linkedin_applier.py # Easy Apply automation with Review Mode
│   │   ├── naukri_applier.py   # Naukri direct apply automation
│   │   └── external_autofill.py# Workday / Greenhouse / Lever copilot
│   ├── storage/
│   │   └── db.py               # SQLite deduplication & state tracker
│   ├── reporter/
│   │   └── report_generator.py # Formats Markdown tables & statistics
│   └── utils/
│       └── logger.py           # Structured Rich console & file logger
├── tests/                      # Pytest unit & integration test suite
├── run.py                      # Master CLI runner
└── requirements.txt            # Python dependencies
```

---

## Clean & Simple Workflow

```
[1. Search <24h]  ──►  [2. View Status]  ──►  [3. Apply & Move to Done]
python run.py search    python run.py status   python run.py apply --auto
```

### 1. Check Status Anytime (`APPLICATIONS.md`)
To see at a glance what is **Done**, what is **Left to apply**, and what was **Excluded**:
```bash
./.venv/bin/python run.py status
```
This updates two simple files:
- [`APPLICATIONS.md`](APPLICATIONS.md): A clean, human-readable checklist with exact dates, times, and direct links.
- [`applications.csv`](applications.csv): Excel / Google Sheets spreadsheet with all records.

### 2. Search Fresh Jobs (< 24 Hours)
Search across all targeted Senior SDET queries (adds newly discovered jobs to "Ready to Apply"):
```bash
./.venv/bin/python run.py search
```

### 3. Apply to Jobs (Moves from "Ready" to "Done")
Automatically applies to top-ranked jobs and excludes already-applied jobs:
```bash
./.venv/bin/python run.py apply --auto --min-score 80.0
```

### 4. Run Automated Test Suite
```bash
./.venv/bin/pytest tests/ -v
```
