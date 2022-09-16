import os
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional, Tuple

from pyramid.httpexceptions import HTTPBadRequest, HTTPFound
from pyramid.request import Request
from pyramid.response import FileResponse, Response
from pyramid.view import view_config, view_defaults
from sqlalchemy import and_, func, not_, or_
from sqlalchemy.orm import Query, joinedload, load_only, subqueryload

from zam_repondeur.data_sanitize import sanitize_string
from zam_repondeur.message import Message
from zam_repondeur.models import Amendement, Article, Batch, DBSession, Lecture
from zam_repondeur.models.amendement import AVIS, SEARCHING_SORTS, AmendementUserContent
from zam_repondeur.resources import (
    AmendementCollection,
    LectureResource,
    RechercheCollection,
)
from zam_repondeur.services.clean import (
    clean_accents,
    decode_special_car,
    encode_special_car,
)
from zam_repondeur.services.import_export.xlsx import export_xlsx


@view_config(context=AmendementCollection, renderer="lecture_index.html")
def lecture_index(context: AmendementCollection, request: Request) -> dict:
    """
    The index lists all amendements in a lecture
    """
    lecture = context.parent.model(
        subqueryload("articles").defer("content"),
        subqueryload("amendements").options(
            load_only(
                "article_pk",
                "auteur",
                "id_identique",
                "lecture_pk",
                "mission_titre",
                "mission_titre_court",
                "num",
                "parent_pk",
                "position",
                "rectif",
                "sort",
                "modified",
            ),
            joinedload("user_content").load_only(
                "avis", "has_reponse", "objet", "reponse_hash"
            ),
            joinedload("location").options(
                subqueryload("batch")
                .joinedload("amendements_locations")
                .joinedload("amendement")
                .load_only("num", "rectif"),
                subqueryload("shared_table").load_only("titre"),
                subqueryload("user_table")
                .joinedload("user")
                .load_only("email", "name"),
            ),
        ),
    )
    object_articles_sorted = sorted(lecture.articles)

    # Récupération du bouton de switch pour la pagination
    if "hidden-switch" in request.POST:
        switch = request.POST.get("hidden-switch")
        request.session[f"seuil_dossier_{lecture.dossier.pk}"] = f"{switch}"

    infos_pagination = set_pagination(
        request=request,
        active_seuil=request.session.get(f"seuil_dossier_{lecture.dossier.pk}"),
        amendements=lecture.amendements,
        seuil=request.registry.settings["zam.seuil_pagination"],
        object_articles_sorted=object_articles_sorted,
        article_session=request.session.get(f"article_lecture_{lecture.pk}", ""),
        lecture_pk=lecture.pk,
    )

    sort_key, reverse = get_sort_config(request)

    return {
        "lecture": lecture,
        "all_amendements": lecture.amendements,
        "amendements_onpage": infos_pagination["all_amendements"],
        "main_amendements": Batch.collapsed_batches(
            infos_pagination["all_amendements"]
        ),
        "sort_key": sort_key,
        "reverse": reverse,
        "articles": object_articles_sorted,
        "article_title": infos_pagination["article_title"],
        "progress_url": request.resource_url(context.parent, "progress_status"),
        "page": infos_pagination["page"],
        "articles_titre_nums": infos_pagination["articles_titre_nums"],
        "affichage_pagination": infos_pagination["pagination"],
        "pagination_data": infos_pagination["pagination_data"],
        "dossier_resource": context.parent.dossier_resource,
        "current_tab": "index",
        "contact_mailto": f"mailto:{get_contacts_coordinateurs(request, lecture)}",
    }


