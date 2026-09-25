"""Alle API-routes, per onderdeel een module. Elke module heeft `register(router, app)`."""

from . import account, inspiration, menu, recipes, settings, shopping, swipe


def register_all(router, app):
    for module in (account, recipes, menu, inspiration, swipe, shopping, settings):
        module.register(router, app)
