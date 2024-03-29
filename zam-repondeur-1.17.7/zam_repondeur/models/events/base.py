from datetime import datetime
from typing import Any, List, Optional
from uuid import uuid4

from pyramid.request import Request
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy_utils import JSONType, UUIDType

from ..base import Base, DBSession
from ..users import User


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events__amendement_pk", "amendement_pk"),)

    # We use single-table inheritance, with polymorphism based on this column
    # see: https://docs.sqlalchemy.org/en/latest/orm/extensions/declarative/inheritance.html#single-table-inheritance  # noqa
    type = Column(String(64), nullable=False)
    __mapper_args__ = {"polymorphic_identity": "event", "polymorphic_on": type}

    pk = Column(UUIDType, primary_key=True, default=uuid4)
    created_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)

    user_pk = Column(Integer, ForeignKey("users.pk"), nullable=True)
    user = relationship(User, backref="events")

    amendement_pk = Column(
        Integer, ForeignKey("amendements.pk", ondelete="cascade"), nullable=True
    )
    dossier_pk = Column(Integer, ForeignKey("dossiers.pk"), nullable=True)
    article_pk = Column(
        Integer, ForeignKey("articles.pk", ondelete="cascade"), nullable=True
    )
    lecture_pk = Column(Integer, ForeignKey("lectures.pk"), nullable=True)

    data = Column(JSONType, nullable=True)
    meta = Column(JSONType, nullable=True)

    def __init__(
        self,
        request: Optional[Request] = None,
        meta: Optional[dict] = None,
        **kwargs: Any
    ) -> None:
        if self.meta is None:
            self.meta = {}
        if request is not None:
            self.user = request.user
            self.meta["ip"] = request.remote_addr
        elif "user" in kwargs:
            self.user = kwargs.pop("user")
        if self.data is None:
            self.data = {}
        self.data.update(kwargs)
        if meta is not None:
            self.meta.update(meta)

    @property
    def created_at_timestamp(self) -> float:
        timestamp: float = (self.created_at - datetime(1970, 1, 1)).total_seconds()
        return timestamp

    def apply(self) -> None:
        raise NotImplementedError

    @classmethod
    def create(cls, *args: Any, **kwargs: Any) -> "Event":
        event = cls(*args, **kwargs)
        event.apply()
        DBSession.add(event)
        return event

    def set_amdt_link(self, request: Request) -> None:
        pass

    @property
    def is_active(self) -> bool:
        return True


class LastEventMixin:

    created_at: datetime
    events: List[Event]

    @property
    def last_event(self) -> Optional[Event]:
        for event in self.events:
            if event.is_active:
                return event
        return None

    @property
    def last_event_datetime(self) -> datetime:
        event = self.last_event
        if event:
            return event.created_at
        return self.created_at

    @property
    def last_event_timestamp(self) -> float:
        delta = self.last_event_datetime - datetime(1970, 1, 1)
        return delta.total_seconds()
