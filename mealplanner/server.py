"""HTTP-server: JSON-API onder /api en de frontend uit /static."""

import argparse
import errno
import json
import mimetypes
import os
import re
import tempfile
import time
import traceback
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import ai, gemini
from .db import Database, NotFound
from .images import MAX_IMAGE_BYTES, ImageStore
from .importer import ImportFailed, import_recipe
from .preloader import DEFAULT_PRELOAD, PRELOAD_OPTIONS, SwipePreloader

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
DEFAULT_DB = ROOT / "data" / "mealplanner.db"
MAX_BODY = 1_000_000


KEY_SETTINGS = {"claude": ai.CLAUDE_KEY, "gemini": ai.GEMINI_KEY}
KEY_PATTERNS = {
    "claude": (r"sk-ant-[A-Za-z0-9_\-]{20,}", "Dit lijkt geen Anthropic API-sleutel. Die begint met ‘sk-ant-’ en is lang."),
    # Google gebruikt zowel het oude formaat (AIza…) als het nieuwere met een punt (AQ.…).
    "gemini": (r"[A-Za-z0-9_.\-]{30,}", "Dit lijkt geen Gemini API-sleutel. Kopieer hem volledig uit Google AI Studio."),
}


PREFERENCES_SETTING = "food_preferences"
SWIPE_PRELOAD_SETTING = "swipe_preload"
MAX_MINUTES = (None, 20, 30, 45, 60)


def clean_preferences(data):
    """Controleer de voedselvoorkeuren uit het swipe-formulier."""
    diet = data.get("diet") or "alles"
    if diet not in ai.DIETS:
        raise ValueError(f"Onbekend dieet: {diet}")
    cuisines = data.get("cuisines") or []
    if not isinstance(cuisines, list) or len(cuisines) > 12:
        raise ValueError("Kies maximaal 12 keukens")
    cuisines = [str(c).strip()[:30] for c in cuisines if str(c).strip()]
    max_minutes = data.get("max_minutes") or None
    if max_minutes is not None:
        max_minutes = int(max_minutes)
    if max_minutes not in MAX_MINUTES:
        raise ValueError("Kies 20, 30, 45 of 60 minuten, of geen maximum")
    return {
        "diet": diet,
        "cuisines": cuisines,
        "max_minutes": max_minutes,
        "avoid": str(data.get("avoid") or "").strip()[:200],
    }


def inspiration_key(theme, servings):
    return f"{str(theme or '').strip().lower()}|{int(servings or 2)}"


