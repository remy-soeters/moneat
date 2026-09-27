"""Namen van de instellingen die de app in de tabel `settings` bewaart."""

# AI (zie ai.py): sleutels, welke AI de tekst schrijft en de modellen.
CLAUDE_KEY = "anthropic_api_key"
CLAUDE_MODEL = "claude_model"
GEMINI_KEY = "gemini_api_key"
GEMINI_TEXT_KEY = "gemini_text_api_key"  # optioneel: sleutel uit een project zónder betalen, voor gratis tekst
TEXT_PROVIDER = "text_provider"
GEMINI_PLAN = "gemini_plan"  # "free" = recepten alleen via de gratis sleutel, "paid" = via de sleutel met betalen
GEMINI_TEXT_MODEL = "gemini_text_model"
GEMINI_IMAGE_MODEL = "gemini_image_model"
AUTO_IMAGES = "auto_images"  # "off" = geen foto's/iconen op de achtergrond laten maken

PREFERENCES = "food_preferences"  # voedselvoorkeuren voor het swipen
SWIPE_PRELOAD = "swipe_preload"  # hoeveel swipekaarten er klaar moeten staan
