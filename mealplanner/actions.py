"""Wat iemand aan het doen was, in woorden, voor het logboek bij Instellingen → Foutmeldingen."""

import re

# (patroon voor "METHODE pad", omschrijving); wat hier niet in staat, komt er als "METHODE pad" in.
ACTIONS = [
    (r"POST /api/menu/fill", "Opties voor het weekmenu"),
    (r"POST /api/menu/refresh", "Andere opties"),
    (r"POST /api/menu/describe", "Recept omschrijven bij Plannen"),
    (r"POST /api/recipes/\d+/write", "Recept uitschrijven"),
    (r"POST /api/recipes/generate", "Recept laten bedenken"),
    (r"POST /api/recipes/import", "Recept importeren"),
    (r"POST (/api/recipes/\d+/photo|/api/photos/draft|/api/inspiration/photo)", "Foto maken"),
    (r"\w+ /api/shopping/icon", "Icoon maken"),
    (r"POST /api/inspiration", "Inspiratie"),
    (r"\w+ (/api/swipe.*|/api/preferences)", "Swipen"),
    (r"POST /api/settings/test", "Verbinding testen"),
    (r"GET /api/home", "Vandaag openen"),
    (r"GET /api/menu", "Weekmenu openen"),
    (r"GET /api/recipes", "Receptenboek openen"),
    (r"GET /api/shopping", "Boodschappenlijst openen"),
]


def describe_action(method, path):
    action = f"{method} {path}".strip()
    return next((label for pattern, label in ACTIONS if re.fullmatch(pattern, action)), action)
