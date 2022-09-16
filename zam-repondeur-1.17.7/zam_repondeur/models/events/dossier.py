from string import Template
from typing import Any, Optional

from markupsafe import Markup
from pyramid.request import Request

from ..dossier import Dossier
from ..users import User
from .base import Event


class DossierEvent(Event):
    details_template = Template("")

    def __init__(
        self, dossier: Dossier, request: Optional[Request] = None, **kwargs: Any
    ):
        super().__init__(request=request, **kwargs)
        self.dossier = dossier

    @property
    def template_vars(self) -> dict:
        if self.user:
            return {"user": self.user.name, "email": self.user.email}
        return {}

    def render_summary(self) -> str:
        return Markup(self.summary_template.safe_substitute(**self.template_vars))

    def render_details(self) -> str:
        return Markup(self.details_template.safe_substitute(**self.template_vars))


class DossierJournalEvent(DossierEvent):
    def __init__(
        self, dossier: Dossier, request: Optional[Request] = None, **kwargs: Any
    ):
        super().__init__(dossier=dossier, request=request, **kwargs)


class DossierActive(DossierJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "dossier_active"}
    icon = "document"

    summary_template = Template(
        "<abbr title='$email'>$user</abbr> a activé le dossier."
    )

    def __init__(self, dossier: Dossier, request: Request):
        super().__init__(dossier=dossier, request=request)

    def apply(self) -> None:
        pass


class DossierSupprime(DossierJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "dossier_desactive"}
    icon = "document"

    summary_template = Template(
        "<abbr title='$email'>$user</abbr> a supprimé le dossier."
    )

    def __init__(
        self, dossier: Dossier, request: Optional[Request] = None, **kwargs: Any
    ):
        super().__init__(dossier=dossier, request=request, **kwargs)

    def apply(self) -> None:
        pass


class LecturesRecuperees(DossierJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "lectures_recuperees"}
    icon = "document"

    summary_template = Template("De nouvelles lectures ont été récupérées.")

    def __init__(self, dossier: Dossier, user: User, dossier_url: str):
        super().__init__(dossier=dossier, user=user)
        self.dossier_url = dossier_url

    def apply(self) -> None:
        pass


class InvitationEnvoyee(DossierJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "invitation_envoyee"}
    icon = "document"

    def __init__(self, dossier: Dossier, email: str, request: Request):
        super().__init__(dossier=dossier, email=email, request=request)

    @property
    def summary_template(self) -> Template:
        email = self.data["email"]
        return Template(
            f"<abbr title='$email'>$user</abbr> a invité « {email} » \
comme contributeur"
        )

    def apply(self) -> None:
        pass


class DossierRetrait(DossierJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "dossier_retrait"}
    icon = "document"

    def __init__(self, dossier: Dossier, email: str, request: Request):
        super().__init__(dossier=dossier, target=email, request=request)

    @property
    def summary_template(self) -> Template:
        email = self.data["target"]
        return Template(
            f"<abbr title='$email'>$user</abbr> a retiré « {email} » de \
ce dossier législatif"
        )

    def apply(self) -> None:
        pass


class InvitationCoordinateurEnvoyee(DossierJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "invitation_coordinateur_envoyee"}
    icon = "document"

    def __init__(self, dossier: Dossier, email: str, request: Request):
        super().__init__(dossier=dossier, target=email, request=request)

    @property
    def summary_template(self) -> Template:
        email = self.data["target"]
        return Template(
            f"<abbr title='$email'>$user</abbr> a invité « {email} » \
comme coordinateur"
        )

    def apply(self) -> None:
        pass


class PasseEnCoordinateur(DossierJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "passe_en_coordinateur"}
    icon = "document"

    def __init__(self, dossier: Dossier, email: str, request: Request):
        super().__init__(dossier=dossier, target=email, request=request)

    @property
    def summary_template(self) -> Template:
        email = self.data["target"]
        return Template(
            f"<abbr title='$email'>$user</abbr> a passé « {email} » \
de contributeur à coordinateur"
        )

    def apply(self) -> None:
        pass


class PasseEnContributeur(DossierJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "passe_en_contributeur"}
    icon = "document"

    def __init__(self, dossier: Dossier, email: str, request: Request):
        super().__init__(dossier=dossier, target=email, request=request)

    @property
    def summary_template(self) -> Template:
        email = self.data["target"]
        return Template(
            f"<abbr title='$email'>$user</abbr> a passé « {email} » \
de coordinateur à contributeur"
        )

    def apply(self) -> None:
        pass


class ArchiverDossier(DossierJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "archiver_dossier"}
    icon = "document"

    def __init__(self, dossier: Dossier, active: bool, request: Request):
        super().__init__(dossier=dossier, active=active, request=request)

    @property
    def summary_template(self) -> Template:
        active = self.data["active"]
        if active:
            if self.user:
                return Template(
                    f"<abbr title='$email'>$user</abbr> a réactivé le dossier"
                )
            else:
                return Template(f"Un utilisateur inconnu a réactivé le dossier")
        if self.user:
            return Template(f"<abbr title='$email'>$user</abbr> a archivé le dossier")
        else:
            return Template(f"Le dossier a été archivé automatiquement")

    def apply(self) -> None:
        pass


class RefreshDossier(DossierJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "refresh_dossier"}
    icon = "document"

    summary_template = Template(
        "<abbr title='$email'>$user</abbr> a demandé un rafraichissement des données."
    )

    def __init__(self, dossier: Dossier, request: Request):
        super().__init__(dossier=dossier, request=request)

    def apply(self) -> None:
        pass

    @property
    def is_active(self) -> bool:
        return False
