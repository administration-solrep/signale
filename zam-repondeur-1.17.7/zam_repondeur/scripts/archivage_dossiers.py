import configparser
import logging
import sys
from argparse import ArgumentParser, Namespace
from typing import List

import transaction
from pyramid.paster import bootstrap, setup_logging

from zam_repondeur.models import DBSession, Team

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
            f"Impossible de lancer la commande d'archivage \
des dossiers sur cet environnement"
        )
        return

    setup_logging(args.config_uri)

    log_level = logging.WARNING
    if args.verbose:
        log_level = logging.INFO
    if args.debug:
        log_level = logging.DEBUG
    logging.getLogger().setLevel(log_level)

    with bootstrap(args.config_uri, options={"app": "zam_archivage_dossiers"}):
        with transaction.manager:
            for team in DBSession.query(Team).all():
                logging.info(f"Archivage du dossier {team.dossier.titre}")
                team.active = False


def parse_args(argv: List[str]) -> Namespace:
    parser = ArgumentParser()
    parser.add_argument("config_uri")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-d", "--debug", action="store_true")
    return parser.parse_args(argv)