@view_config(context=RechercheCollection, renderer="lecture_search.html")
def lecture_index_search(context: RechercheCollection, request: Request) -> dict:
    """
    The index lists all amendements in a lecture
    """
    lecture_resource = context.parent
    lecture = lecture_resource.model(
        subqueryload("articles").defer("content"),
        subqueryload("amendements").options(
            load_only(
                "article_pk",
                "auteur",
                "matricule",
                "groupe",
                "id_identique",
                "lecture_pk",
                "mission_titre",
                "mission_titre_court",
                "num",
                "parent_pk",
                "position",
                "rectif",
                "sort",
            ),
            joinedload("user_content").load_only(
                "avis", "has_reponse", "objet", "reponse_hash"
            ),
            joinedload("location").options(
                subqueryload("batch")
                .joinedload("amendements_locations")
                .joinedload("amendement")
                .load_only("num", "rectif"),
                subqueryload("shared_table").load_only("titre"),
                subqueryload("user_table")
                .joinedload("user")
                .load_only("email", "name"),
            ),
        ),
    )
    object_articles_sorted = sorted(lecture.articles)

    champs_simples = {
        "expose": Amendement.expose_search,
        "corps": Amendement.corps_search,
        "objet": AmendementUserContent.objet_search,
        "reponse": AmendementUserContent.reponse_search,
        "commentaires": AmendementUserContent.comments_search,
    }
    sorts = sorted(list(SEARCHING_SORTS.values()))
    champs_multiple = {
        "auteurs": (Amendement.auteur, get_all_authors(lecture)),
        "groupes": (Amendement.groupe, get_all_groupes(lecture)),
        "sorts": (Amendement.sort, sorts),
        "positions": (AmendementUserContent.avis, AVIS),
    }

    if "redo_search" in request.POST or "recherche-button" in request.POST:
        all_champs = [c for c in champs_simples.keys()] + [
            c for c in champs_multiple.keys()
        ]
        for champ in all_champs:
            delete_search_session(request, lecture, champ)

    # Récupération du bouton de switch pour la pagination
    if "hidden-switch" in request.POST:
        switch = request.POST.get("hidden-switch")
        request.session[f"seuil_dossier_{lecture.dossier.pk}"] = f"{switch}"

    # Construction de la query de la recherche en cours
    query = (
        DBSession.query(Amendement)
        .options(
            load_only(
                "article_pk",
                "auteur",
                "id_identique",
                "lecture_pk",
                "mission_titre",
                "mission_titre_court",
                "num",
                "parent_pk",
                "position",
                "rectif",
                "sort",
            ),
            joinedload("location").options(
                subqueryload("batch")
                .joinedload("amendements_locations")
                .joinedload("amendement")
                .load_only("num", "rectif"),
                subqueryload("shared_table").load_only("titre"),
                subqueryload("user_table")
                .joinedload("user")
                .load_only("email", "name"),
            ),
        )
        .filter(Amendement.pk == AmendementUserContent.amendement_pk)
    )

    # Création de la requète de recherche
    # On filtre sur les amendements de la lecture
    query = query.filter(Amendement.lecture_pk == lecture.pk)
    active_search: int = 0
    search_values: Dict[str, Optional[List[str]]] = {}

    for champ, column in champs_simples.items():
        query, active_search, search_values = set_simple_filtre(
            request, lecture, query, active_search, champ, column, search_values,
        )

    for champ, element in champs_multiple.items():
        query, active_search, search_values = set_multiple_filtre(
            request,
            lecture,
            query,
            active_search,
            champ,
            element[0],
            element[1],
            search_values,
        )

    if "recherche-button" in request.POST:
        active_search += 1

    amendements = query.all()
    infos_pagination = set_pagination(
        request=request,
        active_seuil=request.session.get(f"seuil_dossier_{lecture.dossier.pk}"),
        amendements=amendements,
        seuil=request.registry.settings["zam.seuil_pagination"],
        object_articles_sorted=object_articles_sorted,
        article_session=request.session.get(f"article_lecture_{lecture.pk}", ""),
        lecture_pk=lecture.pk,
    )

    sort_key, reverse = get_sort_config(request)

    return {
        "lecture": lecture,
        "all_amendements": amendements,
        "amendements_onpage": infos_pagination["all_amendements"],
        "main_amendements": infos_pagination["all_amendements"],
        "sort_key": sort_key,
        "reverse": reverse,
        "articles": object_articles_sorted,
        "article_title": infos_pagination["article_title"],
        "progress_url": request.resource_url(context.parent, "progress_status"),
        "page": infos_pagination["page"],
        "articles_titre_nums": infos_pagination["articles_titre_nums"],
        "affichage_pagination": infos_pagination["pagination"],
        "pagination_data": infos_pagination["pagination_data"],
        "dossier_resource": context.parent.dossier_resource,
        "current_tab": "search",
        "contact_mailto": f"mailto:{get_contacts_coordinateurs(request, lecture)}",
        "avis": AVIS,
        "sort": sorts,
        "auteurs": get_all_authors(lecture),
        "groupes": get_all_groupes(lecture),
        "active_search": active_search,
        "search_values": search_values,
    }


