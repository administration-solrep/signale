import hashlib
from datetime import timedelta
from typing import Any, Dict, List, Optional

from pyramid.config import Configurator
from pytz import timezone

from zam_repondeur.initialize import needs_init
from zam_repondeur.models import Lecture, User
from zam_repondeur.services import Repository


def includeme(config: Configurator) -> None:
    """
    Called automatically via config.include("zam_repondeur.services.dossiers")
    """
    lecture_export_pdf_repository.initialize(
        redis_url=config.registry.settings["zam.users.redis_url"]
    )
    lecture_export_pdf_repository.export_duration = int(
        config.registry.settings["zam.users.export_pdf_duration"]
    )


class LectureExportPDFRepository(Repository):
    """
    Store and access lecture export pdf result in Redis
    """

    export_duration = 0

    @needs_init
    def clear_data(self) -> None:
        self.connection.flushdb()

    @staticmethod
    def _export_lecture_pdf_key(lecture: Lecture, articles: List[str] = []) -> str:
        articles_hash = "all"
        if articles:
            articles_hash = hashlib.md5(
                ",".join(sorted(articles)).encode("utf-8")
            ).hexdigest()
        return f"export_lecture_pdf-{lecture.pk}_{articles_hash}"

    def _export_lecture_pdf_match(self, lecture: Lecture) -> str:
        return f"export_lecture_pdf-{lecture.pk}_*"

    @needs_init
    def set_export_content(
        self,
        lecture: Lecture,
        user: User,
        export_content: bytes,
        articles: List[str] = [],
    ) -> None:
        key = self._export_lecture_pdf_key(lecture, articles)
        created_at = self.now()
        expires_at = self.to_timestamp(
            created_at + timedelta(seconds=self.export_duration)
        )
        pipe = self.connection.pipeline()
        pipe.multi()  # start transaction
        pipe.hset(
            key,
            mapping={
                "articles": ",".join(articles),
                "created_at": self.to_timestamp(created_at),
                "expires_at": expires_at,
                "username": user.name,
                "usermail": user.email,
                "export_content": export_content,
            },
        )
        pipe.expireat(key, expires_at)
        pipe.execute()  # execute transaction atomically

    def get_export_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        pdf_data = self.connection.hgetall(key)
        if pdf_data == {}:  # does not exist, or expired in Redis
            return None

        my_tz = timezone("Europe/Paris")
        expires_at = self.from_timestamp(float(pdf_data[b"expires_at"]))
        created_at = self.from_timestamp(float(pdf_data[b"created_at"]))
        articles_str = pdf_data[b"articles"].decode()
        articles = []
        if articles_str:
            articles = articles_str.split(",")
        return {
            "key": key,
            "articles": articles,
            "expires_at": expires_at.astimezone(my_tz),
            "created_at": created_at.astimezone(my_tz),
            "username": pdf_data[b"username"].decode(),
            "usermail": pdf_data[b"usermail"].decode(),
        }

    def has_export_data(self, lecture: Lecture) -> List[Optional[Dict[str, Any]]]:
        match = self._export_lecture_pdf_match(lecture)
        keys = list(key.decode() for key in self.connection.scan_iter(match))
        if not keys:  # does not exist, or expired in Redis
            return []
        return [self.get_export_metadata(key) for key in keys]

    def get_export_data(self, key: str) -> Optional[Dict[str, Any]]:
        lecture_export_pdf = self.connection.hgetall(key)
        if lecture_export_pdf == {}:  # does not exist, or expired in Redis
            return None

        expires_at = self.from_timestamp(float(lecture_export_pdf[b"expires_at"]))
        created_at = self.from_timestamp(float(lecture_export_pdf[b"created_at"]))
        my_tz = timezone("Europe/Paris")

        return {
            "created_at": created_at.astimezone(my_tz),
            "expires_at": expires_at.astimezone(my_tz),
            "export_content": lecture_export_pdf[b"export_content"],
        }


lecture_export_pdf_repository = LectureExportPDFRepository()
