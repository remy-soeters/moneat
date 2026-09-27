"""Instellingen: AI-keuzes, modellen, API-sleutels en achtergrondtaken. Wijzigen kan alleen een beheerder."""

import os
import re
from datetime import datetime, timezone
from http import HTTPStatus

from .. import ai, gemini, setting_keys
from ..actions import describe_action
from ..preloader import PRELOAD_OPTIONS
from ..web import ApiError

KEY_SETTINGS = {
    "claude": setting_keys.CLAUDE_KEY,
    "gemini": setting_keys.GEMINI_KEY,
    "gemini_text": setting_keys.GEMINI_TEXT_KEY,
}
KEY_PATTERNS = {
    "claude": (r"sk-ant-[A-Za-z0-9_\-]{20,200}", "Dit lijkt geen Anthropic API-sleutel. Die begint met ‘sk-ant-’ en is lang."),
    # Google gebruikt zowel het oude formaat (AIza…) als het nieuwere met een punt (AQ.…).
    "gemini": (r"[A-Za-z0-9_.\-]{30,200}", "Dit lijkt geen Gemini API-sleutel. Kopieer hem volledig uit Google AI Studio."),
}
KEY_PATTERNS["gemini_text"] = KEY_PATTERNS["gemini"]
MODEL_NAME = re.compile(r"[a-z0-9][a-z0-9.\-]{2,80}")


def utc_time(value):
    """Een tijdstip uit de browser (ISO) zoals SQLite het bewaart (UTC); onleesbaar = None (nu)."""
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def mask_key(key):
    """Laat alleen het begin en eind van een sleutel zien: sk-ant-…a1b2."""
    return f"{key[:7]}…{key[-4:]}"