def get_simple_search(
    request: Request, lecture: Lecture, libelle: str
) -> Optional[str]:
    if libelle in request.POST and request.POST[libelle]:
        value = encode_special_car(sanitize_string(request.POST[libelle]))
        request.session[f"{libelle}_lecture_{lecture.pk}"] = f"{value}"
        return str(request.session.get(f"{libelle}_lecture_{lecture.pk}"))
    elif request.session.get(f"{libelle}_lecture_{lecture.pk}"):
        return str(request.session.get(f"{libelle}_lecture_{lecture.pk}"))
    return None


def get_exact_search(request: Request, lecture: Lecture, libelle: str) -> Optional[str]:
    if f"exact-search-{libelle}" in request.POST:
        request.session[f"{libelle}_exact_search_lecture_{lecture.pk}"] = 1
        return str(request.session.get(f"{libelle}_exact_search_lecture_{lecture.pk}"))
    elif request.session.get(f"{libelle}_exact_search_lecture_{lecture.pk}"):
        return str(request.session.get(f"{libelle}_exact_search_lecture_{lecture.pk}"))
    return None


def get_multiple_search(
    request: Request, lecture: Lecture, libelle: str
) -> Optional[List[str]]:
    if libelle in request.POST and request.POST.getall(libelle):
        request.session[f"{libelle}_lecture_{lecture.pk}"] = ";".join(
            sanitize_string(element) for element in request.POST.getall(libelle)
        )
        return list(request.session.get(f"{libelle}_lecture_{lecture.pk}").split(";"))
    elif request.session.get(f"{libelle}_lecture_{lecture.pk}"):
        return list(request.session.get(f"{libelle}_lecture_{lecture.pk}").split(";"))
    return None


def set_simple_filtre(
    request: Request,
    lecture: Lecture,
    query: Query,
    active_search: int,
    libelle: str,
    column: Optional[str],
    search_values: Dict[str, Optional[List[str]]],
) -> Tuple[Query, int, Dict[str, Optional[List[str]]]]:
    value = get_simple_search(request, lecture, libelle)
    is_exact_search = get_exact_search(request, lecture, libelle)

    if value is not None:
        if is_exact_search:
            query = query.filter(
                column.ilike(f"%{value}%")  # type: ignore
            )
            search_values[f"exact-search-{libelle}"] = ["checked"]
        else:
            terms = value.split(" ")
            query = query.filter(
                and_(
                    column.ilike(f"%{term}%")  # type: ignore
                    for term in terms
                )
            )

        active_search += 1
        search_values[libelle] = [decode_special_car(value)]
    else:
        search_values[libelle] = None
    return query, active_search, search_values


def set_multiple_filtre(
    request: Request,
    lecture: Lecture,
    query: Query,
    active_search: int,
    libelle: str,
    column: Optional[str],
    list_of_values: List[str],
    search_values: Dict[str, Optional[List[str]]],
) -> Tuple[Query, int, Dict[str, Optional[List[str]]]]:
    values = get_multiple_search(request, lecture, libelle)
    search_values[libelle] = [value for value in values] if values is not None else None
    if values is not None:
        if "aucun" in values or "autres" in values:
            if "aucun" in values:
                values.remove("aucun")
            elif "autres" in values:
                values.remove("autres")

            query = query.filter(
                or_(
                    column.is_(None),  # type: ignore
                    and_(
                        not_(column.ilike(f"%{elt}%"))  # type: ignore
                        for elt in list_of_values
                        if elt.lower() not in values
                    ),
                )
            )
        else:
            if "sorts" in libelle:
                query = query.filter(
                    or_(
                        column.ilike(f"%{value}%")  # type: ignore
                        for value in values
                    )
                )
            else:
                query = query.filter(
                    or_(func.lower(column) == value for value in values)
                )

        active_search += 1
    return query, active_search, search_values


