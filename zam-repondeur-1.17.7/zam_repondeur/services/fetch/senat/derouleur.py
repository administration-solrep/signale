import logging
from http import HTTPStatus
from typing import Any, Dict, Iterable, Iterator, List, NamedTuple, Optional, Tuple

from zam_repondeur.exceptions.alert import AlertOnData
from zam_repondeur.models import Amendement, Lecture
from zam_repondeur.services.fetch.http import get_http_session

from ..missions import MissionRef

BASE_URL = "https://www.senat.fr"


logger = logging.getLogger(__name__)


class DiscussionDetails(NamedTuple):
    num: int
    position: int
    id_discussion_commune: Optional[int]
    id_identique: Optional[int]
    parent_num: Optional[int]
    mission_ref: Optional[MissionRef]


def fetch_and_parse_discussion_details(lecture: Lecture) -> List[DiscussionDetails]:
    data_iter = _fetch_discussion_details(lecture)
    return _parse_derouleur_data(data_iter)


def _fetch_discussion_details(lecture: Lecture) -> Iterator[Tuple[Any, MissionRef]]:
    """
    Récupère les amendements à discuter, dans l'ordre de passage

    NB : les amendements jugés irrecevables ne sont pas inclus.
    """
    http_session = get_http_session()
    for url, mission_ref in derouleur_urls_and_mission_refs(lecture):
        resp = http_session.get(url)
        if resp.status_code in (
            HTTPStatus.NOT_FOUND,
            HTTPStatus.GATEWAY_TIMEOUT,
        ):  # 404, 504
            logger.warning(f"Could not fetch {url}")
            continue
        if resp.text == "":
            logger.warning(f"Empty response for {url}")
            continue
        if resp.status_code != HTTPStatus.OK:
            logger.warning(
                f"Impossible de récuprérer les données de l'url \
{url} du SENAT"
            )
            raise AlertOnData(
                f"Impossible de récupérer les données de l'url \
{url} du SENAT code http:{resp.status_code}",
                "http",
                resp.status_code,
                url=url,
            )
        if resp.text == "":
            logger.warning(f"Empty response for {url}")
            continue
        try:
            json_data = resp.json()
        except Exception as exception:
            logger.error(f"Impossible de récupérer les données de {url}, {exception}")
            raise AlertOnData(
                f"Erreur lors de la lecture du json SENAT: {url}", "data", 1, url=url,
            ) from exception
        yield json_data, mission_ref


def _parse_derouleur_data(
    data_iter: Iterable[Tuple[Any, MissionRef]]
) -> List[DiscussionDetails]:
    subdivs_amends_mission_refs = [
        (subdiv, amend, mission_ref)
        for data, mission_ref in data_iter
        for subdiv in data["Subdivisions"]
        for amend in subdiv["Amendements"]
    ]

    uid_map: Dict[str, int] = {
        amend["idAmendement"]: Amendement.parse_num(amend["num"])[0]
        for _, amend, _ in subdivs_amends_mission_refs
    }

    discussion_details = [
        parse_discussion_details(uid_map, amend, position, mission_ref)
        for position, (subdiv, amend, mission_ref) in enumerate(
            subdivs_amends_mission_refs, start=1
        )
    ]

    return discussion_details


def derouleur_urls_and_mission_refs(
    lecture: Lecture,
) -> Iterator[Tuple[str, MissionRef]]:
    assert lecture.texte.session_str is not None  # nosec (mypy hint)
    phase = "commission" if lecture.is_commission else "seance"
    if lecture.missions_senat:
        for mission in lecture.missions_senat:
            yield (
                f"{BASE_URL}/en{phase}/{lecture.texte.session_str}"
                f"/{lecture.texte.numero}/liste_discussion_{mission.id_texte}.json",
                MissionRef(titre=mission.titre, titre_court=mission.titre_court),
            )
    else:
        yield (
            f"{BASE_URL}/en{phase}/{lecture.texte.session_str}"
            f"/{lecture.texte.numero}/liste_discussion.json",
            MissionRef(titre="", titre_court=""),
        )


def parse_discussion_details(
    uid_map: Dict[str, int], amend: dict, position: int, mission_ref: MissionRef
) -> DiscussionDetails:
    num, rectif = Amendement.parse_num(amend["num"])
    details = DiscussionDetails(
        num=num,
        position=position,
        id_discussion_commune=(
            int(amend["idDiscussionCommune"])
            if parse_bool(amend["isDiscussionCommune"])
            else None
        ),
        id_identique=(
            int(amend["idIdentique"]) if parse_bool(amend["isIdentique"]) else None
        ),
        parent_num=get_parent_num(uid_map, amend),
        mission_ref=mission_ref if mission_ref.titre else None,
    )
    return details


def parse_bool(text: str) -> bool:
    if text == "true":
        return True
    if text == "false":
        return False
    raise ValueError


def get_parent_num(uid_map: Dict[str, int], amend: dict) -> Optional[int]:
    if (
        "isSousAmendement" in amend
        and parse_bool(amend["isSousAmendement"])
        and "idAmendementPere" in amend
    ):
        parent_uid = amend["idAmendementPere"]
        if parent_uid in uid_map:
            return uid_map[parent_uid]
        else:
            logger.warning("Unknown parent amendement %s", parent_uid)
    return None
