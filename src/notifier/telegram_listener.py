import json
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path

from src.utils.logger import get_logger
from src.notifier.telegram_notifier import TelegramNotifier, _make_request

logger = get_logger("TelegramListener")

class TelegramListener:
    """
    Listens for incoming commands from Shubham's private Telegram channel or direct messages.
    Supports on-demand triggers: /status, /run, /auto, /apply, /search, /history, /help.
    """

    def __init__(
        self,
        settings: Dict[str, Any],
        db: Any,
        run_agent_callback: Optional[Callable[[], Any]] = None,
        run_apply_callback: Optional[Callable[[], Any]] = None,
        run_search_callback: Optional[Callable[[], Any]] = None,
        allowed_user_ids: Optional[List[int]] = None
    ):
        self.settings = settings
        self.db = db
        self.run_agent_callback = run_agent_callback
        self.run_apply_callback = run_apply_callback
        self.run_search_callback = run_search_callback

        self.notifier = TelegramNotifier(settings)
        self.bot_token = self.notifier.bot_token
        self.target_chat_id = str(self.notifier.chat_id).strip()

        # Authorized Telegram user IDs (Shubham K)
        self.allowed_user_ids = allowed_user_ids or [1181546323]

        self.is_running_lock = threading.Lock()
        self.current_task_info = {"active": False, "command": None, "started_at": None}
        self.stop_event = threading.Event()
        self.last_update_id = 0

    def is_authorized(self, chat_id: Any, user_id: Optional[int]) -> bool:
        """
        Validates that the update originated strictly from the configured private channel
        or Shubham's authorized Telegram user ID.
        """
        c_id = str(chat_id).strip()
        if c_id == self.target_chat_id:
            return True
        if user_id and user_id in self.allowed_user_ids:
            return True
        return False

    def handle_command(self, cmd_raw: str, chat_id: str, sender_name: str = "") -> None:
        """
        Routes and processes an incoming command.
        """
        parts = cmd_raw.strip().split()
        cmd_clean = parts[0].split("@")[0].lower()
        sub_arg = parts[1].lower() if len(parts) > 1 else ""
        logger.info(f"Received Telegram command: {cmd_clean} (arg: '{sub_arg}') from chat {chat_id} ({sender_name})")

        if cmd_clean in ["/help", "/start"]:
            self._cmd_help(chat_id)
        elif cmd_clean == "/status":
            self._cmd_status(chat_id)
        elif cmd_clean in ["/mode", "/setmode"]:
            self._cmd_mode(chat_id, sub_arg)
        elif cmd_clean in ["/external", "/externaljobs", "/links", "/manual"]:
            self._cmd_external(chat_id)
        elif cmd_clean == "/history":
            self._cmd_history(chat_id)
        elif cmd_clean in ["/run", "/auto"]:
            self._cmd_run_auto(chat_id, sub_arg)
        elif cmd_clean == "/apply":
            self._cmd_run_apply(chat_id)
        elif cmd_clean == "/search":
            self._cmd_run_search(chat_id, sub_arg)
        else:
            self.notifier.send_message(
                f"❓ Unknown command: <code>{cmd_raw}</code>\nSend /help to see all available commands.",
                chat_id=chat_id
            )

    def _cmd_help(self, chat_id: str) -> None:
        help_text = (
            "🤖 <b>Antigravity SDET Job Application Bot</b>\n\n"
            "Control the autonomous agent directly from Telegram:\n\n"
            "• <b>/run</b> or <b>/run easy</b> — Start autonomous cycle (Easy Apply only, 100% automated)\n"
            "• <b>/run external</b> — Start autonomous cycle including external corporate ATS portals\n"
            "• <b>/mode</b> — Check or switch mode: <code>/mode easy</code> or <code>/mode external</code>\n"
            "• <b>/apply</b> — Auto-apply to pending Easy Apply & Fast Apply jobs in queue\n"
            "• <b>/external</b> — View 1-click apply cards for external ATS jobs (Workday/Taleo)\n"
            "• <b>/status</b> — Check current applied stats, Pune/Remote queue & daily quotas\n"
            "• <b>/history</b> — View summary of recent agent runs\n"
            "• <b>/help</b> — Show this command list\n\n"
            "🛡️ <i>Limits: Max 50/day on LinkedIn & Naukri | 30m precautionary timeout enforced.</i>"
        )
        self.notifier.send_message(help_text, chat_id=chat_id)

    def _cmd_mode(self, chat_id: str, sub_arg: str = "") -> None:
        import yaml
        self.settings.setdefault("search_filters", {}).setdefault("linkedin", {})
        self.settings.setdefault("application", {})

        if sub_arg in ["easy", "easy_apply", "easyapply"]:
            self.settings["search_filters"]["linkedin"]["easy_apply_only"] = True
            self.settings["application"]["mode"] = "easy_apply_only"
            settings_file = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"
            try:
                with open(settings_file, "w", encoding="utf-8") as f:
                    yaml.dump(self.settings, f, default_flow_style=False, sort_keys=False)
            except Exception as e:
                logger.error(f"Failed to persist settings: {e}")
            self.notifier.send_message(
                "✅ <b>Mode Switched: Easy Apply Only</b>\n\n"
                "• Searches strictly target jobs with <b>Easy Apply</b> enabled.\n"
                "• Applications are 100% automatically submitted without external redirects.\n"
                "• Send <b>/run</b> to execute.",
                chat_id=chat_id
            )
        elif sub_arg in ["external", "hybrid", "all"]:
            self.settings["search_filters"]["linkedin"]["easy_apply_only"] = False
            self.settings["application"]["mode"] = "hybrid"
            settings_file = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"
            try:
                with open(settings_file, "w", encoding="utf-8") as f:
                    yaml.dump(self.settings, f, default_flow_style=False, sort_keys=False)
            except Exception as e:
                logger.error(f"Failed to persist settings: {e}")
            self.notifier.send_message(
                "✅ <b>Mode Switched: Hybrid (Easy Apply + External ATS)</b>\n\n"
                "• Searches will fetch both Easy Apply and External Portal (Workday/Taleo) jobs.\n"
                "• Easy Apply jobs will be 100% auto-submitted.\n"
                "• External portal jobs will be queued in <b>/external</b> with 1-click links.\n"
                "• Send <b>/run</b> to execute.",
                chat_id=chat_id
            )
        else:
            is_easy = self.settings.get("search_filters", {}).get("linkedin", {}).get("easy_apply_only", True)
            mode_str = "<b>Easy Apply Only</b> (100% auto-submit)" if is_easy else "<b>Hybrid</b> (Auto Easy Apply + Queue External ATS)"
            self.notifier.send_message(
                f"⚙️ <b>Current Application Mode:</b> {mode_str}\n\n"
                "<b>Switch modes:</b>\n"
                "• <code>/mode easy</code> — Easy Apply only (100% automated)\n"
                "• <code>/mode external</code> — Include external portals (Workday/Taleo queued in /external)\n\n"
                "<b>One-time overrides:</b>\n"
                "• <code>/run easy</code> — Run single pass for Easy Apply only\n"
                "• <code>/run external</code> — Run single pass including external portals",
                chat_id=chat_id
            )

    def _cmd_status(self, chat_id: str) -> None:
        all_jobs = self.db.get_all_jobs()
        applied = [j for j in all_jobs if j.get("status") == "applied"]
        is_easy = self.settings.get("search_filters", {}).get("linkedin", {}).get("easy_apply_only", True)
        if is_easy:
            todo = [
                j for j in all_jobs 
                if j.get("status") in ["discovered", "matched"] 
                and j.get("is_easy_apply", True) is not False 
                and j.get("match_score", 0) >= 70.0
            ]
        else:
            todo = [
                j for j in all_jobs 
                if j.get("status") in ["discovered", "matched", "queued_external"] 
                and j.get("match_score", 0) >= 70.0
            ]
        excluded = [j for j in all_jobs if j.get("status") in ["skipped", "filtered", "expired"]]

        def _is_pune_or_remote(j):
            loc_txt = f"{j.get('location', '')} {j.get('title', '')}".lower()
            return any(p in loc_txt for p in ["pune", "remote", "work from home", "wfh"])

        todo.sort(key=lambda x: (1 if _is_pune_or_remote(x) else 0, x.get("match_score", 0)), reverse=True)

        ext_pune_remote = [
            j for j in all_jobs
            if j.get("status") == "queued_external"
            and j.get("match_score", 0) >= 70.0
            and _is_pune_or_remote(j)
        ]

        li_today = self.db.get_daily_applied_count("linkedin")
        nk_today = self.db.get_daily_applied_count("naukri")

        running_indicator = ""
        if self.current_task_info["active"]:
            elapsed = (time.time() - self.current_task_info["started_at"]) / 60.0
            running_indicator = f"\n⚠️ <b>Active Run in Progress:</b> <code>{self.current_task_info['command']}</code> (Running for {elapsed:.1f}m)\n"

        ready_label = "Ready to Apply (Easy Apply ≥70%)" if is_easy else "Ready to Apply (High Match ≥70%)"
        lines = [
            "📊 <b>Autonomous Job Agent Status</b>",
            running_indicator,
            f"✅ <b>Total Applied:</b> {len(applied)} positions",
            f"⏳ <b>{ready_label}:</b> {len(todo)} jobs",
            f"🌐 <b>External 1-Click Roles (Pune & Remote):</b> {len(ext_pune_remote)} positions",
            f"🚫 <b>Excluded / Skipped:</b> {len(excluded)} jobs",
            "",
            "<b>🛡️ Daily Application Caps Today:</b>",
            f"• <b>LinkedIn:</b> {li_today} / 50 applied ({max(0, 50 - li_today)} remaining)",
            f"• <b>Naukri:</b> {nk_today} / 50 applied ({max(0, 50 - nk_today)} remaining)",
            ""
        ]

        if todo:
            queue_title = "📍 Top Easy Apply Opportunities (Pune & Remote Prioritized):" if is_easy else "📍 Top Pending Opportunities (Pune & Remote Prioritized):"
            lines.append(f"<b>{queue_title}</b>")
            for j in todo[:5]:
                comp = j.get("company", "Company")
                titl = j.get("title", "Job Title")
                sc = j.get("match_score", 0)
                plat = j.get("platform", "").capitalize()
                loc = j.get("location", "")
                loc_badge = "📍 Pune" if "pune" in loc.lower() else ("🏡 Remote" if any(r in loc.lower() for r in ["remote", "wfh"]) else loc)
                lines.append(f"• <b>{comp}</b> — {titl} (<b>{sc:.1f}%</b>) [{plat}] <i>{loc_badge}</i>")
            if len(todo) > 5:
                lines.append(f"<i>...and {len(todo) - 5} more ready in queue. Send /apply to submit.</i>")

        if ext_pune_remote:
            lines.append(f"\n💡 <i>Send /external to view 1-click apply message cards</i>")

        self.notifier.send_message("\n".join(lines), chat_id=chat_id)

    def _cmd_external(self, chat_id: str) -> None:
        all_jobs = self.db.get_all_jobs()
        def _is_pune_or_remote(j):
            loc_txt = f"{j.get('location', '')} {j.get('title', '')}".lower()
            return any(p in loc_txt for p in ["pune", "remote", "work from home", "wfh"])

        ext_jobs = [
            j for j in all_jobs
            if j.get("status") == "queued_external"
            and j.get("match_score", 0) >= 70.0
        ]
        ext_jobs.sort(key=lambda x: (1 if _is_pune_or_remote(x) else 0, x.get("match_score", 0)), reverse=True)

        if not ext_jobs:
            self.notifier.send_message(
                "🌐 <b>No Pune or Remote external portal roles queued right now.</b>\n"
                "Run <b>/run</b> or <b>/search</b> to discover fresh postings.",
                chat_id=chat_id
            )
            return

        # Send rich message template cards with 100% clickable links directly in Telegram
        self.notifier.send_external_jobs_template(ext_jobs, chat_id=chat_id)

    def _cmd_history(self, chat_id: str) -> None:
        history_file = Path("reports") / "run_history.json"
        if not history_file.exists():
            self.notifier.send_message("📜 No run history recorded yet.", chat_id=chat_id)
            return

        try:
            with open(history_file, "r", encoding="utf-8") as f:
                runs = json.load(f)
        except Exception:
            runs = []

        if not runs:
            self.notifier.send_message("📜 No run history recorded yet.", chat_id=chat_id)
            return

        lines = ["📜 <b>Recent Autonomous Agent Runs:</b>\n"]
        for r in runs[-4:]:
            ts = r.get("timestamp", "")
            mode = r.get("mode", "auto").upper()
            dur = f"{r.get('runtime_minutes', 0):.1f}m"
            applied = r.get("applied_count", 0)
            status = "⏱️ Timed Out" if r.get("timed_out") else "✓ Done"
            lines.append(f"• <b>{ts}</b> [{mode}] — {dur} | Applied: <b>{applied}</b> ({status})")

        self.notifier.send_message("\n".join(lines), chat_id=chat_id)

    def _cmd_run_auto(self, chat_id: str, sub_arg: str = "") -> None:
        if not self.is_running_lock.acquire(blocking=False):
            elapsed = (time.time() - self.current_task_info["started_at"]) / 60.0
            self.notifier.send_message(
                f"⏳ <b>A job run is already active!</b>\nTask: <code>{self.current_task_info['command']}</code> (running for {elapsed:.1f}m).\nPlease wait until it completes.",
                chat_id=chat_id
            )
            return

        cmd_label = f"/run {sub_arg}".strip()
        self.current_task_info = {"active": True, "command": cmd_label, "started_at": time.time()}

        easy_apply_override = None
        if sub_arg in ["easy", "easy_apply", "easyapply"]:
            easy_apply_override = True
            mode_desc = "<b>Easy Apply Only</b>"
        elif sub_arg in ["external", "hybrid", "all"]:
            easy_apply_override = False
            mode_desc = "<b>Hybrid (Easy Apply + Queue External ATS)</b>"
        else:
            is_easy = self.settings.get("search_filters", {}).get("linkedin", {}).get("easy_apply_only", True)
            mode_desc = "<b>Easy Apply Only</b>" if is_easy else "<b>Hybrid (Easy Apply + External ATS)</b>"

        ack_msg = (
            f"🚀 <b>Starting Autonomous Job Hunting Run ({mode_desc})...</b>\n\n"
            "• Searching LinkedIn & Naukri (&lt;24h freshness)\n"
            "• Calculating 6-factor candidate match scores\n"
            "• Auto-applying with 📍 Pune & 🏡 Remote priority\n"
            "• Enforcing 30m precautionary safety timeout\n\n"
            "<i>I will post the complete audit summary here as soon as the run finishes.</i>"
        )
        self.notifier.send_message(ack_msg, chat_id=chat_id)

        def _worker():
            try:
                if self.run_agent_callback:
                    import inspect
                    sig = inspect.signature(self.run_agent_callback)
                    if "easy_apply_only" in sig.parameters or len(sig.parameters) > 0:
                        self.run_agent_callback(easy_apply_only=easy_apply_override)
                    else:
                        self.run_agent_callback()
                else:
                    from src.agent.autonomous_runner import AutonomousJobAgent
                    agent = AutonomousJobAgent(self.settings, self.db)
                    trig = "Easy Apply" if (easy_apply_override is True or (easy_apply_override is None and self.settings.get("search_filters", {}).get("linkedin", {}).get("easy_apply_only", True))) else "External Jobs"
                    agent.run_single_cycle(min_score=75.0, auto_apply=True, max_runtime_minutes=30.0, easy_apply_only=easy_apply_override, trigger_type=trig)
            except Exception as e:
                logger.error(f"Error executing Telegram-triggered auto run: {e}", exc_info=True)
                self.notifier.send_message(f"❌ <b>Autonomous Run Failed:</b> <code>{str(e)}</code>", chat_id=chat_id)
            finally:
                self.current_task_info = {"active": False, "command": None, "started_at": None}
                self.is_running_lock.release()

        t = threading.Thread(target=_worker, daemon=True, name="TelegramAutoRunner")
        t.start()

    def _cmd_run_apply(self, chat_id: str) -> None:
        if not self.is_running_lock.acquire(blocking=False):
            elapsed = (time.time() - self.current_task_info["started_at"]) / 60.0
            self.notifier.send_message(
                f"⏳ <b>A run is already in progress!</b>\nTask: <code>{self.current_task_info['command']}</code> ({elapsed:.1f}m elapsed).\nPlease wait.",
                chat_id=chat_id
            )
            return

        self.current_task_info = {"active": True, "command": "/apply", "started_at": time.time()}
        self.notifier.send_message(
            "🚀 <b>Starting Application Pass (Easy Apply Only)...</b>\nTargeting direct Easy Apply & Fast Apply jobs with 📍 Pune & 🏡 Remote prioritized.\nI will post the results when done.",
            chat_id=chat_id
        )

        def _worker():
            try:
                if self.run_apply_callback:
                    self.run_apply_callback()
                else:
                    from src.agent.autonomous_runner import AutonomousJobAgent
                    agent = AutonomousJobAgent(self.settings, self.db)
                    agent.run_single_cycle(min_score=70.0, auto_apply=True, max_runtime_minutes=30.0, easy_apply_only=True, trigger_type="Easy Apply")
            except Exception as e:
                logger.error(f"Error executing Telegram-triggered apply run: {e}", exc_info=True)
                self.notifier.send_message(f"❌ <b>Application Run Failed:</b> <code>{str(e)}</code>", chat_id=chat_id)
            finally:
                self.current_task_info = {"active": False, "command": None, "started_at": None}
                self.is_running_lock.release()

        t = threading.Thread(target=_worker, daemon=True, name="TelegramApplier")
        t.start()

    def _cmd_run_search(self, chat_id: str, sub_arg: str = "") -> None:
        if not self.is_running_lock.acquire(blocking=False):
            self.notifier.send_message("⏳ A job run is currently active. Please wait.", chat_id=chat_id)
            return

        cmd_label = f"/search {sub_arg}".strip()
        self.current_task_info = {"active": True, "command": cmd_label, "started_at": time.time()}

        easy_apply_override = None
        if sub_arg in ["easy", "easy_apply", "easyapply"]:
            easy_apply_override = True
        elif sub_arg in ["external", "hybrid", "all"]:
            easy_apply_override = False

        self.notifier.send_message("🔍 <b>Searching for fresh (&lt;24h) SDET opportunities on LinkedIn & Naukri...</b>", chat_id=chat_id)

        def _worker():
            try:
                if self.run_search_callback:
                    self.run_search_callback()
                else:
                    from src.agent.autonomous_runner import AutonomousJobAgent
                    agent = AutonomousJobAgent(self.settings, self.db)
                    agent.run_single_cycle(min_score=75.0, auto_apply=False, max_runtime_minutes=20.0, easy_apply_only=easy_apply_override)
            except Exception as e:
                logger.error(f"Error executing Telegram-triggered search: {e}", exc_info=True)
                self.notifier.send_message(f"❌ <b>Search Failed:</b> <code>{str(e)}</code>", chat_id=chat_id)
            finally:
                self.current_task_info = {"active": False, "command": None, "started_at": None}
                self.is_running_lock.release()

        t = threading.Thread(target=_worker, daemon=True, name="TelegramSearcher")
        t.start()

    def poll_updates_once(self) -> None:
        """
        Queries Telegram getUpdates with an offset and processes new commands.
        """
        if not self.bot_token:
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates?timeout=15"
        if self.last_update_id > 0:
            url += f"&offset={self.last_update_id + 1}"

        try:
            res = _make_request(url, timeout=20)
            if not res.get("ok"):
                return

            updates = res.get("result", [])
            for u in updates:
                uid = u.get("update_id", 0)
                if uid > self.last_update_id:
                    self.last_update_id = uid

                # Check channel_post
                if "channel_post" in u:
                    cp = u["channel_post"]
                    chat_id = str(cp.get("chat", {}).get("id", ""))
                    sender = cp.get("author_signature", "Channel Admin")
                    text = cp.get("text", "")
                    if self.is_authorized(chat_id, user_id=None) and text.startswith("/"):
                        self.handle_command(text, chat_id, sender_name=sender)

                # Check private message / direct message
                if "message" in u:
                    msg = u["message"]
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    from_user = msg.get("from", {})
                    user_id = from_user.get("id")
                    sender = from_user.get("first_name", "User")
                    text = msg.get("text", "")
                    if self.is_authorized(chat_id, user_id=user_id) and text.startswith("/"):
                        self.handle_command(text, chat_id, sender_name=sender)

        except Exception as e:
            logger.debug(f"Polling check: {e}")

    def start_polling(self, poll_interval: float = 2.0) -> None:
        """
        Runs continuous long polling loop until stop() is called.
        """
        logger.info("Telegram command listener started. Listening for commands...")
        while not self.stop_event.is_set():
            self.poll_updates_once()
            self.stop_event.wait(poll_interval)
        logger.info("Telegram command listener stopped.")

    def stop(self) -> None:
        """Stops the polling loop."""
        self.stop_event.set()
