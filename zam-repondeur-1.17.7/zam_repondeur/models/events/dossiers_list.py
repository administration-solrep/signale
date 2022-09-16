from string import Template
from typing import Any, Optional

from markupsafe import Markup
from pyramid.request import Request

from ..dossier import Dossier
from .base import Event


class DossiersListEvent(Event):
    details_template = Template("")

    def __init__(
        self, dossier: Dossier, request: Optional[Request] = None, **kwargs: Any
    ):
        super().__init__(request=request, **kwargs)
        self.dossier = dossier

    @property
    def template_vars(self) -> dict:
        if self.user:
            return {
                "user": self.user.name,
                "email": self.user.email,
                "dossier_name": self.dossier.titre,
            }
        else:
            return {"dossier_name": self.dossier.titre}

    def render_summary(self) -> str:
        return Markup(self.summary_template.safe_substitute(**self.template_vars))

    def render_details(self) -> str:
        return Markup(self.details_template.safe_substitute(**self.template_vars))


class DossiersListJournalEvent(DossiersListEvent):
    def __init__(
        self, dossier: Dossier, request: Optional[Request] = None, **kwargs: Any
    ):
        super().__init__(dossier=dossier, request=request, **kwargs)


class DossiersListActive(DossiersListJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "dossiers_list_active"}
    icon = "document"

    summary_template = Template(
        "<abbr title='$email'>$user</abbr> a activé le dossier \"$dossier_name\"."
    )

    def __init__(self, dossier: Dossier, request: Request):
        super().__init__(dossier=dossier, request=request)

    def apply(self) -> None:
        pass


class DossiersListSupprime(DossiersListJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "dossiers_list_desactive"}
    icon = "document"

    summary_template = Template(
        "<abbr title='$email'>$user</abbr> a supprimé le dossier \"$dossier_name\"."
    )

    def __init__(
        self, dossier: Dossier, request: Optional[Request] = None, **kwargs: Any
    ):
        super().__init__(dossier=dossier, request=request, **kwargs)

    def apply(self) -> None:
        pass


class ArchiverDossiersList(DossiersListJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "archiver_dossiers_list"}
    icon = "document"

    def __init__(self, dossier: Dossier, active: bool, request: Request):
        super().__init__(dossier=dossier, active=active, request=request)

    @property
    def summary_template(self) -> Template:
        active = self.data["active"]
        if active:
            if self.user:
                return Template(
                    "<abbr title='$email'>$user</abbr> a réactivé le dossier "
                    '"$dossier_name".'
                )
            else:
                return Template(
                    'Un utilisateur anonyme a réactivé le dossier "$dossier_name".'
                )
        if self.user:
            return Template(
                "<abbr title='$email'>$user</abbr> a archivé le dossier "
                '"$dossier_name".'
            )
        else:
            return Template('Le dossier "$dossier_name" a été archivé automatiquement')

    def apply(self) -> None:
        pass
