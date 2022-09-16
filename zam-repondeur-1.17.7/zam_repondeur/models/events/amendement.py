from datetime import datetime
from string import Template
from typing import Any, List, Optional

from lxml.html.diff import htmldiff  # nosec
from markupsafe import Markup
from pyramid.request import Request

from zam_repondeur.services.clean import clean_all_for_search, clean_html
from zam_repondeur.views.jinja2_filters import enumeration

from ..amendement import DOSSIER_DE_BANC, Amendement
from ..batch import Batch
from ..chambre import Chambre
from .base import Event


class AmendementEvent(Event):
    icon = ""

    summary_template = Template("<abbr title='$email'>$user</abbr>")

    def __init__(
        self, amendement: Amendement, request: Optional[Request] = None, **kwargs: Any
    ):
        super().__init__(request=request, **kwargs)
        self.amendement = amendement

    @property
    def template_vars(self) -> dict:
        template_vars = {
            "new_value": self.data["new_value"],
            "old_value": self.data["old_value"],
        }
        if self.user:
            template_vars.update({"user": self.user.name, "email": self.user.email})
        return template_vars

    def render_summary(self) -> str:
        return Markup(self.summary_template.safe_substitute(**self.template_vars))

    def render_details(self) -> str:
        return Markup(
            clean_html(
                htmldiff(
                    self.template_vars["old_value"], self.template_vars["new_value"]
                )
            )
        )


class AmendementRectifie(AmendementEvent):
    __mapper_args__ = {"polymorphic_identity": "amendement_rectifie"}

    icon = "edit"

    summary_template = Template("L’amendement a été rectifié.")

    def __init__(self, amendement: Amendement, rectif: str) -> None:
        super().__init__(
            amendement=amendement, old_value=amendement.rectif, new_value=rectif
        )

    def apply(self) -> None:
        self.amendement.rectif = self.data["new_value"]

    def render_details(self) -> str:
        return ""


class AmendementIrrecevable(AmendementEvent):
    __mapper_args__ = {"polymorphic_identity": "amendement_irrecevable"}

    icon = "document"

    @property
    def summary_template(self) -> Template:  # type: ignore
        chambre = self.amendement.lecture.chambre
        if chambre == Chambre.AN:
            de_qui = "de l’Asssemblée nationale"
        elif chambre == Chambre.SENAT:
            de_qui = "du Sénat"
        else:
            raise ValueError(f"Unsupported chambre {chambre}")
        return Template(
            f"L’amendement a été déclaré irrecevable par les services {de_qui}."
        )

    def __init__(self, amendement: Amendement, sort: str) -> None:
        super().__init__(
            amendement=amendement, old_value=amendement.sort, new_value=sort
        )

    def apply(self) -> None:
        self.amendement.sort = self.data["new_value"]

    def render_details(self) -> str:
        return ""


class AmendementTransfere(AmendementEvent):
    __mapper_args__ = {"polymorphic_identity": "amendement_transfere"}

    icon = "boite"

    def __init__(
        self,
        amendement: Amendement,
        old_value: str,
        new_value: str,
        request: Optional[Request] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            amendement=amendement,
            old_value=old_value,
            new_value=new_value,
            request=request,
            **kwargs,
        )

    @property
    def summary_template(self) -> Template:  # type: ignore
        if self.template_vars["old_value"] and self.template_vars["new_value"]:
            if str(self.user) == self.template_vars["old_value"]:
                summary = (
                    "<abbr title='$email'>$user</abbr> a transféré l’amendement "
                    "à « $new_value »."
                )
            elif str(self.user) == self.template_vars["new_value"]:
                summary = (
                    "<abbr title='$email'>$user</abbr> a transféré l’amendement "
                    "de « $old_value » à lui/elle-même."
                )
            else:
                summary = (
                    "<abbr title='$email'>$user</abbr> a transféré l’amendement "
                    "de « $old_value » à « $new_value »."
                )
        elif self.template_vars["old_value"] and not self.template_vars["new_value"]:
            if self.user:
                if str(self.user) == self.template_vars["old_value"]:
                    summary = (
                        "<abbr title='$email'>$user</abbr> a remis l’amendement "
                        "dans le dérouleur."
                    )
                else:
                    summary = (
                        "<abbr title='$email'>$user</abbr> a remis l’amendement "
                        "de « $old_value » dans le dérouleur."
                    )
            else:
                summary = "L’amendement a été remis automatiquement sur le dérouleur."
        else:
            if str(self.user) == self.template_vars["new_value"]:
                summary = (
                    "<abbr title='$email'>$user</abbr> a mis l’amendement "
                    "sur son espace de travail."
                )
            else:
                summary = (
                    "<abbr title='$email'>$user</abbr> a transféré l’amendement "
                    "à « $new_value »."
                )
        return Template(summary)

    def apply(self) -> None:
        pass

    def render_details(self) -> str:
        return ""


