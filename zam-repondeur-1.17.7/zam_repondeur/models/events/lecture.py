from string import Template
from typing import Any, List, Optional

from markupsafe import Markup
from pyramid.request import Request

from zam_repondeur.models import Amendement, DBSession

from ..lecture import Lecture
from ..texte import Texte
from ..users import User
from .base import Event


class LectureEvent(Event):

    details_template = Template("")

    def __init__(
        self, lecture: Lecture, request: Optional[Request] = None, **kwargs: Any
    ):
        super().__init__(request=request, **kwargs)
        self.lecture = lecture

    @property
    def template_vars(self) -> dict:
        if self.user:
            return {"user": self.user.name, "email": self.user.email}
        return {}

    def render_summary(self) -> str:
        return Markup(self.summary_template.safe_substitute(**self.template_vars))

    def render_details(self) -> str:
        return Markup(self.details_template.safe_substitute(**self.template_vars))


class LectureJournalEvent(LectureEvent):
    def __init__(
        self, lecture: Lecture, request: Optional[Request] = None, **kwargs: Any
    ):
        super().__init__(lecture=lecture, request=request, **kwargs)


class LectureCreee(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "lecture_creee"}
    icon = "document"

    def __init__(self, lecture: Lecture, user: User) -> None:
        super().__init__(lecture=lecture, user=user)

    def apply(self) -> None:
        pass

    def render_summary(self) -> str:
        if self.user is None:
            return Markup("La lecture a été créée.")
        return Markup(
            f"<abbr title='{self.user.email}'>{self.user.name}</abbr>"
            " a créé la lecture."
        )


class TexteMisAJour(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "lecture_texte_mis_a_jour"}
    icon = "document"

    def __init__(self, lecture: Lecture, texte: Texte) -> None:
        super().__init__(
            lecture=lecture, old_value=lecture.texte.numero, new_value=texte.numero
        )
        self.texte = texte

    @property
    def summary_template(self) -> Template:
        old_value = self.data["old_value"]
        new_value = self.data["new_value"]
        return Template(
            f"Le numéro du texte a été mis à jour ({old_value} → {new_value})."
        )

    def apply(self) -> None:
        self.lecture.texte = self.texte


class ArticlesRecuperes(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "articles_recuperes"}
    icon = "document"

    summary_template = Template("Le contenu des articles a été récupéré.")

    def __init__(self, lecture: Lecture) -> None:
        super().__init__(lecture=lecture)

    def apply(self) -> None:
        pass


class AmendementsRecuperes(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "amendements_recuperes"}
    icon = "document"

    @property
    def summary_template(self) -> Template:
        count = self.data["count"]
        if count == 1:
            message = "1 nouvel amendement récupéré."
        else:
            message = f"{count} nouveaux amendements récupérés."
        return Template(message)

    def __init__(self, lecture: Lecture, count: int) -> None:
        super().__init__(lecture=lecture, count=count)

    def apply(self) -> None:
        pass


class AmendementsNonRecuperes(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "amendements_non_recuperes"}
    icon = "document"

    @property
    def summary_template(self) -> Template:
        missings = ", ".join(self.data["missings"])
        return Template(f"Les amendements {missings} n’ont pu être récupérés.")

    def __init__(self, lecture: Lecture, missings: List[str]) -> None:
        super().__init__(lecture=lecture, missings=missings)

    def apply(self) -> None:
        pass


class AmendementsAJour(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "amendements_a_jour"}
    icon = "document"

    summary_template = Template("Les amendements étaient à jour.")

    def __init__(self, lecture: Lecture) -> None:
        super().__init__(lecture=lecture)

    def apply(self) -> None:
        pass


class AmendementsNonTrouves(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "amendements_non_trouves"}
    icon = "document"

    summary_template = Template("Les amendements n’ont pas été trouvés.")

    def __init__(self, lecture: Lecture) -> None:
        super().__init__(lecture=lecture)

    def apply(self) -> None:
        pass


class SharedTableCreee(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "shared_table_creee"}
    icon = "document"

    @property
    def summary_template(self) -> Template:
        titre = self.data["titre"]
        return Template(
            f"<abbr title='$email'>$user</abbr> a créé la corbeille « {titre} »."
        )

    def __init__(self, lecture: Lecture, titre: str, request: Request) -> None:
        super().__init__(lecture=lecture, titre=titre, request=request)

    def apply(self) -> None:
        pass

    @property
    def is_active(self) -> bool:
        return False


class SharedTableRenommee(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "shared_table_renommee"}
    icon = "document"

    @property
    def summary_template(self) -> Template:
        old_titre = self.data["old_titre"]
        new_titre = self.data["new_titre"]
        return Template(
            f"<abbr title='$email'>$user</abbr> a renommé la corbeille."
            f"« {old_titre} » en « {new_titre} »"
        )

    def __init__(
        self, lecture: Lecture, old_titre: str, new_titre: str, request: Request
    ) -> None:
        super().__init__(
            lecture=lecture, old_titre=old_titre, new_titre=new_titre, request=request
        )

    def apply(self) -> None:
        pass

    @property
    def is_active(self) -> bool:
        return False


