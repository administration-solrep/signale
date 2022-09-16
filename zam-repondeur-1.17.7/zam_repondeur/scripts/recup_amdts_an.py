import logging
import sys
from argparse import ArgumentParser, Namespace
from typing import List, Optional

import transaction
from pyramid.paster import bootstrap, setup_logging

logger = logging.getLogger(__name__)


def main(argv: List[str] = sys.argv) -> None:

    args = parse_args(argv[1:])

    setup_logging(args.config_uri)

    with bootstrap(args.config_uri, options={"app": "zam_force_amdts_an"}):
        from zam_repondeur.services.fetch.an.amendements import (
            AssembleeNationale,
            fetch_discussion_list,
        )

        from zam_repondeur.models import Lecture, DBSession, Dossier, Texte

        partie: Optional[int] = None
        try:
            chambre, legislature, texte_partie, organe = args.lecture_url_key.split(".")
            if "-" in texte_partie:
                texte, partie = (int(value) for value in texte_partie.split("-"))
            else:
                texte = int(texte_partie)
        except Exception:
            logger.error(
                "Mauvais format pour la clef de lecture %r", args.lecture_url_key
            )
            return

        if chambre.lower() != "an":
            logger.error(
                "Mauvais format pour la clef de lecture %r, ce n'est pas une \
lecture de l'AN",
                args.lecture_url_key,
            )
            return

        max_404 = args.max404
        dossier_slug = args.dossier_slug

        with transaction.manager:
            lectures = (
                DBSession.query(Lecture)
                .filter(
                    Lecture.dossier_pk == Dossier.pk,
                    Dossier.slug == dossier_slug,
                    Lecture.organe == organe,
                    Lecture.partie == partie,
                    Lecture.texte_pk == Texte.pk,
                    Texte.numero == texte,
                )
                .all()
            )

            if not lectures:
                logger.error("Aucune lecture trouvée")
                return

            for lecture in lectures:
                logger.info("Traitement de la lecture : %r", str(lecture))
                derouleur = fetch_discussion_list(lecture)
                discussion_nums = derouleur.discussion_nums
                prefix = derouleur.find_prefix()
                AN = AssembleeNationale(prefetching_enabled=False)
                (
                    actions,
                    unchanged,
                    errored,
                    triAmendements,
                ) = AN._collect_amendements_other(
                    lecture, discussion_nums, prefix, max_404
                )
                for action in actions:
                    try:
                        print(f"Traitement de l'action : {action}")
                        action.apply(lecture)
                    except Exception:
                        logger.error("Erreur avec l'action : %r", str(action))


def parse_args(argv: List[str]) -> Namespace:
    parser = ArgumentParser()
    parser.add_argument("config_uri")
    parser.add_argument(
        "dossier_slug",
        type=str,
        help="slug du dossier dans l'url ex: loi-finances-2021",
    )
    parser.add_argument(
        "lecture_url_key",
        type=str,
        help="Clef de la lecture dans l'url ex: an.15.3360-2.PO717460",
    )
    parser.add_argument(
        "max404",
        type=int,
        default=400,
        nargs="?",
        help="Valeur maximale pour l'exploration ( 400 par défaut )",
    )
    return parser.parse_args(argv)
