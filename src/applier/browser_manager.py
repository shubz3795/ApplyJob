import os
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright, Playwright, BrowserContext, Page
from playwright_stealth.stealth import Stealth

class BrowserManager:
    """
    Manages a persistent Playwright browser session with stealth evasions.
    Allows user to log into LinkedIn & Naukri once; cookies and tokens persist locally.
    """

    def __init__(self, user_data_dir: Optional[str] = None, headless: bool = False):
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.user_data_dir = Path(user_data_dir) if user_data_dir else base_dir / "user_data"
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless

        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._stealth = Stealth()

    def start(self) -> BrowserContext:
        if self._context:
            return self._context

        self._playwright = sync_playwright().start()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-default-browser-check",
            "--no-first-run",
            "--start-maximized"
        ]

        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            headless=self.headless,
            viewport=None,  # Takes native window size
            args=args,
            accept_downloads=True
        )

        return self._context

    def new_page(self) -> Page:
        ctx = self.start()
        if ctx.pages:
            page = ctx.pages[0]
        else:
            page = ctx.new_page()
        self._stealth.apply_stealth_sync(page)
        return page

    def close(self):
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
