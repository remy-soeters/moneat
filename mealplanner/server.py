"""Start de mealplanner: `python -m mealplanner.server` (of `python -m mealplanner`)."""

import argparse
import errno
import os
import signal
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from .app import App, Config, make_handler
from .db import Database
from .images import ImageStore

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "mealplanner.db"


def remove_orphaned_images(db, images, min_age_seconds=86400):
    """Ruim foto's op van imports die nooit zijn opgeslagen (ouder dan een dag, nergens gebruikt)."""
    cutoff = time.time() - min_age_seconds
    for file in images.directory.iterdir():
        url = "/images/" + file.name
        if images.path_for(url) and file.stat().st_mtime < cutoff and not db.image_in_use(url):
            file.unlink(missing_ok=True)


def open_app(db_path, config=None):
    db = Database(db_path)
    images = ImageStore(Path(db_path).resolve().parent / "images")
    remove_orphaned_images(db, images)
    return App(db, images, config or Config.from_env())


def main():
    parser = argparse.ArgumentParser(description="Start de mealplanner-server.")
    parser.add_argument("--host", default=os.environ.get("MEALPLANNER_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MEALPLANNER_PORT", 8000)))
    parser.add_argument("--db", default=os.environ.get("MEALPLANNER_DB", str(DEFAULT_DB)), help="Pad naar het SQLite-bestand")
    args = parser.parse_args()

    app = open_app(args.db)
    try:
        server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        raise SystemExit(
            f"Poort {args.port} is al in gebruik; waarschijnlijk draait Mealplanner al.\n"
            f"Stop die eerst met Ctrl+C in de terminal waar hij draait, of kies een andere poort: --port {args.port + 1}"
        )
    print(f"Mealplanner draait op http://{args.host}:{args.port}  (Ctrl+C om te stoppen)", flush=True)
    if app.config.trust_proxy:
        print("Achter een proxy: X-Forwarded-Proto/-For en X-Real-IP worden vertrouwd.", flush=True)
    if app.setup_code:
        print(
            "\n  Nog geen accounts. Open de app en maak het eerste (beheerders)account aan met deze code:\n"
            f"\n      {app.setup_code}\n\n  De code verandert bij elke herstart.\n",
            flush=True,
        )

    # Docker (en systemd) stoppen met SIGTERM: net zo netjes afsluiten als bij Ctrl+C.
    def stop(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
