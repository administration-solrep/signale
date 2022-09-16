from time import time

import transaction

from zam_repondeur.models import Article, DBSession

# Pour effectuer les modifications Modifier la valeur de DRY_RUN a False
DRY_RUN = True

if DRY_RUN:
    print("Mode DRY -- aucune modification")
    dry_mode = "DRY - "
else:
    dry_mode = ""

with transaction.manager:
    start = time()
    mult = "–"
    articles = DBSession.query(Article).filter(Article.mult == mult).all()
    print(f"{dry_mode}{len(articles)} articles vont être supprimés.")
    for article in articles:
        print(f"{dry_mode}Suppression de : {article} {article.lecture}")
        if not DRY_RUN:
            DBSession.delete(article)
    end = time()
    delta = end - start
    print(f"{dry_mode}Durée : {delta}s")
