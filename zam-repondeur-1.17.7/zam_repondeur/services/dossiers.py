from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from pyramid.config import Configurator
from pytz import timezone

from zam_repondeur.initialize import needs_init
from zam_repondeur.models import Dossier
from zam_repondeur.services import Repository
from zam_repondeur.services.data import repository
from zam_repondeur.services.fetch.an.dossiers.models import DossierRefsByUID


def includeme(config: Configurator) -> None:
    """
    Called automatically via config.include("zam_repondeur.services.dossiers")
    """
    dossier_export_repository.initialize(
        redis_url=config.registry.settings["zam.users.redis_url"]
    )
    dossier_export_repository.export_duration = int(
        config.registry.settings["zam.users.export_dossier_duration"]
    )


def get_dossiers_legislatifs_open_data_from_cache() -> DossierRefsByUID:
    dossiers: DossierRefsByUID = {
        uid: repository.get_opendata_dossier_ref(uid)
        for uid in repository.list_opendata_dossiers()
    }
    return dossiers


def get_dossiers_legislatifs_scraping_senat_from_cache() -> DossierRefsByUID:
    dossiers: DossierRefsByUID = {
        uid: repository.get_senat_scraping_dossier_ref(uid)
        for uid in repository.list_senat_scraping_dossiers()
    }
    return dossiers


class DossierExportRepository(Repository):
    """
    Store and access dossier export result in Redis
    """

    export_duration = 0

    @needs_init
    def clear_data(self) -> None:
        self.connection.flushdb()

    @staticmethod
    def _export_dossier_key(dossier: Dossier) -> str:
        return f"export_dossier-{dossier.pk}"

    @needs_init
    def set_export_content(self, dossier: Dossier, export_content: bytes) -> None:
        key = self._export_dossier_key(dossier)
        created_at = self.now()
        expires_at = self.to_timestamp(
            created_at + timedelta(seconds=self.export_duration)
        )
        pipe = self.connection.pipeline()
        pipe.multi()  # start transaction
        pipe.hset(
            key,
            mapping={
                "slug": dossier.slug,
                "created_at": self.to_timestamp(created_at),
                "expires_at": expires_at,
                "export_content": export_content,
            },
        )
        pipe.expireat(key, expires_at)
        pipe.execute()  # execute transaction atomically

    def has_export_content(self, dossier: Dossier) -> Optional[datetime]:
        key = self._export_dossier_key(dossier)
        dossier_export = self.connection.hgetall(key)
        if dossier_export == {}:  # does not exist, or expired in Redis
            return None

        my_tz = timezone("Europe/Paris")
        expires_at = self.from_timestamp(float(dossier_export[b"expires_at"]))
        return expires_at.astimezone(my_tz)

    def get_export_data(self, dossier: Dossier) -> Optional[Dict[str, Any]]:
        key = self._export_dossier_key(dossier)
        dossier_export = self.connection.hgetall(key)
        if dossier_export == {}:  # does not exist, or expired in Redis
            return None

        expires_at = self.from_timestamp(float(dossier_export[b"expires_at"]))
        created_at = self.from_timestamp(float(dossier_export[b"created_at"]))
        my_tz = timezone("Europe/Paris")

        return {
            "created_at": created_at.astimezone(my_tz),
            "expires_at": expires_at.astimezone(my_tz),
            "export_content": dossier_export[b"export_content"],
        }


dossier_export_repository = DossierExportRepository()
