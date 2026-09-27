"""Schrijft op de achtergrond recepten van de AI volledig uit.

Opties voor het weekmenu, swipekaarten en inspiratie worden met vele tegelijk bedacht; dan schrijft de AI ze kort.
Komt zo'n schets in het receptenboek (kiezen, bewaren, naar rechts swipen), dan schrijft deze taak hem hier één
voor één volledig uit: alle stappen, tijden en temperaturen, en elk ingrediënt gebruikt.
"""

import threading
import time
import traceback

from . import ai
from .db import NotFound

RETRY_AFTER = 300  # na een fout (bijv. een limiet van Gemini) pas na vijf minuten opnieuw proberen


class RecipeWriter:
    def __init__(self, db, log_error):
        self.db = db
        self.log_error = log_error
        self.lock = threading.Lock()
        self.thread = None
        self.error = None
        self.failed_at = 0.0

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def kick(self, retry=False):
        """Start het uitschrijven als er schetsen zijn; keert direct terug."""
        with self.lock:
            if retry:
                self.error = None
            if self.error and time.monotonic() - self.failed_at < RETRY_AFTER:
                return
            if self.running() or not self.db.draft_recipe_ids():
                return
            self.error = None
            self.thread = threading.Thread(target=self._run, name="recipe-writer", daemon=True)
            self.thread.start()

    def write(self, recipe_id, force=False):
        """Schrijf één recept volledig uit en bewaar het. Zonder `force` blijft een recept dat intussen zelf gewijzigd
        is zoals het is (dan geeft dit None)."""
        before = self.db.get_recipe(recipe_id)
        return self.db.save_written_recipe(recipe_id, before, ai.write_out_recipe(before), force=force)

    def _run(self):
        done = set()
        while True:
            todo = [i for i in self.db.draft_recipe_ids() if i not in done]
            if not todo:
                return
            done.add(todo[0])
            try:
                with ai.usage("Recepten uitschrijven na bewaren", auto=True):
                    self.write(todo[0])
            except NotFound:
                continue  # intussen verwijderd
            except ai.AIUnavailable as e:
                self._failed(str(e), e.source or ai.provider_name(), e.detail)
                return
            except Exception as e:  # een achtergrondtaak mag de server nooit laten crashen
                self._failed(f"Onverwachte fout bij het uitschrijven: {e}", "Server", traceback.format_exc()[-4000:])
                return

    def _failed(self, message, source, detail):
        self.error = message
        self.failed_at = time.monotonic()
        self.log_error(source, "Recepten uitschrijven", message, detail)
