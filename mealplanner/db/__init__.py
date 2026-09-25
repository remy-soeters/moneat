"""SQLite-opslag van de mealplanner. Elk onderdeel (recepten, menu, lijst, …) staat in een eigen module."""

from .base import BaseDatabase, NotFound
from .cleaning import check_date, icon_key, week_dates
from .menu import MenuMixin
from .misc import SettingsMixin
from .ratings import RatingsMixin
from .recipes import RecipesMixin
from .shopping import ShoppingMixin
from .swipe import SwipeMixin
from .users import UsersMixin


class Database(RecipesMixin, MenuMixin, ShoppingMixin, SwipeMixin, SettingsMixin, RatingsMixin, UsersMixin, BaseDatabase):
    """Alle opslag in één object; de methodes komen uit de mixins hierboven."""


__all__ = ["Database", "NotFound", "check_date", "icon_key", "week_dates"]