class TransfertDossierDeBanc(AmendementEvent):
    __mapper_args__ = {"polymorphic_identity": "transfert_dossier_de_banc"}

    icon = "boite"

    def __init__(
        self, amendement: Amendement, request: Optional[Request] = None, **kwargs: Any,
    ) -> None:
        super().__init__(
            amendement=amendement, old_value="", new_value="", request=request, **kwargs
        )

    @property
    def summary_template(self) -> Template:  # type: ignore
        summary = (
            "<abbr title='$email'>$user</abbr> a transféré l’amendement "
            f"dans le « {DOSSIER_DE_BANC} »."
        )
        return Template(summary)

    def apply(self) -> None:
        self.amendement.location.user_table = None
        self.amendement.location.shared_table = None
        self.amendement.location.has_ever_been_on_dossier_de_banc = True
        self.amendement.location.date_dossier_de_banc = datetime.utcnow()


class CorpsAmendementModifie(AmendementEvent):
    __mapper_args__ = {"polymorphic_identity": "corps_amendement_modifie"}

    icon = "edit"

    def __init__(self, amendement: Amendement, corps: str, **kwargs: Any) -> None:
        super().__init__(
            amendement=amendement,
            old_value=amendement.corps or "",
            new_value=corps,
            modified=True,
            **kwargs,
        )

    @property
    def summary_template(self) -> Template:  # type: ignore
        action = "modifié" if self.template_vars["old_value"] else "initialisé"
        return Template(f"Le corps de l’amendement a été {action}.")

    def apply(self) -> None:
        self.amendement.corps = self.data["new_value"]
        self.amendement.corps_search = clean_all_for_search(self.data["new_value"])
        if (
            self.amendement.user_content.is_answered
            and not self.amendement.is_abandoned
        ):
            self.amendement.modified = self.data["modified"]


class ExposeAmendementModifie(AmendementEvent):
    __mapper_args__ = {"polymorphic_identity": "expose_amendement_modifie"}
    icon = "edit"

    def __init__(self, amendement: Amendement, expose: str, **kwargs: Any) -> None:
        super().__init__(
            amendement=amendement,
            old_value=amendement.expose or "",
            new_value=expose,
            modified=True,
            **kwargs,
        )

    @property
    def summary_template(self) -> Template:  # type: ignore
        action = "modifié" if self.template_vars["old_value"] else "initialisé"
        return Template(f"L’exposé de l’amendement a été {action}.")

    def apply(self) -> None:
        self.amendement.expose = self.data["new_value"]
        self.amendement.expose_search = clean_all_for_search(self.data["new_value"])
        if (
            self.amendement.user_content.is_answered
            and not self.amendement.is_abandoned
        ):
            self.amendement.modified = self.data["modified"]


class AvisAmendementModifie(AmendementEvent):
    __mapper_args__ = {"polymorphic_identity": "avis_amendement_modifie"}

    icon = "edit"

    def __init__(
        self,
        amendement: Amendement,
        avis: str,
        request: Optional[Request] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            amendement=amendement,
            old_value=amendement.user_content.avis or "",
            new_value=avis,
            request=request,
            **kwargs,
        )

    def apply(self) -> None:
        self.amendement.user_content.avis = self.data["new_value"]
        if self.user:
            user_table = self.user.table_for(self.amendement.lecture)
            if self.amendement not in user_table.user_table_history:
                user_table.user_table_history.append(self.amendement)

    @property
    def summary_template(self) -> Template:  # type: ignore
        if self.template_vars["old_value"]:
            summary = (
                "<abbr title='$email'>$user</abbr> a modifié l’avis "
                "de « $old_value » à « $new_value »."
            )
        else:
            summary = "<abbr title='$email'>$user</abbr> a mis l’avis à « $new_value »."
        return Template(summary)

    def render_details(self) -> str:
        return ""


class ObjetAmendementModifie(AmendementEvent):
    __mapper_args__ = {"polymorphic_identity": "objet_modifie"}

    icon = "edit"

    def __init__(
        self,
        amendement: Amendement,
        objet: str,
        request: Optional[Request] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            amendement=amendement,
            old_value=amendement.user_content.objet or "",
            new_value=objet,
            request=request,
            **kwargs,
        )

    @property
    def summary_template(self) -> Template:  # type: ignore
        action = "modifié" if self.template_vars["old_value"] else "ajouté"
        return Template(f"<abbr title='$email'>$user</abbr> a {action} l’objet.")

    def apply(self) -> None:
        self.amendement.user_content.objet = self.data["new_value"]
        self.amendement.user_content.objet_search = clean_all_for_search(
            self.data["new_value"]
        )
        if self.user:
            user_table = self.user.table_for(self.amendement.lecture)
            if self.amendement not in user_table.user_table_history:
                user_table.user_table_history.append(self.amendement)


