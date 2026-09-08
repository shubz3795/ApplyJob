import json
import ssl
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple
from src.utils.logger import get_logger

logger = get_logger("TelegramNotifier")

try:
    import certifi
    _DEFAULT_SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _DEFAULT_SSL_CTX = ssl._create_unverified_context()

def _make_request(url: str, data: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None, timeout: int = 15) -> Dict[str, Any]:
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, context=_DEFAULT_SSL_CTX, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        # Fallback to unverified SSL context in case of self-signed cert chain or corporate proxy
        try:
            unverified_ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, context=unverified_ctx, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            raise e

class TelegramNotifier:
    """
    Sends automated, rich notifications to a private Telegram channel
    after every autonomous agent run or application batch.
    """

    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings
        tg_config = settings.get("telegram", {})
        self.enabled = tg_config.get("enabled", False)
        self.bot_token = tg_config.get("bot_token", "").strip()
        self.chat_id = str(tg_config.get("chat_id", "")).strip()
        self.notify_only_if_applied = tg_config.get("notify_only_if_applied", False)

    def is_configured(self) -> bool:
        return bool(self.enabled and self.bot_token and self.chat_id)

    def send_message(self, text: str, parse_mode: str = "HTML", chat_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Sends an HTML or Markdown message to the configured Telegram chat/channel.
        Splits automatically if message exceeds 4000 characters.
        """
        target_chat_id = str(chat_id).strip() if chat_id else self.chat_id
        if not self.bot_token:
            return False, "Telegram bot token not configured"
        if not target_chat_id:
            return False, "Telegram chat ID not configured"

        # Split message if exceeds limit (Telegram max is 4096 chars)
        chunks = self._chunk_message(text, max_len=4000)
        all_success = True
        last_error = ""

        for chunk in chunks:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": target_chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            data = json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            try:
                res_body = _make_request(url, data=data, headers=headers, timeout=15)
                if not res_body.get("ok"):
                    all_success = False
                    last_error = res_body.get("description", "Unknown Telegram API error")
            except Exception as e:
                all_success = False
                last_error = str(e)
                logger.error(f"Failed to send Telegram message: {e}")
            except Exception as e:
                all_success = False
                last_error = str(e)
                logger.error(f"Failed to send Telegram message: {e}")

        if all_success:
            return True, "Telegram notification delivered successfully"
        return False, f"Telegram delivery failed: {last_error}"

    def send_document(
        self,
        file_path: Any,
        caption: Optional[str] = None,
        chat_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Uploads and sends a file document (e.g. EXTERNAL_JOBS.md) to Telegram.
        """
        from pathlib import Path
        target_chat_id = str(chat_id).strip() if chat_id else self.chat_id
        if not self.bot_token:
            return False, "Telegram bot token not configured"
        if not target_chat_id:
            return False, "Telegram chat ID not configured"

        p = Path(file_path)
        if not p.exists():
            return False, f"File not found: {file_path}"

        url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"
        try:
            import requests
            with open(p, "rb") as f:
                mime = "text/markdown" if p.suffix == ".md" else "application/octet-stream"
                files = {"document": (p.name, f, mime)}
                data = {"chat_id": target_chat_id}
                if caption:
                    data["caption"] = caption
                    data["parse_mode"] = "HTML"
                resp = requests.post(url, data=data, files=files, timeout=30)
                res_data = resp.json()
                if res_data.get("ok"):
                    return True, "Document delivered successfully"
                return False, res_data.get("description", "Unknown Telegram API error")
        except Exception as e:
            logger.error(f"Failed to send Telegram document {p.name}: {e}")
            return False, str(e)

    def format_external_jobs_template(self, jobs: List[Dict[str, Any]]) -> str:
        """
        Formats high-match Pune & Remote external portal jobs as rich mobile message cards
        with prominent 1-tap clickable links (no .md attachment needed).
        """
        if not jobs:
            return "🌐 <b>No high-match Pune or Remote external roles currently queued.</b>"

        lines = [
            f"🌐 <b>1-Click External Portal Roles ({len(jobs)} Positions)</b>",
            "🎯 <i>Location Filter: Strictly 📍 Pune & 🏡 Remote Only (≥70% Match)</i>",
            "<i>Tap any link below to apply directly on the company portal:</i>\n"
        ]

        for i, j in enumerate(jobs, 1):
            comp = self._escape_html(j.get("company", "Company"))
            titl = self._escape_html(j.get("title", "Job Title"))
            sc = j.get("match_score", 0)
            u = j.get("url", "")
            loc = j.get("location", "")
            loc_badge = "📍 Pune" if "pune" in loc.lower() else ("🏡 Remote" if any(r in loc.lower() for r in ["remote", "wfh", "work from home"]) else loc)
            notes = self._escape_html(j.get("skip_reason", "")[:60])

            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"<b>{i}. {comp}</b>  •  <b>{sc:.1f}% Match</b>")
            lines.append(f"💼 <b>{titl}</b>")
            lines.append(f"📍 <i>{self._escape_html(loc_badge)}</i>")
            if notes:
                lines.append(f"⚡ <code>{notes}</code>")
            if u:
                lines.append(f"🔗 <a href=\"{u}\">👉 <b>TAP TO APPLY ON {comp.upper()} PORTAL</b></a>")
                lines.append(f"🌐 <i>Direct URL:</i> {u}")
            else:
                lines.append("<i>No apply URL available</i>")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    def send_external_jobs_template(self, jobs: List[Dict[str, Any]], chat_id: Optional[str] = None) -> Tuple[bool, str]:
        text = self.format_external_jobs_template(jobs)
        return self.send_message(text, parse_mode="HTML", chat_id=chat_id)

    def send_run_summary(
        self,
        run_meta: Dict[str, Any],
        applied_in_this_run: List[Dict[str, Any]],
        top_todo: Optional[List[Dict[str, Any]]] = None,
        external_jobs: Optional[List[Dict[str, Any]]] = None,
        send_external_template: bool = False
    ) -> Tuple[bool, str]:
        """
        Formats and sends a comprehensive, clean run summary to the Telegram channel.
        In Easy Apply mode, external roles are NEVER sent or rendered.
        In External mode, external roles can be sent as rich message template cards.
        """
        if not self.is_configured():
            return False, "Telegram notifications are disabled or not configured"

        if self.notify_only_if_applied and not applied_in_this_run:
            logger.info("Skipping Telegram notification: notify_only_if_applied is True and no applications were submitted.")
            return True, "Skipped (no applications submitted)"

        trigger_type = run_meta.get("trigger_type", "")
        is_easy_mode = "easy" in trigger_type.lower() if trigger_type else (run_meta.get("mode", "").lower() in ["apply", "easy", "auto"])

        # In Easy Apply mode, strictly suppress external jobs
        ext_jobs_to_render = None if is_easy_mode else external_jobs
        text = self.format_run_message(run_meta, applied_in_this_run, top_todo or [], external_jobs=ext_jobs_to_render)
        sent, msg = self.send_message(text, parse_mode="HTML")

        # Deliver external roles as message cards ONLY if NOT easy apply mode and explicitly enabled
        if not is_easy_mode and send_external_template and external_jobs:
            ext_text = self.format_external_jobs_template(external_jobs[:6])
            self.send_message(ext_text, parse_mode="HTML")

        return sent, msg

    def format_run_message(
        self,
        run_meta: Dict[str, Any],
        applied_in_this_run: List[Dict[str, Any]],
        top_todo: List[Dict[str, Any]],
        external_jobs: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Generates a clean, trigger-wise HTML Telegram notification.
        """
        trigger_type = run_meta.get("trigger_type")
        if not trigger_type:
            mode = run_meta.get("mode", "auto").lower()
            if "external" in mode:
                trigger_type = "External Jobs"
            elif mode in ["apply", "easy", "auto"]:
                trigger_type = "Easy Apply"
            else:
                trigger_type = mode.capitalize()

        li_applied = sum(1 for j in applied_in_this_run if j.get("platform", "").lower() == "linkedin")
        nk_applied = sum(1 for j in applied_in_this_run if j.get("platform", "").lower() == "naukri")
        total_applied = len(applied_in_this_run)

        ts = run_meta.get("timestamp_str", "Just Now")
        duration = run_meta.get("runtime_minutes", 0.0)
        timed_out = run_meta.get("timed_out", False)
        status_tag = "⏱️ <b>Precautionary Timeout</b>" if timed_out else "✅ <b>Completed</b>"

        lines = [
            "🚀 <b>SDET Job Hunt Summary</b>",
            "",
            f"<b>Trigger type:</b> {self._escape_html(trigger_type)}",
            f"<b>Jobs applied in this run:</b> <b>{total_applied}</b>",
            f"• <b>Applied from LinkedIn:</b> <b>{li_applied}</b>",
            f"• <b>Applied from Naukri:</b> <b>{nk_applied}</b>",
            f"• <b>Duration:</b> {duration:.1f} mins ({status_tag})",
            ""
        ]

        # Section 1: Applied in this run
        if applied_in_this_run:
            lines.append(f"<b>✅ Applications Submitted in This Run ({total_applied}):</b>")
            for idx, item in enumerate(applied_in_this_run, 1):
                company = self._escape_html(item.get("company", "Company"))
                title = self._escape_html(item.get("title", "Job Title"))
                platform = item.get("platform", "").capitalize()
                score = item.get("match_score", 0)
                url = item.get("url", "")
                loc = item.get("location", "")
                loc_badge = "📍 Pune" if "pune" in loc.lower() else ("🏡 Remote" if any(r in loc.lower() for r in ["remote", "wfh", "work from home"]) else loc)
                link_text = f"<a href=\"{url}\">{company}</a>" if url else f"<b>{company}</b>"
                lines.append(f"{idx}. {link_text} — {title} (<b>{score:.1f}%</b>) [{platform}] <i>{self._escape_html(loc_badge)}</i>")
                if url:
                    lines.append(f"   🔗 Direct Link: {url}")
            lines.append("")
        else:
            lines.append("<i>No new applications submitted in this run.</i>")
            lines.append("")

        # Section 2: Daily Safety Quotas
        li_today = run_meta.get("li_today", 0)
        nk_today = run_meta.get("nk_today", 0)
        lines.append("<b>🛡️ Daily Safety Quotas Today:</b>")
        lines.append(f"• <b>LinkedIn:</b> {li_today} / 50 applied ({max(0, 50 - li_today)} left)")
        lines.append(f"• <b>Naukri:</b> {nk_today} / 50 applied ({max(0, 50 - nk_today)} left)")
        lines.append("")

        is_easy_mode = "easy" in trigger_type.lower()
        if is_easy_mode:
            # Section 3 for Easy Apply: Next direct Easy Apply jobs in queue (Pune & Remote prioritized)
            if top_todo:
                lines.append("<b>⏳ Next Easy Apply Jobs in Queue (📍 Pune & 🏡 Remote Prioritized):</b>")
                for j in top_todo[:6]:
                    comp = self._escape_html(j.get("company", "Company"))
                    titl = self._escape_html(j.get("title", "Job Title"))
                    plat = j.get("platform", "").capitalize()
                    sc = j.get("match_score", 0)
                    u = j.get("url", "")
                    loc = j.get("location", "")
                    loc_badge = "📍 Pune" if "pune" in loc.lower() else ("🏡 Remote" if any(r in loc.lower() for r in ["remote", "wfh", "work from home"]) else loc)
                    link_txt = f"<a href=\"{u}\">{comp}</a>" if u else f"<b>{comp}</b>"
                    lines.append(f"• {link_txt} — {titl} (<b>{sc:.1f}%</b>) [{plat}] <i>{self._escape_html(loc_badge)}</i>")
                if len(top_todo) > 6:
                    lines.append(f"<i>...and {len(top_todo) - 6} more high-match roles queued.</i>")
                lines.append("")
        else:
            # Section 3 for External mode: External portal roles
            if external_jobs:
                lines.append("<b>🌐 Top External Portal Roles (📍 Pune & 🏡 Remote 1-Click Apply):</b>")
                for j in external_jobs[:5]:
                    comp = self._escape_html(j.get("company", "Company"))
                    titl = self._escape_html(j.get("title", "Job Title"))
                    sc = j.get("match_score", 0)
                    u = j.get("url", "")
                    loc = j.get("location", "")
                    loc_badge = "📍 Pune" if "pune" in loc.lower() else ("🏡 Remote" if any(r in loc.lower() for r in ["remote", "wfh", "work from home"]) else loc)
                    link_txt = f"<a href=\"{u}\">{comp}</a>" if u else f"<b>{comp}</b>"
                    lines.append(f"• {link_txt} — {titl} (<b>{sc:.1f}%</b>) <i>{self._escape_html(loc_badge)}</i>")
                    if u:
                        lines.append(f"  👉 <b>Apply:</b> {u}")
                if len(external_jobs) > 5:
                    lines.append(f"<i>...and {len(external_jobs) - 5} more roles. Send /external to view all cards.</i>")
                lines.append("")

        return "\n".join(lines).strip()

    @staticmethod
    def detect_channel_chat_id(bot_token: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Queries Telegram getUpdates to automatically detect the channel ID where
        the bot was added as an administrator or posted to.
        Returns (chat_id, title) if found.
        """
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        try:
            data = _make_request(url, timeout=10)
            if not data.get("ok"):
                return None, None
            updates = data.get("result", [])
            for u in reversed(updates):
                # Check channel_post
                if "channel_post" in u:
                    chat = u["channel_post"].get("chat", {})
                    return str(chat.get("id")), chat.get("title")
                # Check my_chat_member
                if "my_chat_member" in u:
                    chat = u["my_chat_member"].get("chat", {})
                    if chat.get("type") in ["channel", "supergroup"]:
                        return str(chat.get("id")), chat.get("title")
                # Check message
                if "message" in u:
                    chat = u["message"].get("chat", {})
                    return str(chat.get("id")), chat.get("title")
        except Exception as e:
            logger.error(f"Error checking Telegram updates: {e}")
        return None, None

    @staticmethod
    def _chunk_message(text: str, max_len: int = 4000) -> List[str]:
        if len(text) <= max_len:
            return [text]
        chunks = []
        lines = text.split("\n")
        curr = []
        curr_len = 0
        for line in lines:
            if curr_len + len(line) + 1 > max_len:
                chunks.append("\n".join(curr))
                curr = [line]
                curr_len = len(line) + 1
            else:
                curr.append(line)
                curr_len += len(line) + 1
        if curr:
            chunks.append("\n".join(curr))
        return chunks

    @staticmethod
    def _escape_html(text: str) -> str:
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