class SharedTableSupprimee(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "shared_table_supprimee"}
    icon = "document"

    @property
    def summary_template(self) -> Template:
        titre = self.data["titre"]
        return Template(
            f"<abbr title='$email'>$user</abbr> a supprimé la corbeille « {titre} »."
        )

    def __init__(self, lecture: Lecture, titre: str, request: Request) -> None:
        super().__init__(lecture=lecture, titre=titre, request=request)

    def apply(self) -> None:
        pass

    @property
    def is_active(self) -> bool:
        return False


class ChangeUpdateStatus(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "change_update_status"}
    icon = "document"

    @property
    def summary_template(self) -> Template:
        actions = {True: "activé", False: "désactivé"}
        update = self.data["update"]
        action = actions[update]
        if self.user:
            return Template(
                f"<abbr title='$email'>$user</abbr> a {action} "
                f"la synchronisation du dérouleur."
            )
        else:
            return Template(
                f"La synchronisation du dérouleur a été {action}e automatiquement."
            )

    def __init__(self, lecture: Lecture, update: bool, request: Request) -> None:
        super().__init__(lecture=lecture, update=update, request=request)

    def apply(self) -> None:
        pass


class AutomaticDisablingNavette(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "automatic_disabling_navette"}
    icon = "document"

    summary_template = Template(
        "La synchronisation du dérouleur a été désactivée automatiquement suite à navette parlementaire."
    )

    def __init__(self, lecture: Lecture) -> None:
        super().__init__(lecture=lecture)

    def apply(self) -> None:
        pass


class AutomaticDisablingSortAmendements(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "automatic_disabling_sort_amendements"}
    icon = "document"

    summary_template = Template(
        "La synchronisation du dérouleur a été désactivée automatiquement suite à mise à jour des sorts des amendements."
    )

    def __init__(self, lecture: Lecture) -> None:
        super().__init__(lecture=lecture)

    def apply(self) -> None:
        pass


class OrdreDiscussionModified(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "ordre_discussion_modified"}
    icon = "document"

    summary_template = Template(
        "L’ordre de discussion des amendements a été mis à jour."
    )

    def __init__(self, lecture: Lecture) -> None:
        super().__init__(lecture=lecture)

    def apply(self) -> None:
        pass


class AmendementSortUpdateUnbatched(LectureJournalEvent):

    __mapper_args__ = {"polymorphic_identity": "amendement_sort_update_unbatched"}
    icon = "document"

    def __init__(self, lecture: Lecture, amdt_num: str, status: str) -> None:
        super().__init__(
            lecture=lecture, amdt_num=amdt_num, status=status,
        )

    @property
    def summary_template(self) -> Template:
        status = self.data["status"]
        num = self.data["amdt_num"]
        link = self.data.get("link", None)
        if link is not None:
            return Template(
                f'L’amendement <a href="{link}">n°{num}</a> a été désalloti '
                f"car son statut est passé à « {status} »."
            )
        else:
            return Template(
                f"L’amendement n°{num} a été désalloti "
                f"car son statut est passé à « {status} »."
            )

    def apply(self) -> None:
        pass

    def set_amdt_link(self, request: Request) -> None:
        amdt = (
            DBSession.query(Amendement)
            .filter(
                Amendement.lecture_pk == self.lecture.pk,
                Amendement.num == int(self.data["amdt_num"]),
            )
            .one_or_none()
        )
        if amdt is not None:
            self.data["link"] = request.resource_url(
                request.context["amendements"][amdt.num_str], "amendement_edit"
            )


class AmendementArticleUpdateUnbatched(LectureJournalEvent):

    __mapper_args__ = {"polymorphic_identity": "amendement_article_update_unbatched"}
    icon = "document"

    def __init__(self, lecture: Lecture, amdt_num: str, article_num: str) -> None:
        super().__init__(lecture=lecture, amdt_num=amdt_num, article_num=article_num)

    @property
    def summary_template(self) -> Template:
        article = self.data["article_num"]
        num = self.data["amdt_num"]
        link = self.data.get("link", None)
        if link is not None:
            return Template(
                f'L’amendement <a href="{link}">n°{num}</a> a été désalloti '
                f"car déplacé à l'article {article}."
            )
        else:
            return Template(
                f"L’amendement n°{num} a été désalloti "
                f"car déplacé à l'article {article}."
            )

    def apply(self) -> None:
        pass

    def set_amdt_link(self, request: Request) -> None:
        amdt = (
            DBSession.query(Amendement)
            .filter(
                Amendement.lecture_pk == self.lecture.pk,
                Amendement.num == int(self.data["amdt_num"]),
            )
            .one_or_none()
        )
        if amdt is not None:
            self.data["link"] = request.resource_url(
                request.context["amendements"][amdt.num_str], "amendement_edit"
            )


class RefreshLecture(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "refresh_lecture"}
    icon = "document"

    summary_template = Template(
        "<abbr title='$email'>$user</abbr> a demandé un rafraichissement des données."
    )

    def __init__(self, lecture: Lecture, request: Request) -> None:
        super().__init__(lecture=lecture, request=request)

    def apply(self) -> None:
        pass

    @property
    def is_active(self) -> bool:
        return False


class RefreshMissionsSenat(LectureJournalEvent):
    __mapper_args__ = {"polymorphic_identity": "refresh_missions_senat_lecture"}
    icon = "document"

    summary_template = Template("De nouvelles missions ont été récupérées.")

    def __init__(self, lecture: Lecture) -> None:
        super().__init__(lecture=lecture)

    def apply(self) -> None:
        pass
