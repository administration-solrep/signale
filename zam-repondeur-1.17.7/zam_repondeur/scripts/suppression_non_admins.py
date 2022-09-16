import configparser
import logging
import sys
from argparse import ArgumentParser, Namespace
from typing import List

import transaction
from pyramid.paster import bootstrap, setup_logging

from zam_repondeur.models import DBSession, User

logger = logging.getLogger(__name__)


def main(argv: List[str] = sys.argv) -> None:

    args = parse_args(argv[1:])

    config = configparser.ConfigParser()
    config.read(args.config_uri)
    special_command = (
        config["app:worker"].get("zam.allow.special.command", "false").lower()
    )
    if special_command not in ["true", "oui", "yes"]:
        print(
            f"Impossible de lancer la commande de suppression \
des utilisateurs sur cet environnement"
        )
        return

    setup_logging(args.config_uri)

    log_level = logging.WARNING
    if args.verbose:
        log_level = logging.INFO
    if args.debug:
        log_level = logging.DEBUG
    logging.getLogger().setLevel(log_level)

    with bootstrap(args.config_uri, options={"app": "zam_suppression_non_admin"}):
        with transaction.manager:
            for user in (
                DBSession.query(User).filter(User.admin_at == None).all()
            ):  # noqa
                logging.info(f"Suppression de l'utilisateur {user}")
                for table in user.tables:
                    DBSession.delete(table)
                DBSession.delete(user)


def parse_args(argv: List[str]) -> Namespace:
    parser = ArgumentParser()
    parser.add_argument("config_uri")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-d", "--debug", action="store_true")
    return parser.parse_args(argv)
