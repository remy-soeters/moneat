"""Controle en opschoning van invoer voordat die de database in gaat."""

import re
from datetime import date, timedelta


def week_dates(any_day):
    """De zeven datums (ma t/m zo) van de week waarin `any_day` valt."""
    d = check_date(any_day)
    monday = d - timedelta(days=d.weekday())
    return [(monday + timedelta(days=i)).isoformat() for i in range(7)]


def icon_key(name):
    """Eén icoon per product, ongeacht hoofdletters of spaties: 'Rode ui ' en 'rode ui' delen er een."""
    return " ".join(str(name or "").lower().split())[:60]


def clean_image(value):
    value = str(value or "").strip()
    if value and not re.fullmatch(r"/images/[0-9a-f]{32}\.(jpg|png|gif|webp)", value):
        raise ValueError("Ongeldige afbeelding")
    return value


def clean_url(value):
    value = str(value or "").strip()
    if value and not re.match(r"https?://", value):
        raise ValueError("De bron moet een http- of https-link zijn")
    return value[:2000]


def check_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"Ongeldige datum: {value!r} (verwacht JJJJ-MM-DD)")


def positive_int(value, default, label):
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} moet een geheel getal zijn")
    if number <= 0:
        raise ValueError(f"{label} moet groter dan 0 zijn")
    return number


# Bovengrenzen, zodat een recept (of een fout in een import) de database niet kan volstoppen.
MAX_NAME = 150
MAX_INGREDIENTS = 100
MAX_TEXT = 20_000
MAX_TAGS = 300


def clean_recipe(data):
    if not isinstance(data, dict):
        raise ValueError("Recept moet een object zijn")
    name = str(data.get("name") or "").strip()[:MAX_NAME]
    if not name:
        raise ValueError("Een recept heeft een naam nodig")

    prep = data.get("prep_minutes")
    prep = None if prep in (None, "") else positive_int(prep, None, "Bereidingstijd")

    raw_ingredients = data.get("ingredients") or []
    if not isinstance(raw_ingredients, list):
        raise ValueError("Ingrediënten moeten een lijst zijn")
    if len(raw_ingredients) > MAX_INGREDIENTS:
        raise ValueError(f"Een recept kan maximaal {MAX_INGREDIENTS} ingrediënten hebben")
    ingredients = []
    for ing in raw_ingredients:
        if not isinstance(ing, dict):
            continue
        ing_name = str(ing.get("name") or "").strip()[:MAX_NAME]
        if not ing_name:
            continue
        qty = ing.get("quantity")
        if qty in (None, ""):
            qty = None
        else:
            try:
                qty = float(str(qty).replace(",", "."))
            except ValueError:
                raise ValueError(f"Ongeldige hoeveelheid voor {ing_name}: {qty!r}")
            if not 0 <= qty < 1_000_000:
                raise ValueError(f"Ongeldige hoeveelheid voor {ing_name}")
        ingredients.append({"name": ing_name, "quantity": qty, "unit": str(ing.get("unit") or "").strip()[:30]})

    return {
        "name": name,
        "servings": min(positive_int(data.get("servings"), 2, "Aantal personen"), 100),
        "prep_minutes": prep,
        "instructions": str(data.get("instructions") or "").strip()[:MAX_TEXT],
        "tags": str(data.get("tags") or "").strip()[:MAX_TAGS],
        "image": clean_image(data.get("image")),
        "source_url": clean_url(data.get("source_url")),
        "ingredients": ingredients,
    }
