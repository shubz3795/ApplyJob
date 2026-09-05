import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
import pypdf

class ResumeManager:
    """
    Manages the user's resume and verified profile data.
    Ensures zero hallucination and strict adherence to the resume source of truth.
    """
    def __init__(self, resume_path: Optional[str] = None, profile_path: Optional[str] = None):
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.resume_path = Path(resume_path) if resume_path else base_dir / "Shubham_Kulkarni_Resume.pdf"
        self.profile_path = Path(profile_path) if profile_path else base_dir / "config" / "profile.json"
        
        self.raw_text = self._extract_pdf_text()
        self.profile_data = self._load_profile_data()

    def _extract_pdf_text(self) -> str:
        if not self.resume_path.exists():
            raise FileNotFoundError(f"Resume PDF not found at: {self.resume_path}")
        
        reader = pypdf.PdfReader(str(self.resume_path))
        text_parts = []
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        
        full_text = "\n".join(text_parts)
        # Sanity check
        if "SHUBHAM KULKARNI" not in full_text.upper():
            raise ValueError("Parsed PDF does not match Shubham Kulkarni's resume!")
        return full_text

    def _load_profile_data(self) -> Dict[str, Any]:
        if not self.profile_path.exists():
            raise FileNotFoundError(f"Profile data not found at: {self.profile_path}")
        with open(self.profile_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_profile(self) -> Dict[str, Any]:
        return self.profile_data

    def get_raw_text(self) -> str:
        return self.raw_text

    def get_skill_years(self, skill_name: str) -> Optional[int]:
        skills = self.profile_data.get("skill_years", {})
        norm_skill = skill_name.strip().lower()
        return skills.get(norm_skill)

if __name__ == "__main__":
    mgr = ResumeManager()
    print(f"Loaded resume successfully! Length: {len(mgr.get_raw_text())} characters.")
    print(f"Candidate: {mgr.profile_data['personal']['full_name']}")
    print(f"Experience: {mgr.profile_data['professional']['total_experience_years']} years")
    print(f"Core skills: {mgr.profile_data['skills']['test_automation']}")
