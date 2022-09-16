from time import time

import transaction

from zam_repondeur.models import DBSession, Team, User

# Pour effectuer les modifications Modifier la valeur de DRY_RUN a False
DRY_RUN = True

if DRY_RUN:
    print("Mode DRY -- aucune modification")
    dry_mode = "DRY - "
else:
    dry_mode = ""

with transaction.manager:
    start = time()
    admins = DBSession.query(User).filter(User.admin_at.isnot(None)).all()
    print(f"{dry_mode}Liste des admins ({len(admins)}) : ")
    for admin in admins:
        print(f"{dry_mode}{admin.name};{admin.email}")
    print(f"{dry_mode}Mise à jour des dossiers")
    for team in DBSession.query(Team).all():
        print(f"{dry_mode}Mise a jour du dossier : {team.name}")
        if not DRY_RUN:
            team.add_members(admin for admin in admins)
    end = time()
    delta = end - start
    print(f"{dry_mode}Durée : {delta}s")