def register(r, app):
    db, preloader = app.db, app.preloader

    def full_settings():
        claude_key = db.get_setting(setting_keys.CLAUDE_KEY)
        gemini_key = db.get_setting(setting_keys.GEMINI_KEY)
        text_key = db.get_setting(setting_keys.GEMINI_TEXT_KEY)
        text_model, image_model = ai.gemini_models()
        return {
            "is_admin": True,
            "sdk_installed": ai.sdk_installed(),
            "text_provider": ai.text_provider(),
            "gemini_plan": ai.gemini_plan(),
            "swipe_preload": app.preload_target(),
            "swipe_preload_options": list(PRELOAD_OPTIONS),
            "auto_images": db.get_setting(setting_keys.AUTO_IMAGES) != "off",
            "claude": {
                "set": bool(claude_key),
                "hint": mask_key(claude_key) if claude_key else None,
                "env": ai.env_key_present(),
                "model": ai.claude_model()["id"],
                # Welk model er nu achter zit (het nieuwste van de familie; bijgewerkt als Claude iets doet)
                "current": ai.latest_claude_model()["name"],
                "models": [{k: m[k] for k in ("id", "name", "note")} for m in ai.CLAUDE_MODELS],
            },
            "gemini": {
                "set": bool(gemini_key),
                "hint": mask_key(gemini_key) if gemini_key else None,
                "env": bool(os.environ.get("GEMINI_API_KEY")),
                "text_model": text_model,
                "image_model": image_model,
                "default_text_model": gemini.DEFAULT_TEXT_MODEL,
                "default_image_model": gemini.DEFAULT_IMAGE_MODEL,
                "image_models": gemini.IMAGE_MODELS,
                "text_models": gemini.TEXT_MODELS,
                "text_key": {"set": bool(text_key), "hint": mask_key(text_key) if text_key else None},
            },
        }

    @r.get("/api/settings")
    def get_settings(req):
        if req.user["is_admin"]:
            return full_settings()
        # Gewone leden zien alleen wat de app nodig heeft; sleutels en kosten zijn voor de beheerder.
        return {"is_admin": False, "text_provider": ai.text_provider()}

    @r.put("/api/settings", admin=True)
    def save_settings(req):
        body = req.json()
        for provider, setting in KEY_SETTINGS.items():
            field = f"{provider}_api_key"
            if field in body:
                key = str(body.get(field) or "").strip()
                pattern, message = KEY_PATTERNS[provider]
                if not re.fullmatch(pattern, key):
                    raise ApiError(HTTPStatus.BAD_REQUEST, message)
                db.set_setting(setting, key)
        if "swipe_preload" in body:
            if int(body["swipe_preload"]) not in PRELOAD_OPTIONS:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Kies 5, 10, 15 of 20 gerechten")
            db.set_setting(setting_keys.SWIPE_PRELOAD, str(int(body["swipe_preload"])))
            preloader.kick()
        if "auto_images" in body:
            db.set_setting(setting_keys.AUTO_IMAGES, None if body["auto_images"] else "off")
            preloader.kick()
        if "claude_model" in body:
            if body["claude_model"] not in {m["id"] for m in ai.CLAUDE_MODELS}:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Kies Sonnet of Haiku")
            db.set_setting(setting_keys.CLAUDE_MODEL, body["claude_model"])
        if "text_provider" in body:
            if body["text_provider"] not in ("claude", "gemini"):
                raise ApiError(HTTPStatus.BAD_REQUEST, "Kies Claude of Gemini")
            db.set_setting(setting_keys.TEXT_PROVIDER, body["text_provider"])
        if "gemini_plan" in body:
            if body["gemini_plan"] not in ("free", "paid"):
                raise ApiError(HTTPStatus.BAD_REQUEST, "Kies gratis of betaald")
            db.set_setting(setting_keys.GEMINI_PLAN, body["gemini_plan"])
        for field, setting in (
            ("gemini_text_model", setting_keys.GEMINI_TEXT_MODEL),
            ("gemini_image_model", setting_keys.GEMINI_IMAGE_MODEL),
        ):
            if field in body:
                model = str(body.get(field) or "").strip()
                if model and not MODEL_NAME.fullmatch(model):
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"Ongeldige modelnaam: {model[:80]}")
                db.set_setting(setting, model or None)  # leeg = standaardmodel
        return full_settings()

    @r.delete(r"/api/settings/key/(claude|gemini_text|gemini)", admin=True)
    def delete_key(req, provider):
        db.set_setting(KEY_SETTINGS[provider], None)
        return full_settings()

    @r.post("/api/settings/test", admin=True)
    def test_connection(req):
        if req.json().get("provider") in ("gemini", "gemini_text"):
            ai.check_gemini()
            text_model, image_model = ai.gemini_models()
            return {"ok": True, "message": f"Verbinding met Gemini werkt ({text_model}, {image_model})."}
        ai.check_connection()
        return {"ok": True, "message": f"Verbinding met Claude werkt ({ai.latest_claude_model()['name']})."}

    # ---------- foutmeldingen ----------

    @r.get("/api/usage", admin=True)
    def usage(req):
        """Verbruik van de AI per dag en per doel (Instellingen → Slimme hulp → Foto's en icoontjes)."""
        days = max(1, min(int(req.query.get("days") or 30), 120))
        return db.ai_usage_report(days)

    @r.get("/api/errors", admin=True)
    def get_errors(req):
        return {"errors": db.recent_errors()}

    @r.post("/api/errors")
    def browser_errors(req):
        """Fouten die de browser zag maar de server niet, zoals geen verbinding of een time-out onderweg.
        De browser stuurt ze zodra het weer lukt: [{method, path, message, detail, at}]."""
        entries = req.json().get("errors")
        if not isinstance(entries, list):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Verwacht een lijst met fouten")
        for entry in entries[:20]:
            if isinstance(entry, dict) and entry.get("message"):
                app.log_error(
                    "Browser",
                    describe_action(str(entry.get("method") or "")[:10], str(entry.get("path") or "").split("?")[0][:200]),
                    str(entry["message"])[:500],
                    str(entry.get("detail") or "")[:500],
                    req.user["display_name"],
                    utc_time(entry.get("at")),
                )
        return {"ok": True}

    @r.delete("/api/errors", admin=True)
    def clear_errors(req):
        db.clear_errors()
        return {"ok": True}

    @r.get("/api/health", auth=False)
    def health(req):
        return {"ok": True}
