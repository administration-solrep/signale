from time import time

import transaction

from zam_repondeur.models import Amendement, DBSession
from zam_repondeur.services.clean import clean_all_for_search

with transaction.manager:
    start = time()
    query = DBSession.query(Amendement).order_by(Amendement.pk)
    print("Traitement de la table amendements")
    count = 1
    # Si besoin de reprise ajouter :
    # query = query.filter(Amendement.pk > last_pk)
    total = query.count()
    for amdt in query.all():
        print(f"{count}/{total} => traitement de l'amendement pk: {amdt.pk}")
        amdt.expose_search = clean_all_for_search(amdt.expose or "")
        amdt.corps_search = clean_all_for_search(amdt.corps or "")
        amdt.user_content.objet_search = clean_all_for_search(
            amdt.user_content.objet or ""
        )
        amdt.user_content.reponse_search = clean_all_for_search(
            amdt.user_content.reponse or ""
        )
        amdt.user_content.comments_search = clean_all_for_search(
            amdt.user_content.comments or ""
        )
        DBSession.add(amdt)
        count += 1
    end = time()
    delta = end - start
    print(f"{delta}s")
