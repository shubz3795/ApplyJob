import re
from typing import Dict, Any, Tuple, List, Optional

class JobMatcher:
    """
    Evaluates job postings against Shubham Kulkarni's resume with the exact 6-factor formula:
    - 30% Technical skill match
    - 20% Experience / seniority match
    - 15% Job freshness (< 24 hours)
    - 15% Role quality / company quality
    - 10% Compensation potential
    - 10% Location / work arrangement
    """

    CORE_SKILLS = {
        # Strongest skills (High weight)
        "c#": 1.2,
        ".net": 1.1,
        "playwright": 1.3,
        "selenium": 1.1,
        "reqnroll": 1.2,
        "specflow": 1.1,
        "bdd": 1.0,
        "azure devops": 1.1,
        "azure pipelines": 1.1,
        "ci/cd": 1.0,
        "parallel execution": 1.1,
        "framework development": 1.2,
        "automation architecture": 1.2,
        "wiremock": 1.0,
        "rest api": 1.0,
        "restsharp": 1.1,
        "allure": 0.9,
        "nunit": 1.0,
        "ai": 1.1,
        "copilot": 1.0,
        "agentic": 1.1
    }

    NEGATIVE_PENALTY_SKILLS = [
        # Heavy competitor stacks where C# is absent
        "java only",
        "python only",
        "appium",
        "mobile automation",
        "embedded c",
        "salesforce qa"
    ]

    PREFERRED_LOCATIONS = [
        "pune", "mumbai", "bengaluru", "bangalore", "hyderabad", "chennai", "remote", "hybrid"
    ]

    TOP_TIER_COMPANIES = [
        "hsbc", "barclays", "virgin money", "nice", "morgan stanley", "jpmorgan", "goldman sachs",
        "ubs", "bnymellon", "citi", "standard chartered", "fidelity", "natwest", "mastercard",
        "visa", "microsoft", "amazon", "google", "cisco", "oracle", "adobe", "salesforce",
        "sap", "intuit", "servicenow", "atlassian", "crowdstrike", "palo alto", "accenture", "ey", "pwc", "deloitte"
    ]

    def __init__(self, profile: Dict[str, Any]):
        self.profile = profile

    def evaluate(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        Job dictionary must include:
        - title: str
        - company: str
        - description: str
        - location: str
        - posted_time_str: str (or hours_ago: float)
        - salary: Optional[str] (e.g. "30-40 Lacs P.A.", "Not Disclosed")
        - is_easy_apply: bool
        """
        title = job.get("title", "").lower()
        company = job.get("company", "").lower()
        desc = job.get("description", "").lower()
        loc = job.get("location", "").lower()
        hours_ago = job.get("hours_ago", 12.0)
        salary_str = job.get("salary", "Not Disclosed")

        combined_text = f"{title} {company} {desc}"

        # 1. Technical Skill Match (30%)
        tech_score, matched_skills, missing_skills = self._eval_tech_skills(combined_text)

        # 2. Seniority & Experience Match (20%)
        exp_score, exp_reason = self._eval_seniority_and_exp(title, combined_text)

        # 3. Freshness Match (15%)
        freshness_score, freshness_reason = self._eval_freshness(hours_ago, job.get("posted_time_str", ""))

        # 4. Role & Company Quality (15%)
        comp_quality_score, comp_quality_reason = self._eval_company_and_role(title, company, combined_text)

        # 5. Compensation Potential (10%)
        comp_potential_score, comp_potential_reason = self._eval_compensation(salary_str, company)

        # 6. Location & Work Arrangement (10%)
        location_score, location_reason = self._eval_location(loc, combined_text)

        # Total Composite Score
        total_score = (
            (tech_score * 0.30) +
            (exp_score * 0.20) +
            (freshness_score * 0.15) +
            (comp_quality_score * 0.15) +
            (comp_potential_score * 0.10) +
            (location_score * 0.10)
        )
        total_score_pct = round(total_score, 1)

        # Classification
        if total_score_pct >= 85.0:
            priority = "🔥 HIGH PRIORITY"
            action = "Apply"
        elif total_score_pct >= 70.0:
            priority = "🟢 GOOD MATCH"
            action = "Apply"
        elif total_score_pct >= 50.0:
            priority = "🟡 POSSIBLE MATCH"
            action = "Consider"
        else:
            priority = "🔴 LOW MATCH"
            action = "Skip"

        # Generate blunt explanation
        reasons = []
        if matched_skills:
            reasons.append(f"Strong tech matches: {', '.join(matched_skills[:5])}")
        if exp_reason:
            reasons.append(exp_reason)
        if comp_quality_reason:
            reasons.append(comp_quality_reason)
        if freshness_score < 50:
            reasons.append(f"Old posting ({freshness_reason})")
        if location_score < 60:
            reasons.append(f"Location friction: {loc}")

        summary_reason = " | ".join(reasons) if reasons else "Keyword match"

        return {
            "total_score_pct": total_score_pct,
            "priority": priority,
            "action": action,
            "summary_reason": summary_reason,
            "breakdown": {
                "tech_score": round(tech_score, 1),
                "exp_score": round(exp_score, 1),
                "freshness_score": round(freshness_score, 1),
                "comp_quality_score": round(comp_quality_score, 1),
                "comp_potential_score": round(comp_potential_score, 1),
                "location_score": round(location_score, 1)
            },
            "matched_skills": matched_skills,
            "missing_skills": missing_skills
        }

    @staticmethod
    def _contains_word(keyword: str, text: str) -> bool:
        """Accurately checks for keywords including special symbols like C#, .NET, C++"""
        if keyword in ["c#", "csharp"]:
            return bool(re.search(r'(?:^|[\s,/(])(?:c#|csharp)(?:$|[\s,/)!.;])', text, re.IGNORECASE))
        elif keyword in [".net", "dotnet"]:
            return bool(re.search(r'(?:^|[\s,/(])(?:\.net|dotnet)(?:$|[\s,/)!.;])', text, re.IGNORECASE))
        else:
            escaped = re.escape(keyword)
            return bool(re.search(r'\b' + escaped + r'\b', text, re.IGNORECASE))

    def _eval_tech_skills(self, text: str) -> Tuple[float, List[str], List[str]]:
        matched = []
        missing = []
        for skill in self.CORE_SKILLS:
            if self._contains_word(skill, text):
                matched.append(skill)
            else:
                missing.append(skill)

        # Essential core checks
        has_csharp = self._contains_word("c#", text) or self._contains_word(".net", text) or self._contains_word("csharp", text)
        has_playwright = self._contains_word("playwright", text)
        has_selenium = self._contains_word("selenium", text)
        has_automation = has_playwright or has_selenium or self._contains_word("automation", text) or self._contains_word("sdet", text)
        has_bdd = self._contains_word("bdd", text) or self._contains_word("specflow", text) or self._contains_word("reqnroll", text)
        has_api = self._contains_word("api", text) or self._contains_word("rest", text) or self._contains_word("restsharp", text) or self._contains_word("wiremock", text)
        has_devops = self._contains_word("azure", text) or self._contains_word("ci/cd", text) or self._contains_word("pipeline", text) or self._contains_word("devops", text)
        has_competitor = bool(re.search(r'\b(java|python|golang|ruby)\b', text, re.IGNORECASE))

        # Check if C# is negated (e.g. 'no c#', 'not c#', 'without c#')
        if bool(re.search(r'\b(?:no|not|without)\s+(?:c#|csharp|\.net)\b', text, re.IGNORECASE)):
            has_csharp = False

        # Base ATS match calculation
        tech_score = 0.0

        # Anchor 1: Programming Language (40 pts)
        if has_csharp:
            tech_score += 40.0
        elif not has_competitor:
            # Neutral / generic automation posting
            tech_score += 25.0
        else:
            # Competitor stack (e.g. Pure Java/Python)
            tech_score += 5.0

        # Anchor 2: Core Automation Framework (25 pts)
        if has_playwright and has_selenium:
            tech_score += 25.0
        elif has_playwright or has_selenium:
            tech_score += 22.0
        elif has_automation:
            tech_score += 15.0

        # Anchor 3: BDD / Framework Design (15 pts)
        if has_bdd or self._contains_word("framework", text) or self._contains_word("pom", text):
            tech_score += 15.0
        else:
            tech_score += 5.0

        # Anchor 4: API & DevOps / CI/CD (20 pts)
        if has_api and has_devops:
            tech_score += 20.0
        elif has_api or has_devops:
            tech_score += 12.0
        else:
            tech_score += 5.0

        # Bonus for AI testing / WireMock / Allure / Parallel
        if self._contains_word("ai", text) or self._contains_word("copilot", text) or self._contains_word("wiremock", text) or self._contains_word("parallel", text):
            tech_score = min(tech_score + 5.0, 100.0)

        # Deduct for irrelevant / non-target skill sets (e.g. Appium mobile, embedded)
        for ps in self.NEGATIVE_PENALTY_SKILLS:
            if self._contains_word(ps, text):
                tech_score = max(tech_score - 25.0, 0.0)
                break

        # Severe penalty if JD explicitly mandates Java or Python without C#
        if not has_csharp and has_competitor:
            tech_score = min(tech_score * 0.4, 25.0)

        return min(max(tech_score, 0.0), 100.0), matched, missing

    def _eval_seniority_and_exp(self, title: str, text: str) -> Tuple[float, str]:
        # Target: ~9 years (Senior SDET / QA Automation Engineer / Lead)
        senior_titles = ["senior", "sr", "lead", "principal", "staff", "architect", "manager", "sdet iii", "sdet ii", "specialist"]
        is_senior_title = any(st in title for st in senior_titles)
        
        # Check explicit experience requirements in JD (e.g. 7-10 years, 8+ years)
        exp_matches = re.findall(r'(\d{1,2})\s*(?:-|to|\+)\s*(\d{1,2})?\s*(?:years?|yrs?)', text)
        
        req_min = None
        req_max = None
        if exp_matches:
            for match in exp_matches:
                try:
                    v1 = int(match[0])
                    v2 = int(match[1]) if match[1] else v1
                    if 1 <= v1 <= 20:
                        req_min = v1
                        req_max = v2
                        break
                except ValueError:
                    continue

        if req_min is not None:
            if 6 <= req_min <= 10:
                return 100.0, f"Perfect experience match ({req_min}-{req_max} yrs)"
            elif req_min < 5:
                return 75.0, f"Slightly junior ({req_min} yrs req)"
            elif req_min > 12:
                return 50.0, f"Experience req too high ({req_min}+ yrs)"
            else:
                return 85.0, f"Acceptable exp range ({req_min}-{req_max} yrs)"

        if is_senior_title:
            return 95.0, "Senior / Lead level role"
        elif "junior" in title or "entry" in title or "intern" in title:
            return 20.0, "Junior / Intern role (Skip)"
        else:
            return 80.0, "Standard SDET role"

    def _eval_freshness(self, hours_ago: float, posted_str: str) -> Tuple[float, str]:
        if hours_ago <= 12:
            return 100.0, f"Posted {int(hours_ago)} hours ago"
        elif hours_ago <= 24:
            return 90.0, f"Posted {int(hours_ago)} hours ago"
        elif hours_ago <= 48:
            return 50.0, "Posted 1-2 days ago"
        else:
            return 20.0, "Older than 48 hours"

    def _eval_company_and_role(self, title: str, company: str, text: str) -> Tuple[float, str]:
        score = 75.0
        reason = "Standard employer"

        # Domain match: Banking / Fintech (Shubham has direct HSBC & Virgin Money experience)
        is_banking = any(b in text for b in ["banking", "fintech", "financial services", "hsbc", "barclays", "payment", "wealth", "trading"])
        if is_banking:
            score += 15.0
            reason = "Banking / Fintech domain (Strong match)"

        # Product MNC / Top Tier
        if any(top in company for top in self.TOP_TIER_COMPANIES):
            score = max(score, 95.0)
            reason = f"Top-tier MNC / Enterprise ({company.title()})"

        return min(score, 100.0), reason

    def _eval_compensation(self, salary_str: str, company: str) -> Tuple[float, str]:
        if not salary_str or "not disclosed" in salary_str.lower():
            # If undisclosed but top-tier company, assume high potential
            if any(top in company for top in self.TOP_TIER_COMPANIES):
                return 85.0, "Undisclosed (Top tier company: ₹30-40L+ potential)"
            return 75.0, "Undisclosed salary"

        # Extract numeric CTC in LPA
        lacs_match = re.findall(r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(?:lpa|lacs?|lac|lakhs?)', salary_str.lower())
        if lacs_match:
            try:
                min_c = float(lacs_match[0][0])
                max_c = float(lacs_match[0][1]) if lacs_match[0][1] else min_c
                if max_c >= 40.0:
                    return 100.0, f"Exceptional salary: {salary_str} (₹40L+)"
                elif max_c >= 35.0:
                    return 95.0, f"High salary: {salary_str} (₹35L+)"
                elif max_c >= 30.0:
                    return 85.0, f"Target salary: {salary_str} (₹30L+)"
                elif max_c < 20.0:
                    return 40.0, f"Below target: {salary_str}"
                else:
                    return 70.0, f"Salary: {salary_str}"
            except Exception:
                pass

        return 75.0, f"Salary: {salary_str}"

    def _eval_location(self, location_str: str, text: str) -> Tuple[float, str]:
        loc = f"{location_str} {text}".lower()
        if "pune" in loc:
            return 100.0, "Top Priority: Pune"
        elif any(p in loc for p in ["remote", "work from home", "wfh"]):
            return 100.0, "Top Priority: Remote / WFH"
        elif "hyderabad" in loc:
            return 85.0, "Tier 2 Metro (Hyderabad)"
        elif any(p in loc for p in ["bengaluru", "bangalore", "mumbai", "chennai"]):
            return 75.0, f"Tier 3 Metro ({location_str})"
        elif "hybrid" in loc:
            return 75.0, "Hybrid India"
        elif "india" in loc:
            return 70.0, "Pan-India"
        else:
            return 50.0, f"Other location ({location_str})"