class ReponseAmendementModifiee(AmendementEvent):
    __mapper_args__ = {"polymorphic_identity": "reponse_amendement_modifiee"}

    icon = "edit"

    def __init__(
        self,
        amendement: Amendement,
        reponse: str,
        request: Optional[Request] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            amendement=amendement,
            old_value=amendement.user_content.reponse or "",
            new_value=reponse,
            request=request,
            **kwargs,
        )

    @property
    def summary_template(self) -> Template:  # type: ignore
        action = "modifié" if self.template_vars["old_value"] else "ajouté"
        return Template(f"<abbr title='$email'>$user</abbr> a {action} la réponse.")

    def apply(self) -> None:
        self.amendement.user_content.reponse = self.data["new_value"]
        self.amendement.user_content.reponse_search = clean_all_for_search(
            self.data["new_value"]
        )
        if self.user:
            user_table = self.user.table_for(self.amendement.lecture)
            if self.amendement not in user_table.user_table_history:
                user_table.user_table_history.append(self.amendement)


class CommentsAmendementModifie(AmendementEvent):
    __mapper_args__ = {"polymorphic_identity": "comments_amendement_modifie"}

    icon = "edit"

    def __init__(
        self,
        amendement: Amendement,
        comments: str,
        request: Optional[Request] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            amendement=amendement,
            old_value=amendement.user_content.comments or "",
            new_value=comments,
            request=request,
            **kwargs,
        )

    @property
    def summary_template(self) -> Template:  # type: ignore
        action = "modifié les" if self.template_vars["old_value"] else "ajouté des"
        return Template(f"<abbr title='$email'>$user</abbr> a {action} commentaires.")

    def apply(self) -> None:
        self.amendement.user_content.comments = self.data["new_value"]
        self.amendement.user_content.comments_search = clean_all_for_search(
            self.data["new_value"]
        )
        if self.user:
            user_table = self.user.table_for(self.amendement.lecture)
            if self.amendement not in user_table.user_table_history:
                user_table.user_table_history.append(self.amendement)


class ConfirmResponseAmendement(AmendementEvent):
    __mapper_args__ = {"polymorphic_identity": "confirm_response_amendement"}

    icon = "edit"

    def __init__(
        self, amendement: Amendement, request: Optional[Request] = None
    ) -> None:
        super().__init__(
            amendement=amendement, old_value=True, new_value=False, request=request,
        )

    @property
    def summary_template(self) -> Template:  # type: ignore
        return Template(
            f"<abbr title='$email'>$user</abbr> "
            f"a confirmé la réponse et l’avis de l’amendement."
        )

    def apply(self) -> None:
        self.amendement.modified = self.data["new_value"]

    def render_details(self) -> str:
        return ""


class BatchSet(AmendementEvent):
    __mapper_args__ = {"polymorphic_identity": "batch_set"}

    icon = "edit"

    def __init__(
        self,
        amendement: Amendement,
        batch: Batch,
        amendements_nums: List[int],
        request: Request,
        **kwargs: Any,
    ) -> None:
        self.request = request
        others = [
            amendement_num
            for amendement_num in amendements_nums
            if int(amendement_num) != amendement.num
        ]
        super().__init__(
            amendement=amendement, amendements_nums=others, request=request, **kwargs
        )
        self.batch = batch

    def apply(self) -> None:
        if self.amendement.location.batch:
            BatchUnset.create(
                amendement=self.amendement, request=self.request, user=self.user
            )
        self.amendement.location.batch = self.batch

    def render_details(self) -> str:
        return ""

    def render_summary(self) -> str:
        nums = self.data["amendements_nums"]
        if len(nums) == 1:
            siblings = f"l’amendement {nums[0]}"
        else:
            siblings = f"les amendements {enumeration(nums)}"
        return Markup(
            f"<abbr title='{self.user.email}'>{self.user.name}</abbr> a placé "
            f"cet amendement dans un lot avec {siblings}."
        )


class BatchUnset(AmendementEvent):
    __mapper_args__ = {"polymorphic_identity": "batch_unset"}

    icon = "edit"

    def __init__(self, amendement: Amendement, request: Request, **kwargs: Any) -> None:
        self.request = request
        super().__init__(amendement=amendement, request=request, **kwargs)

    def apply(self) -> None:
        batch = self.amendement.location.batch
        if batch is None:
            return

        others = [amdt for amdt in batch.amendements if amdt is not self.amendement]

        # Remove amendement from batch.
        self.amendement.location.batch = None

        # Avoid lonely amendement in a batch.
        if len(others) == 1:
            self.create(amendement=others[0], request=self.request)

    def render_details(self) -> str:
        return ""

    def render_summary(self) -> str:
        if self.user is None:
            return Markup("Cet amendement a été sorti du lot dans lequel il était.")
        return Markup(
            f"<abbr title='{self.user.email}'>{self.user.name}</abbr> a sorti "
            "cet amendement du lot dans lequel il était."
        )
