"""Accounts beheren vanaf de opdrachtregel, bijvoorbeeld als je je wachtwoord kwijt bent.

    python -m mealplanner.users list
    python -m mealplanner.users add <naam> [--admin]
    python -m mealplanner.users password <naam>

In Docker: `docker compose exec mealplanner python -m mealplanner.users password <naam>`.
"""

import argparse
import getpass
import os
import sys

from . import auth
from .db import Database
from .server import DEFAULT_DB


def ask_password(username):
    while True:
        password = getpass.getpass("Nieuw wachtwoord: ")
        if password != getpass.getpass("Nog een keer: "):
            print("De wachtwoorden zijn niet gelijk, probeer opnieuw.")
            continue
        try:
            return auth.check_new_password(password, username)
        except ValueError as e:
            print(e)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Accounts van de mealplanner beheren.")
    parser.add_argument("--db", default=os.environ.get("MEALPLANNER_DB", str(DEFAULT_DB)))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="Toon alle accounts")
    add = commands.add_parser("add", help="Maak een account aan")
    add.add_argument("username")
    add.add_argument("--name", default="", help="Naam zoals die in de app staat")
    add.add_argument("--admin", action="store_true", help="Maak er een beheerder van")
    password = commands.add_parser("password", help="Stel een nieuw wachtwoord in (en log overal uit)")
    password.add_argument("username")
    args = parser.parse_args(argv)

    db = Database(args.db)
    if args.command == "list":
        for user in db.list_users():
            print(f"{user['username']:<20} {user['display_name']:<24} {'beheerder' if user['is_admin'] else ''}")
        return
    if args.command == "add":
        user = db.create_user(args.username, auth.hash_password(ask_password(args.username)), args.name, args.admin)
        print(f"Account {user['username']} aangemaakt.")
        return
    user, _ = db.credentials(args.username)
    if user is None:
        sys.exit(f"Geen account met de naam {args.username}.")
    db.set_password_hash(user["id"], auth.hash_password(ask_password(user["username"])))
    db.delete_user_sessions(user["id"])
    print(f"Nieuw wachtwoord ingesteld voor {user['username']}; alle apparaten moeten opnieuw inloggen.")


if __name__ == "__main__":
    main()
