"""Laat Gemini op de achtergrond iconen tekenen voor producten op de boodschappenlijst."""

import threading
from concurrent.futures import ThreadPoolExecutor

from . import ai
from .db import icon_key

WORKERS = 3


class IconMaker:
    def __init__(self, db, images):
        self.db = db
        self.images = images
        self.lock = threading.Lock()
        self.queue = {}  # icoonsleutel -> productnaam, wacht op tekenen
        self.thread = None
        self.failed = None  # melding als iconen maken niet lukt (bijv. geen sleutel of betaling)

    def enabled(self):
        return self.failed is None and ai.auto_images()

    def pending(self):
        with self.lock:
            return bool(self.queue) or (self.thread is not None and self.thread.is_alive())

    def request(self, names):
        """Zet producten zonder icoon in de wachtrij; start het tekenen als dat nog niet loopt."""
        if not self.enabled():
            return
        have = self.db.product_icons(names)
        with self.lock:
            for name in names:
                if name not in have and icon_key(name):
                    self.queue.setdefault(icon_key(name), name)
            if self.queue and not (self.thread and self.thread.is_alive()):
                self.thread = threading.Thread(target=self._run, name="icon-maker", daemon=True)
                self.thread.start()

    def _next_batch(self):
        with self.lock:
            batch = list(self.queue.items())[:WORKERS * 4]
            for key, _ in batch:
                del self.queue[key]
            return batch

    def _run(self):
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            while self.enabled():
                batch = self._next_batch()
                if not batch:
                    return
                for _ in pool.map(lambda item: self._draw(item[1]), batch):
                    pass
        with self.lock:
            self.queue.clear()  # uitgeschakeld (fout): niet blijven wachten

    def _draw(self, name):
        if not self.enabled() or self.db.product_icons([name]):
            return
        try:
            with ai.usage("Iconen voor boodschappen", auto=True):
                image = self.images.save(ai.generate_icon(name))
        except ai.AIUnavailable as e:
            if self.failed is None:
                self.db.log_error(e.source or "Gemini", "Iconen tekenen", str(e), e.detail)
            self.failed = str(e)
            return
        self.db.set_product_icon(name, image)
