"""Inloggen: wachtwoorden hashen, sessies en een rem op het raden van wachtwoorden.

- Wachtwoorden worden gehasht met scrypt (traag en geheugenintensief, dus duur om te kraken).
- Een sessie is een willekeurige sleutel in een HttpOnly-cookie; in de database staat alleen de SHA-256 ervan.
- Na te veel mislukte pogingen per IP-adres of per gebruikersnaam volgt een tijdelijke blokkade.
"""

import base64
import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

# scrypt-instellingen (OWASP-aanbeveling: N=2^17 is streng; 2^15 is een goede balans voor een kleine server).
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
MIN_PASSWORD = 10
MAX_PASSWORD = 256

SESSION_DAYS = 30
SESSION_REFRESH = timedelta(hours=1)  # zo vaak schuift de verloopdatum op bij gebruik
COOKIE = "mp_session"
SECURE_COOKIE = "__Host-mp_session"  # __Host-: alleen via HTTPS, alleen voor dit domein

MAX_FAILURES = 5
FAILURE_WINDOW = 15 * 60
LOCKOUT = 15 * 60


class AuthError(Exception):
    def __init__(self, message, status=401):
        super().__init__(message)
        self.status = status


# ---------- wachtwoorden ----------


def check_new_password(password, username=""):
    password = str(password or "")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"Kies een wachtwoord van minstens {MIN_PASSWORD} tekens (een zin werkt goed)")
    if len(password) > MAX_PASSWORD:
        raise ValueError("Dit wachtwoord is te lang")
    if username and password.lower() == str(username).lower():
        raise ValueError("Je wachtwoord mag niet hetzelfde zijn als je gebruikersnaam")
    if password.lower() in COMMON_PASSWORDS:
        raise ValueError("Dit wachtwoord wordt te vaak gebruikt; kies iets anders")
    return password


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return "scrypt${}${}${}${}${}".format(
        SCRYPT_N, SCRYPT_R, SCRYPT_P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def verify_password(password, stored):
    try:
        kind, n, r, p, salt, digest = stored.split("$")
        if kind != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = _scrypt(str(password or ""), base64.b64decode(salt), int(n), int(r), int(p))
    except (ValueError, TypeError, AttributeError):
        return False
    return hmac.compare_digest(actual, expected)


# Voor een onbekende gebruikersnaam rekenen we net zo lang, zodat de tijd niet verraadt of een naam bestaat.
_DUMMY_HASH = None


def dummy_verify(password):
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_hex(8))
    verify_password(password, _DUMMY_HASH)


# scrypt gebruikt per keer ~32 MB geheugen; zo veel tegelijk mag er maximaal draaien.
_HASH_SLOTS = threading.BoundedSemaphore(2)


def _scrypt(password, salt, n, r, p):
    with _HASH_SLOTS:
        return hashlib.scrypt(
            str(password).encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=256 * n * r + 1024 * 1024
        )


# ---------- sessies ----------


def new_token():
    return secrets.token_urlsafe(32)


def token_hash(token):
    return hashlib.sha256(str(token).encode()).hexdigest()


def session_expiry():
    return _sql_time(datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS))


def needs_refresh(last_seen):
    try:
        seen = datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return True
    return datetime.now(timezone.utc) - seen > SESSION_REFRESH


def _sql_time(moment):
    """Zelfde notatie als SQLite's datetime('now'), zodat vergelijken in SQL klopt."""
    return moment.strftime("%Y-%m-%d %H:%M:%S")


# ---------- rem op wachtwoorden raden ----------


class Throttle:
    """Telt mislukte pogingen per sleutel (IP-adres, gebruikersnaam) en blokkeert tijdelijk bij te veel."""

    def __init__(self, max_failures=MAX_FAILURES, window=FAILURE_WINDOW, lockout=LOCKOUT, clock=time.monotonic):
        self.max_failures = max_failures
        self.window = window
        self.lockout = lockout
        self.clock = clock
        self._failures = {}  # sleutel -> [tijdstippen]
        self._blocked = {}  # sleutel -> tot wanneer
        self._lock = threading.Lock()

    def check(self, *keys):
        """Gooi AuthError als een van de sleutels geblokkeerd is."""
        now = self.clock()
        with self._lock:
            for key in keys:
                until = self._blocked.get(key)
                if until and until > now:
                    minutes = max(1, round((until - now) / 60))
                    raise AuthError(
                        f"Te veel mislukte pogingen. Probeer het over {minutes} {'minuut' if minutes == 1 else 'minuten'} opnieuw.",
                        status=429,
                    )

    def failure(self, *keys):
        now = self.clock()
        with self._lock:
            for key in keys:
                recent = [t for t in self._failures.get(key, []) if now - t < self.window] + [now]
                self._failures[key] = recent
                if len(recent) >= self.max_failures:
                    self._blocked[key] = now + self.lockout
                    self._failures[key] = []
            if len(self._failures) > 10_000:  # opruimen, zodat het geheugen niet volloopt
                self._failures = {k: v for k, v in self._failures.items() if v and now - v[-1] < self.window}
                self._blocked = {k: v for k, v in self._blocked.items() if v > now}

    def success(self, *keys):
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)


def new_setup_code():
    """Eenmalige code om het eerste (beheerders)account aan te maken; staat alleen in het serverlog."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    code = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{code[:4]}-{code[4:]}"


def same_code(given, expected):
    normalize = lambda c: str(c or "").strip().upper().replace(" ", "").replace("-", "")
    return bool(expected) and hmac.compare_digest(normalize(given), normalize(expected))


# Een korte lijst van de meest gebruikte wachtwoorden (die van 10+ tekens), zodat die geweigerd worden.
COMMON_PASSWORDS = {
    "1234567890", "12345678910", "0123456789", "qwertyuiop", "wachtwoord", "wachtwoord1", "wachtwoord123",
    "password12", "password123", "password1234", "passw0rd123", "iloveyou12", "1q2w3e4r5t", "qwerty1234",
    "qwerty12345", "1111111111", "0000000000", "abcdefghij", "welkom1234", "welkom123!", "mealplanner",
    "mealplanner1", "mealplanner123", "administrator", "adminadmin", "letmein123", "football12",
}
