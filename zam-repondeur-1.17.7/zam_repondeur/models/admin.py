from datetime import datetime
from typing import Optional

from psycopg2 import Binary
from sqlalchemy import Column, DateTime, Integer, LargeBinary, Text

from .base import Base, DBSession


class Actualite(Base):
    __tablename__ = "actualite"

    pk = Column(Integer, primary_key=True)
    created_at: datetime = Column(DateTime, nullable=False)

    file_name: Optional[str] = Column(Text, nullable=True)
    file_content_type: Optional[str] = Column(Text, nullable=True)
    file_data: Optional[Binary] = Column(LargeBinary, nullable=True)

    message: Optional[str] = Column(Text, nullable=True)

    def __repr__(self) -> str:
        message_repr: str = ""
        if self.message:
            message_repr = self.message[:10]
        return f"<Actualite: {self.pk}, {self.file_name}, {message_repr}>"

    @classmethod
    def create(  # type: ignore
        cls,
        message: Optional[str] = None,
        piece_jointe=None,
        file_name: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> "Actualite":
        now = datetime.utcnow()
        file_data: Optional[Binary] = None
        if piece_jointe is not None:
            file_data = piece_jointe.read()

        actualite = cls(
            created_at=now,
            file_name=file_name,
            file_content_type=content_type,
            file_data=file_data,
            message=message,
        )
        DBSession.add(actualite)
        return actualite

    @classmethod
    def remove(cls) -> None:
        DBSession.query(cls).delete()

    @classmethod
    def get(cls) -> Optional["Actualite"]:
        res: Optional["Actualite"] = DBSession.query(cls).first()
        return res

    @property
    def has_attachment(self) -> bool:
        return (
            self.file_name is not None
            and self.file_content_type is not None
            and self.file_data is not None
        )


class Parametres(Base):
    __tablename__ = "parametres"

    pk: int = Column(Integer, primary_key=True)
    type: str = Column(Text, nullable=False)
    value: str = Column(Text, nullable=False)

    @classmethod
    def get_active_alerts(cls) -> bool:
        res: "Parametres" = DBSession.query(cls).filter(
            cls.type == "alert_system_active"
        ).first()
        return bool(int(res.value))

    @classmethod
    def switch_alerts(cls) -> bool:
        sys_alerts = (
            DBSession.query(cls).filter(cls.type == "alert_system_active").first()
        )
        sys_alerts.value = "1" if not bool(int(sys_alerts.value)) else "0"
        DBSession.add(sys_alerts)
        return bool(int(sys_alerts.value))