def delete_search_session(request: Request, lecture: Lecture, libelle: str) -> None:
    if request.session.get(f"{libelle}_lecture_{lecture.pk}"):
        del request.session[f"{libelle}_lecture_{lecture.pk}"]
    if request.session.get(f"{libelle}_exact_search_lecture_{lecture.pk}"):
        del request.session[f"{libelle}_exact_search_lecture_{lecture.pk}"]


def get_all_authors(lecture: Lecture) -> List[str]:
    auteurs = [
        a.auteur for a in lecture.amendements if a.auteur is not None and a.auteur != ""
    ]
    auteurs_distinct = list(set(auteurs))
    auteurs_distinct.sort(key=lambda x: get_name_author(x))  # type: ignore[arg-type,return-value] # noqa
    return auteurs_distinct


def get_all_groupes(lecture: Lecture) -> List[str]:
    groupes = [
        a.groupe for a in lecture.amendements if a.groupe is not None and a.groupe != ""
    ]
    groupes_distinct = list(set(groupes))
    return sorted(groupes_distinct)


def get_name_author(auteur: Optional[str]) -> Optional[str]:
    if auteur is not None:
        auteur_cleaned = clean_accents(auteur.lower())
        return (
            auteur_cleaned.replace("m. ", "", 1)
            .replace("mme ", "", 1)
            .replace("mr ", "", 1)
            if auteur_cleaned.startswith(("mr ", "m. ", "mme "))
            else auteur_cleaned
        )
    return auteur


def paginate(
    active_seuil: str,
    amendements: List[Amendement],
    seuil: str,
    object_articles_sorted: List[Article],
) -> bool:
    if active_seuil is None:
        if object_articles_sorted:
            return len(amendements) >= int(seuil)
    else:
        if int(active_seuil) != 0 and amendements:
            return True
    return False


def get_sort_config(request: Request) -> Tuple[str, bool]:

    # Récupération de la clef pour le tri
    sort_key = request.GET.get("sort_key", "sort_key")
    reverse = bool(request.GET.get("reverse", False))

    # Vérification que la clef de tri est autorisée
    if sort_key not in ["num", "sort_key"]:
        sort_key = "sort_key"

    return (sort_key, reverse)


def set_pagination(
    request: Request,
    active_seuil: str,
    amendements: List[Amendement],
    seuil: str,
    object_articles_sorted: List[Article],
    article_session: str,
    lecture_pk: int,
) -> Dict[str, Any]:
    pagination = paginate(active_seuil, amendements, seuil, object_articles_sorted)
    if pagination:
        try:
            type_, num, mult, pos = request.GET.get(
                "article_derouleur", article_session
            ).split(".")
        except Exception:
            # Par défaut sur l'article liminaire
            type_, num, mult, pos = ("article", "0", "", "")

        # Requéte pour récupérer les articles de la lecture possédant
        # au moins un amendement
        non_empty_articles_query = DBSession.query(Article).filter(
            Article.lecture_pk == lecture_pk,
            Amendement.article_pk == Article.pk,
            Article.pk.in_(amdt.article_pk for amdt in amendements),  # type: ignore
        )

        current_article = non_empty_articles_query.filter(
            Article.type == type_,
            Article.num == num,
            Article.mult == mult,
            Article.pos == pos,
        ).first()

        # Tri des articles
        non_empty_articles_sorted = sorted(non_empty_articles_query.all())

        # Si pas d'article courant on prend le premier
        if not current_article:
            current_article = non_empty_articles_sorted[0]

        articles_titre_nums = [
            (str(article) or "Retiré", f"{article.url_key}")
            for article in non_empty_articles_sorted
        ]

        request.session[f"article_lecture_{lecture_pk}"] = f"{current_article.url_key}"
        page = non_empty_articles_sorted.index(current_article)

        article_amendements = [
            amdt for amdt in amendements if amdt.article_pk == current_article.pk
        ]

        return {
            "pagination_data": {
                "previous": get_previous(page, articles_titre_nums),
                "first": get_first(page, articles_titre_nums),
                "first_elipse": page > 2,
                "pages": get_pages(page, articles_titre_nums),
                "last_elipse": len(articles_titre_nums) - page - 1 > 2,
                "last": get_last(page, articles_titre_nums),
                "next": get_next(page, articles_titre_nums),
            },
            "all_amendements": sorted(article_amendements),
            "page": page,
            "articles_titre_nums": articles_titre_nums,
            "article_title": current_article.format(short=False),
            "pagination": pagination,
        }
    else:
        return {
            "pagination_data": {},
            "all_amendements": sorted(amendements),
            "page": 0,
            "articles_titre_nums": [],
            "article_title": "",
            "pagination": pagination,
        }


