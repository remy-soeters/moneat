"""Houdt op de achtergrond een voorraad swipekaarten mét foto klaar."""

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

from . import ai
from .db import NotFound

PRELOAD_OPTIONS = (5, 10, 15, 20)
DEFAULT_PRELOAD = 10
PHOTO_WORKERS = 3  # foto's tegelijk; hoger loopt eerder tegen limieten van Gemini aan
MAX_BATCH = 12  # maximaal aantal gerechten per AI-verzoek
MAX_ROUNDS = 3  # zo vaak opnieuw vragen als er te veel dubbele gerechten tussen zitten


class SwipePreloader:
    def __init__(self, db, images, release_image, load_preferences, target):
        self.db = db
        self.images = images
        self.release_image = release_image
        self.load_preferences = load_preferences
        self.target = target  # functie die het gewenste aantal kaarten geeft
        self.lock = threading.Lock()
        self.db_lock = threading.Lock()  # foto's worden tegelijk gemaakt, maar één voor één opgeslagen
        self.thread = None
        self.servings = 2
        self.error = None
        self.photos_failed = None  # melding als foto's maken niet lukt (bijv. geen betaling)

    # ---------- status ----------

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def status(self):
        return {
            "running": self.running(),
            "target": self.target(),
            "error": self.error,
            "photos_failed": self.photos_failed,
            "photos_enabled": self.photos_enabled(),
        }

    def photos_enabled(self):
        return self.photos_failed is None and ai.auto_images()

    # ---------- aansturen ----------

    def kick(self, servings=None, retry=False):
        """Start het aanvullen als dat nodig is; keert direct terug."""
        with self.lock:
            if servings:
                self.servings = int(servings)
            if retry:
                self.error = None
                self.photos_failed = None
            if self.running() or not self.load_preferences().get("diet"):
                return
            self.thread = threading.Thread(target=self._run, name="swipe-preloader", daemon=True)
            self.thread.start()

    def _run(self):
        try:
            self.error = None
            self._fill_cards()
            self._fill_photos()
        except ai.AIUnavailable as e:
            self.error = str(e)
            self.db.log_error(e.source or ai.provider_name(), "Swipekaarten klaarzetten", str(e), e.detail)
        except Exception as e:  # een achtergrondtaak mag de server nooit laten crashen
            self.error = f"Onverwachte fout bij het klaarzetten: {e}"
            self.db.log_error("Server", "Swipekaarten klaarzetten", self.error, traceback.format_exc()[-4000:])

    def _fill_cards(self):
        # Soms stelt de AI gerechten voor die je al gezien hebt; die vallen af, dus vraag zo nodig nog eens.
        for _ in range(MAX_ROUNDS):
            missing = self.target() - len(self.db.pending_swipe_cards())
            if missing <= 0:
                return
            ideas = ai.swipe_recipes(
                self.load_preferences(), min(missing + 2, MAX_BATCH), exclude=self.db.known_dish_names(), servings=self.servings
            )
            self.db.add_swipe_cards(ideas)

    def _fill_photos(self):
        if not self.photos_enabled():
            return
        todo = [c for c in self.db.pending_swipe_cards()[: self.target()] if not c["image"]]
        with ThreadPoolExecutor(max_workers=PHOTO_WORKERS) as pool:
            for _ in pool.map(self._photo, todo):
                pass

    def _photo(self, card):
        if self.photos_failed:
            return
        try:
            image = self.images.save(ai.generate_photo(card["recipe"]))
        except ai.AIUnavailable as e:
            if self.photos_failed is None:
                self.db.log_error(e.source or "Gemini", "Foto's voor swipekaarten", str(e), e.detail)
            self.photos_failed = str(e)
            return
        with self.db_lock:
            try:
                current = self.db.get_swipe_card(card["id"])
            except NotFound:
                self.images.delete(image)  # kaart is intussen weggegooid (nieuwe voorkeuren)
                return
            self.db.set_swipe_card_image(card["id"], image)
            self.release_image(current["image"])
            if current["status"] == "liked" and current["recipe_id"]:
                # Intussen al bewaard: geef het recept in het receptenboek alsnog deze foto.
                recipe = self.db.get_recipe(current["recipe_id"])
                if not recipe["image"]:
                    self.db.update_recipe(recipe["id"], {**recipe, "image": image})