def mask_key(key):
    """Laat alleen het begin en eind van een sleutel zien: sk-ant-…a1b2."""
    return f"{key[:7]}…{key[-4:]}"


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def make_handler(db, images=None):
    images = images or ImageStore(tempfile.mkdtemp(prefix="mealplanner-images-"))

    ai.set_settings(db.get_setting)

    def load_preferences():
        try:
            return json.loads(db.get_setting(PREFERENCES_SETTING) or "{}")
        except ValueError:
            return {}

    def release_image(url):
        """Verwijder een foto van schijf zodra geen recept of voorstel hem meer gebruikt."""
        if url and not db.image_in_use(url):
            images.delete(url)

    def preload_target():
        try:
            value = int(db.get_setting(SWIPE_PRELOAD_SETTING) or DEFAULT_PRELOAD)
        except ValueError:
            value = DEFAULT_PRELOAD
        return value if value in PRELOAD_OPTIONS else DEFAULT_PRELOAD

    preloader = SwipePreloader(db, images, release_image, load_preferences, preload_target)

    class Handler(BaseHTTPRequestHandler):
        server_version = "mealplanner/0.1"

        # ---------- routering ----------

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):
            self._dispatch("PUT")

        def do_DELETE(self):
            self._dispatch("DELETE")

        def _dispatch(self, method):
            url = urlparse(self.path)
            if not url.path.startswith("/api/"):
                if method == "GET" and url.path.startswith("/images/"):
                    return self._serve_image(url.path)
                if method == "GET":
                    return self._serve_static(url.path)
                return self._send_json({"error": "Niet gevonden"}, HTTPStatus.NOT_FOUND)

            query = {k: v[-1] for k, v in parse_qs(url.query).items()}
            try:
                for route_method, pattern, action in ROUTES:
                    match = pattern.fullmatch(url.path)
                    if match and route_method == method:
                        result = action(self, query, *match.groups())
                        return self._send_json(result, HTTPStatus.OK)
                raise ApiError(HTTPStatus.NOT_FOUND, "Onbekend API-pad")
            except ApiError as e:
                self._send_json({"error": str(e)}, e.status)
            except NotFound as e:
                self._send_json({"error": str(e)}, HTTPStatus.NOT_FOUND)
            except ValueError as e:
                self._send_json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
            except ai.AIUnavailable as e:
                self._send_json({"error": str(e)}, HTTPStatus.SERVICE_UNAVAILABLE)
            except ImportFailed as e:
                self._send_json({"error": str(e)}, HTTPStatus.UNPROCESSABLE_ENTITY)
            except Exception:
                traceback.print_exc()
                self._send_json({"error": "Interne serverfout"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        # ---------- recepten ----------

        def list_recipes(self, query):
            return db.list_recipes()

        def create_recipe(self, query):
            return db.create_recipe(self._body())

        def get_recipe(self, query, recipe_id):
            return db.get_recipe(int(recipe_id))

        def update_recipe(self, query, recipe_id):
            old_image = db.get_recipe(int(recipe_id))["image"]
            recipe = db.update_recipe(int(recipe_id), self._body())
            if old_image != recipe["image"]:
                release_image(old_image)
            return recipe

        def delete_recipe(self, query, recipe_id):
            image = db.get_recipe(int(recipe_id))["image"]
            db.delete_recipe(int(recipe_id))
            release_image(image)
            return {"ok": True}

        def import_recipe(self, query):
            url = str(self._body().get("url") or "").strip()
            if not url:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Plak eerst een link naar een recept")
            if "://" not in url:
                url = "https://" + url
            return import_recipe(url, images, ai_extract=ai.extract_recipe)

        def generate_recipe(self, query):
            body = self._body()
            request = str(body.get("prompt") or "").strip()
            if not request:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Beschrijf eerst wat je wilt maken")
            return ai.generate_recipe(request, int(body.get("servings") or 2))

        def upload_image(self, query):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_IMAGE_BYTES:
                raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "De afbeelding is te groot (maximaal 8 MB)")
            return {"image": images.save(self.rfile.read(length))}

        # ---------- instellingen ----------

        def get_settings(self, query):
            claude_key = db.get_setting(ai.CLAUDE_KEY)
            gemini_key = db.get_setting(ai.GEMINI_KEY)
            text_model, image_model = ai.gemini_models()
            return {
                "sdk_installed": ai.sdk_installed(),
                "text_provider": ai.text_provider(),
                "swipe_preload": preload_target(),
                "swipe_preload_options": list(PRELOAD_OPTIONS),
                "claude": {
                    "set": bool(claude_key),
                    "hint": mask_key(claude_key) if claude_key else None,
                    "env": ai.env_key_present(),
                    "model": ai.MODEL,
                },
                "gemini": {
                    "set": bool(gemini_key),
                    "hint": mask_key(gemini_key) if gemini_key else None,
                    "env": bool(os.environ.get("GEMINI_API_KEY")),
                    "text_model": text_model,
                    "image_model": image_model,
                    "default_text_model": gemini.DEFAULT_TEXT_MODEL,
                    "default_image_model": gemini.DEFAULT_IMAGE_MODEL,
                },
            }

        def save_settings(self, query):
            body = self._body()
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
                db.set_setting(SWIPE_PRELOAD_SETTING, str(int(body["swipe_preload"])))
                preloader.kick()
            if "text_provider" in body:
                if body["text_provider"] not in ("claude", "gemini"):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Kies Claude of Gemini")
                db.set_setting(ai.TEXT_PROVIDER, body["text_provider"])
            for field, setting in (("gemini_text_model", ai.GEMINI_TEXT_MODEL), ("gemini_image_model", ai.GEMINI_IMAGE_MODEL)):
                if field in body:
                    model = str(body.get(field) or "").strip()
                    if model and not re.fullmatch(r"[a-z0-9][a-z0-9.\-]{2,80}", model):
                        raise ApiError(HTTPStatus.BAD_REQUEST, f"Ongeldige modelnaam: {model}")
                    db.set_setting(setting, model or None)  # leeg = standaardmodel
            return self.get_settings(query)

        def delete_key(self, query, provider):
            db.set_setting(KEY_SETTINGS[provider], None)
            return self.get_settings(query)

        def test_connection(self, query):
            if self._body().get("provider") == "gemini":
                ai.check_gemini()
                text_model, image_model = ai.gemini_models()
                return {"ok": True, "message": f"Verbinding met Gemini werkt ({text_model}, {image_model})."}
            ai.check_connection()
            return {"ok": True, "message": f"Verbinding met Claude werkt ({ai.MODEL})."}

        # ---------- foto's maken ----------

        def photo_for_draft(self, query):
            recipe = self._body().get("recipe") or {}
            if not str(recipe.get("name") or "").strip():
                raise ApiError(HTTPStatus.BAD_REQUEST, "Geef het recept eerst een naam")
            return {"image": images.save(ai.generate_photo(recipe))}

        def photo_for_recipe(self, query, recipe_id):
            recipe = db.get_recipe(int(recipe_id))
            old_image = recipe["image"]
            recipe["image"] = images.save(ai.generate_photo(recipe))
            recipe = db.update_recipe(recipe["id"], recipe)
            release_image(old_image)
            return recipe

        def photo_for_idea(self, query):
            body = self._body()
            key = inspiration_key(body.get("theme"), body.get("servings"))
            collection = db.get_inspiration(key)
            index = int(body.get("index", -1))
            if not collection or not 0 <= index < len(collection["ideas"]):
                raise ApiError(HTTPStatus.NOT_FOUND, "Dit idee bestaat niet (meer); laad de inspiratie opnieuw")
            recipe = collection["ideas"][index]["recipe"]
            old_image = recipe.get("image")
            recipe["image"] = images.save(ai.generate_photo(recipe))
            collection.pop("created_at", None)
            db.save_inspiration(key, collection)
            release_image(old_image)
            return {"image": recipe["image"]}

        # ---------- swipen ----------

        def get_preferences(self, query):
            return load_preferences()

        def save_preferences(self, query):
            prefs = clean_preferences(self._body())
            db.set_setting(PREFERENCES_SETTING, json.dumps(prefs, ensure_ascii=False))
            preloader.kick()
            return prefs

        def get_swipe(self, query):
            return {
                "cards": db.pending_swipe_cards(),
                "stats": db.swipe_stats(),
                "preferences": load_preferences(),
                "preload": preloader.status(),
            }

        def preload_swipe(self, query):
            body = self._body()
            preloader.kick(body.get("servings"), retry=bool(body.get("retry")))
            return preloader.status()

        def more_swipe_cards(self, query):
            body = self._body()
            count = max(1, min(int(body.get("count") or 8), 12))
            ideas = ai.swipe_recipes(
                load_preferences(), count, exclude=db.known_dish_names(), servings=int(body.get("servings") or 2)
            )
            added = db.add_swipe_cards(ideas)
            return {"added": added, "cards": db.pending_swipe_cards()}

        def swipe_card_photo(self, query, card_id):
            card = db.get_swipe_card(int(card_id))
            image = images.save(ai.generate_photo(card["recipe"]))
            db.set_swipe_card_image(card["id"], image)
            release_image(card["image"])
            return {"image": image}

        def swipe_card(self, query, card_id):
            recipe = db.swipe(int(card_id), bool(self._body().get("liked")))
            preloader.kick()  # voorraad weer aanvullen
            return {"recipe": recipe, "stats": db.swipe_stats()}

        def clear_swipe_cards(self, query):
            for image in db.clear_pending_swipe_cards():
                release_image(image)
            preloader.kick()
            return {"ok": True}

        def undo_swipe(self, query):
            return {"card": db.undo_swipe(), "stats": db.swipe_stats()}

        # ---------- inspiratie ----------

        def inspiration(self, query):
            body = self._body()
            theme = str(body.get("theme") or "").strip()
            if not theme:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Kies een thema of typ waar je zin in hebt")
            servings = int(body.get("servings") or 2)
            key = inspiration_key(theme, servings)
            if not body.get("refresh"):
                cached = db.get_inspiration(key)
                if cached:
                    return cached
            return db.save_inspiration(key, ai.inspiration(theme, servings))

        # ---------- weekmenu ----------

        def get_menu(self, query):
            return db.get_week_menu(self._require(query, "week"))

        def add_option(self, query):
            body = self._body()
            return {"id": db.add_menu_option(body.get("date"), body.get("recipe_id"))}

        def remove_option(self, query, option_id):
            db.remove_menu_option(int(option_id))
            return {"ok": True}

        def choose_option(self, query, option_id):
            db.choose_option(int(option_id), self._body().get("servings"))
            return {"ok": True}

        def save_option(self, query, option_id):
            return {"recipe_id": db.save_option_recipe(int(option_id))}

        def clear_choice(self, query):
            db.clear_dinner_choice(self._require(query, "date"))
            return {"ok": True}

        def copy_menu(self, query):
            return {"copied": db.copy_menu_from_previous_week(self._body().get("week"))}

        # ---------- boodschappen ----------

        def get_shopping(self, query):
            return db.shopping_list(self._require(query, "week"))

        def check_shopping(self, query):
            body = self._body()
            db.set_shopping_check(body.get("week"), str(body.get("key") or ""), bool(body.get("checked")))
            return {"ok": True}

        # ---------- AI ----------

        def fill_menu(self, query):
            """Laat Claude elke avond zonder keuze aanvullen tot `per_day` opties."""
            body = self._body()
            per_day = max(1, min(int(body.get("per_day") or 3), 5))
            menu = db.get_week_menu(body.get("week"))
            chosen = {c["date"] for c in menu["choices"]}
            today = date.today().isoformat()
            needs = {}
            for day in menu["days"]:
                count = sum(1 for o in menu["options"] if o["date"] == day)
                if day >= today and day not in chosen and count < per_day:
                    needs[day] = per_day - count
            if not needs:
                return {"added": 0, "message": "Elke komende avond heeft al genoeg opties of een keuze."}

            suggestions = ai.suggest_menu_options(
                db.list_recipes(),
                needs,
                current_menu=[{"date": o["date"], "gerecht": o["name"]} for o in menu["options"]],
                wishes=str(body.get("wishes") or ""),
                servings=int(body.get("servings") or 2),
            )
            added = 0
            for s in suggestions:
                if s["existing_recipe_id"] is not None:
                    db.add_menu_option(s["date"], s["existing_recipe_id"], s["reason"], source="claude")
                    added += 1
                elif db.add_suggested_option(s["date"], s["new_recipe"], s["reason"]) is not None:
                    added += 1
            return {"added": added}

        # ---------- hulpfuncties ----------

        def _require(self, query, name):
            if not query.get(name):
                raise ApiError(HTTPStatus.BAD_REQUEST, f"Parameter '{name}' ontbreekt")
            return query[name]

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Verzoek is te groot")
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Ongeldige JSON")

        def _send_json(self, payload, status):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _serve_image(self, path):
            file = images.path_for(path)
            if file is None:
                return self._send_json({"error": "Afbeelding niet gevonden"}, HTTPStatus.NOT_FOUND)
            data = file.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", images.content_type(file))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            self.wfile.write(data)

        def _serve_static(self, path):
            if path in ("", "/"):
                path = "/index.html"
            file = (STATIC_DIR / path.lstrip("/")).resolve()
            if not file.is_relative_to(STATIC_DIR) or not file.is_file():
                file = STATIC_DIR / "index.html"
            data = file.read_bytes()
            content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type == "application/javascript":
                content_type += "; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

    ROUTES = [
        ("GET", re.compile(r"/api/recipes"), Handler.list_recipes),
        ("POST", re.compile(r"/api/recipes"), Handler.create_recipe),
        ("POST", re.compile(r"/api/recipes/import"), Handler.import_recipe),
        ("POST", re.compile(r"/api/recipes/generate"), Handler.generate_recipe),
        ("POST", re.compile(r"/api/images"), Handler.upload_image),
        ("POST", re.compile(r"/api/inspiration"), Handler.inspiration),
        ("GET", re.compile(r"/api/preferences"), Handler.get_preferences),
        ("PUT", re.compile(r"/api/preferences"), Handler.save_preferences),
        ("GET", re.compile(r"/api/swipe"), Handler.get_swipe),
        ("POST", re.compile(r"/api/swipe/more"), Handler.more_swipe_cards),
        ("POST", re.compile(r"/api/swipe/undo"), Handler.undo_swipe),
        ("POST", re.compile(r"/api/swipe/preload"), Handler.preload_swipe),
        ("DELETE", re.compile(r"/api/swipe/pending"), Handler.clear_swipe_cards),
        ("POST", re.compile(r"/api/swipe/cards/(\d+)/photo"), Handler.swipe_card_photo),
        ("POST", re.compile(r"/api/swipe/cards/(\d+)"), Handler.swipe_card),
        ("GET", re.compile(r"/api/settings"), Handler.get_settings),
        ("PUT", re.compile(r"/api/settings"), Handler.save_settings),
        ("DELETE", re.compile(r"/api/settings/key/(claude|gemini)"), Handler.delete_key),
        ("POST", re.compile(r"/api/settings/test"), Handler.test_connection),
        ("POST", re.compile(r"/api/photos/draft"), Handler.photo_for_draft),
        ("POST", re.compile(r"/api/recipes/(\d+)/photo"), Handler.photo_for_recipe),
        ("POST", re.compile(r"/api/inspiration/photo"), Handler.photo_for_idea),
        ("GET", re.compile(r"/api/recipes/(\d+)"), Handler.get_recipe),
        ("PUT", re.compile(r"/api/recipes/(\d+)"), Handler.update_recipe),
        ("DELETE", re.compile(r"/api/recipes/(\d+)"), Handler.delete_recipe),
        ("GET", re.compile(r"/api/menu"), Handler.get_menu),
        ("POST", re.compile(r"/api/menu/options"), Handler.add_option),
        ("DELETE", re.compile(r"/api/menu/options/(\d+)"), Handler.remove_option),
        ("POST", re.compile(r"/api/menu/options/(\d+)/choose"), Handler.choose_option),
        ("POST", re.compile(r"/api/menu/options/(\d+)/save"), Handler.save_option),
        ("DELETE", re.compile(r"/api/menu/choice"), Handler.clear_choice),
        ("POST", re.compile(r"/api/menu/copy-previous"), Handler.copy_menu),
        ("POST", re.compile(r"/api/menu/fill"), Handler.fill_menu),
        ("GET", re.compile(r"/api/shopping"), Handler.get_shopping),
        ("POST", re.compile(r"/api/shopping/check"), Handler.check_shopping),
    ]

    return Handler


def remove_orphaned_images(db, images, min_age_seconds=86400):
    """Ruim foto's op van imports die nooit zijn opgeslagen (ouder dan een dag, nergens gebruikt)."""
    cutoff = time.time() - min_age_seconds
    for file in images.directory.iterdir():
        url = "/images/" + file.name
        if images.path_for(url) and file.stat().st_mtime < cutoff and not db.image_in_use(url):
            file.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Start de mealplanner-server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Pad naar het SQLite-bestand")
    args = parser.parse_args()

    db = Database(args.db)
    images = ImageStore(Path(args.db).resolve().parent / "images")
    remove_orphaned_images(db, images)
    try:
        server = ThreadingHTTPServer((args.host, args.port), make_handler(db, images))
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        raise SystemExit(
            f"Poort {args.port} is al in gebruik; waarschijnlijk draait Mealplanner al.\n"
            f"Stop die eerst met Ctrl+C in de terminal waar hij draait, of kies een andere poort: --port {args.port + 1}"
        )
    print(f"Mealplanner draait op http://{args.host}:{args.port}  (Ctrl+C om te stoppen)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