def get_first(page: int, articles_titre_nums: List[Tuple[str, str]]) -> Optional[dict]:
    if page < 2:
        return None
    titre, num = articles_titre_nums[0]
    return {
        "param": "article_derouleur",
        "value": f"{num}",
        "label": titre,
    }


def get_last(page: int, articles_titre_nums: List[Tuple[str, str]]) -> Optional[dict]:
    if len(articles_titre_nums) - page - 1 < 2:
        return None
    titre, num = articles_titre_nums[-1]
    return {
        "param": "article_derouleur",
        "value": f"{num}",
        "label": titre,
    }


def get_next(page: int, articles_titre_nums: List[Tuple[str, str]]) -> Optional[dict]:
    if page == len(articles_titre_nums) - 1:
        return None
    titre, num = articles_titre_nums[page + 1]
    return {
        "param": "article_derouleur",
        "value": f"{num}",
        "title": "Article suivant",
    }


def get_previous(
    page: int, articles_titre_nums: List[Tuple[str, str]]
) -> Optional[dict]:
    if page == 0:
        return None
    titre, num = articles_titre_nums[page - 1]
    return {
        "param": "article_derouleur",
        "value": f"{num}",
        "title": "Article précédent",
    }


def get_pages(
    page: int, articles_titre_nums: List[Tuple[str, str]], page_range: int = 1,
) -> List[dict]:
    index_min = 0
    index_max = len(articles_titre_nums)

    range_min = max(page - page_range, index_min)
    range_max = min(page + page_range + 1, index_max)

    pages = []
    for i in range(range_min, range_max):
        titre, num = articles_titre_nums[i]
        pages.append(
            {
                "param": "article_derouleur",
                "value": f"{num}",
                "label": titre,
                "current": i == page,
            }
        )
    return pages


def get_contacts_coordinateurs(request: Request, lecture: Lecture) -> Any:
    contact_emails = request.registry.settings["zam.contact_mail"]
    if lecture.dossier.team.coordinators:
        contact_emails = ";".join(
            contact.email for contact in lecture.dossier.team.coordinators
        )
    return contact_emails


@view_defaults(context=LectureResource, name="download_search")
class SearchExport:
    def __init__(self, context: LectureResource, request: Request) -> None:
        self.context = context
        self.request = request
        self.lecture = self.context.model()

    @view_config(request_method="POST")
    def post(self) -> Response:
        amendements: List[int] = self.request.POST.getall("nums")
        if not amendements:
            self.request.session.flash(
                Message(
                    cls="danger",
                    text="Erreur : Il faut au moins un résultat "
                    "pour effectuer l'export.",
                )
            )
            return HTTPFound(
                location=self.request.resource_url(self.context, "recherche")
            )

        download_formats = {
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }

        fmt: str = self.request.POST.get("format", "")
        if fmt not in download_formats.keys():
            raise HTTPBadRequest(f'Invalid value "{fmt}" for "format" param')

        query = (
            DBSession.query(Amendement)
            .options(
                joinedload("user_content"),
                joinedload("location").options(
                    joinedload("user_table")
                    .joinedload("user")
                    .load_only("email", "name")
                ),
                joinedload("article").options(
                    load_only("lecture_pk", "mult", "num", "pos", "type"),
                    joinedload("user_content"),
                ),
            )
            .filter(
                Amendement.lecture_pk == self.lecture.pk,
                or_(Amendement.num == amendement for amendement in amendements),
            )
        )

        with NamedTemporaryFile() as file_:
            tmp_file_path = os.path.abspath(file_.name)

            export_xlsx(filename=tmp_file_path, amendements=query.all())

            response = FileResponse(tmp_file_path)
            attach_name = (
                f"recherche-lecture-{self.lecture.chambre}-{self.lecture.texte.numero}-"
                f"{self.lecture.organe}.{fmt}"
            )
            response.content_type = download_formats[fmt]
            response.headers[
                "Content-Disposition"
            ] = f'attachment; filename="{attach_name}"'
            return response
