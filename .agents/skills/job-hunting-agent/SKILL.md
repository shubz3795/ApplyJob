---
name: job-hunting-agent
description: Autonomous Senior SDET job search, matching, and application workflow for Shubham Kulkarni. Searches LinkedIn and Naukri (<24h), prioritizes Pune/Remote, strictly enforces 50/day platform limits, and keeps APPLICATIONS.md in sync.
---

# Autonomous Job Hunting Agent Skill

This skill guides the AI assistant in running autonomous job discovery and application workflows for Shubham Kulkarni.

## When to Activate
Activate this skill whenever the user requests:
- Searching for new jobs on LinkedIn or Naukri
- Running applications or checking what to apply to next
- Prioritizing Pune or Remote positions
- Checking application status, daily quotas, or updating `APPLICATIONS.md`
- Running autonomous loops (`auto` / `daemon`)

## Candidate Source of Truth
- **Name:** Shubham Kulkarni (9 YOE, Senior SDET)
- **Primary Tech Stack:** C#, .NET, Playwright, Selenium, SpecFlow / Reqnroll, Azure DevOps, BDD
- **Target Domains:** Banking, Fintech, Financial Services (Prior HSBC, Virgin Money, NICE Ltd)
- **Notice Period:** 30 Days Official
- **Compensation:** Current ₹27 LPA | Target ₹32-35+ LPA
- **Location:** 📍 Top Priority: Pune & Remote / WFH | Tier 2: Hyderabad | Tier 3: Bengaluru, Mumbai

## Core Safety Invariants
1. **Never Post or Edit Profile**: Strictly no posts, comments, InMails, or profile changes on LinkedIn or Naukri.
2. **Zero Fabrication**: Only answer questionnaires from verified resume facts.
3. **Daily Application Limit**: Strictly enforce 50 applications per day on LinkedIn and 50 on Naukri.
4. **24-Hour Freshness**: Only apply to roles posted within the last 24 hours (`f_TPR=r86400`, `postDate=1`).
5. **Precautionary Timeout**: Enforce 30 minutes maximum per cycle/run (`--timeout-minutes 30.0`).

## Execution Procedures
- Search: `./.venv/bin/python run.py search --platform all`
- Apply: `./.venv/bin/python run.py apply --auto --min-score 75.0`
- Autonomous One-Shot: `./.venv/bin/python run.py auto --min-score 75.0`
- Continuous Daemon: `./.venv/bin/python run.py auto --daemon --interval-hours 10`
- Status: `./.venv/bin/python run.py status`
