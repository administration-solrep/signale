import logging
import re
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Dict, Generator, Iterable, Iterator, List, Optional, Set, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup, element

from zam_repondeur.models.phase import ALL_PHASES, Phase
from zam_repondeur.services.fetch.an.dossiers.models import (
    Chambre,
    DossierRef,
    DossierRefsByUID,
    LectureRef,
    TexteRef,
    TypeTexte,
)
from zam_repondeur.services.fetch.http import get_http_session
from zam_repondeur.slugs import slugify

logger = logging.getLogger(__name__)


URL_WWW_SENAT = "www.senat.fr"
BASE_URL_SENAT = f"https://{URL_WWW_SENAT}"
DEPOTS_URL = f"{BASE_URL_SENAT}/akomantoso/depots.xml"
TYPE_TEXTE = ["pjl", "ppl"]


def get_dossier_refs_senat() -> DossierRefsByUID:
    dossier_ids = get_dossiers_id(get_depots_texts())
    dossier_refs = (create_dossier_ref(dossier_id) for dossier_id in dossier_ids)
    dossier_refs_by_uid = {dossier_ref.uid: dossier_ref for dossier_ref in dossier_refs}
    return dossier_refs_by_uid


def download_xml(url: str) -> str:
    http_session = get_http_session()
    resp = http_session.get(url)
    if resp.status_code != HTTPStatus.OK:
        raise RuntimeError(f"Failed to download xml file from {url}")

    content: str = resp.text
    return content


def get_depots_texts() -> Generator[str, None, None]:
    page = download_xml(DEPOTS_URL)
    soup = BeautifulSoup(page, "xml")
    return (url.text for url in soup.find_all("url"))


def get_last_text_from_depots(numero: str) -> Optional[str]:
    try:
        page = download_xml(DEPOTS_URL)
    except RuntimeError:
        return None
    soup = BeautifulSoup(page, "xml")

    textes = sorted(
        (
            datetime.strptime(text.lastModifiedDateTime.text, "%Y-%m-%dT%H:%M:%S"),
            f"{text.url.text}",
        )
        for text in soup.find_all("text")
        if f"{numero}" in text.url.text
    )

    if textes:
        return textes[-1][1]
    return None


def get_dossiers_id(urls: Generator[str, None, None]) -> Generator[str, None, None]:
    dossiers_vu: Set[str] = set()
    for url in urls:
        file_name = url.split("/")[-1]
        if file_name[:3] not in TYPE_TEXTE:
            continue
        xml_file = download_xml(url)
        soup_xml = BeautifulSoup(xml_file, "xml")
        dossier_id = soup_xml.find(
            "FRBRalias", attrs={"name": "signet-dossier-legislatif-senat"}
        )["value"]
        if dossier_id not in dossiers_vu:
            dossiers_vu.add(dossier_id)
            yield dossier_id


def build_webpage_url(dossier_id: str) -> str:
    return urljoin(BASE_URL_SENAT, f"/dossier-legislatif/{dossier_id}.html")


def build_rss_url(dossier_id: str) -> str:
    return urljoin(BASE_URL_SENAT, f"/dossier-legislatif/rss/dosleg{dossier_id}.xml")


def create_dossier_ref(dossier_id: str) -> DossierRef:
    webpage_url = build_webpage_url(dossier_id)
    rss_url = build_rss_url(dossier_id)
    title, lecture_refs = extract_from_rss(dossier_id, rss_url)
    dossier_ref = DossierRef(
        uid=dossier_id,
        titre=title,
        slug=slugify(title),
        an_url="",
        senat_url=webpage_url,
        lectures=lecture_refs,
    )
    return dossier_ref


def extract_from_rss(dossier_id: str, rss_url: str) -> Tuple[str, List[LectureRef]]:
    rss_content = download_rss(rss_url)
    soup = BeautifulSoup(rss_content, "html5lib")

    prefix = len("Sénat - ")
    title = soup.title.string[prefix:]

    lecture_refs: List[LectureRef] = []
    entries = sorted(soup.select("entry"), key=lambda e: e.created.string)  # type: ignore[no-any-return] # noqa
    senat_entries = [
        entry for entry in entries if guess_chambre(entry) == Chambre.SENAT
    ]
    texte_refs = extract_texte_refs(dossier_id, senat_entries)
    lecture_refs = list(extract_lecture_refs(dossier_id, senat_entries, texte_refs))
    return title, lecture_refs


def canonical_senat_url(url: str) -> str:
    # URLs in Sénat's own feeds are actually redirections.
    return url.replace("dossierleg", "dossier-legislatif")


def download_rss(url: str) -> str:
    http_session = get_http_session()
    resp = http_session.get(url)
    if resp.status_code != HTTPStatus.OK:
        raise RuntimeError(f"Failed to download RSS url: {url}")

    content: str = resp.text
    return content


def extract_texte_refs(
    dossier_id: str, entries: Iterable[element.Tag]
) -> Dict[int, TexteRef]:
    textes: Dict[int, TexteRef] = {}
    for entry in entries:
        if entry.title.string.startswith("Texte "):
            texte = create_texte_ref(dossier_id, entry)
            textes[texte.numero] = texte
    return textes


def extract_lecture_refs(
    dossier_id: str, entries: Iterable[element.Tag], textes: Dict[int, TexteRef]
) -> Iterator[LectureRef]:
    for phase in ALL_PHASES:
        parties = _list_parties(dossier_id, phase)
        for partie in parties:
            lecture_commission = find_examen_commission(phase, entries, textes, partie)
            if lecture_commission:
                yield lecture_commission
        texte_initial = lecture_commission.texte if lecture_commission else None
        texte_commission = find_texte_commission(phase, entries, textes)
        texte_examine = texte_commission or texte_initial
        if not texte_examine:
            continue
        for partie in parties:
            yield from find_examens_seance_publique(
                phase, entries, textes, texte_examine, partie
            )


def _list_parties(dossier_id: str, phase: Phase) -> List[Optional[int]]:
    if dossier_id.startswith("pjlf") and phase == Phase.PREMIERE_LECTURE:
        return [1, 2]
    return [None]


def find_texte_commission(
    phase: Phase, entries: Iterable[element.Tag], textes: Dict[int, TexteRef]
) -> Optional[TexteRef]:
    for entry in entries:
        if extract_phase(entry) != phase:
            continue
        if is_texte_initial(entry.summary.string):
            continue

        num_texte = extract_texte_num(
            entry.title.string, regexp=r"Texte de la commission n°\s*(\d+)"
        )
        if not num_texte:
            continue

        return textes[num_texte]
    return None


def find_examen_commission(
    phase: Phase,
    entries: Iterable[element.Tag],
    textes: Dict[int, TexteRef],
    partie: Optional[int],
) -> Optional[LectureRef]:
    for entry in entries:
        if not entry.title.string.startswith("Texte n°"):
            continue

        if extract_phase(entry) != phase:
            continue

        if not is_texte_initial(entry.summary.string):
            continue

        num_texte = extract_texte_num(entry.title.string)
        if not num_texte:
            continue

        texte = textes[num_texte]

        return LectureRef(
            chambre=Chambre.SENAT,
            phase=phase,
            titre=f"{_PHASE_TO_STR[phase]} – Commissions",
            organe="",
            texte=texte,
            partie=partie,
        )
    return None


def find_examens_seance_publique(
    phase: Phase,
    entries: Iterable[element.Tag],
    textes: Dict[int, TexteRef],
    texte_examine: TexteRef,
    partie: Optional[int],
) -> List[LectureRef]:
    lecture_refs = list(
        find_amendements_seance_publique(phase, entries, textes, partie)
    )
    if lecture_refs:
        return lecture_refs
    # default: séance publique will look at initial texte
    return [
        LectureRef(
            chambre=Chambre.SENAT,
            phase=phase,
            titre=f"{_PHASE_TO_STR[phase]} – Séance publique",
            organe="PO78718",
            texte=texte_examine,
            partie=partie,
        )
    ]


def find_amendements_seance_publique(
    phase: Phase,
    entries: Iterable[element.Tag],
    textes: Dict[int, TexteRef],
    partie: Optional[int],
) -> Iterator[LectureRef]:
    for entry in entries:
        if extract_phase(entry) != phase:
            continue

        num_texte = extract_texte_num(
            entry.title.string, regexp=r"Amendements déposés sur le texte n°\s*(\d+)"
        )
        if not num_texte:
            continue

        texte = textes[num_texte]

        yield LectureRef(
            chambre=Chambre.SENAT,
            phase=phase,
            titre=f"{_PHASE_TO_STR[phase]} – Séance publique",
            organe="PO78718",
            texte=texte,
            partie=partie,
        )


def extract_texte_num(title: str, regexp: str = r"Texte n°\s*(\d+)") -> int:
    mo = re.search(regexp, title)
    if mo is None:
        return 0

    return int(mo.group(1))


def extract_phase(entry: element.Tag) -> Optional[Phase]:
    phase = entry.summary.string.split(" - ", 1)[0]
    return _STR_TO_PHASE.get(phase, None)


_STR_TO_PHASE = {
    "Première lecture": Phase.PREMIERE_LECTURE,
    "Deuxième lecture": Phase.DEUXIEME_LECTURE,
    "Nouvelle lecture": Phase.NOUVELLE_LECTURE,
    "Lecture définitive": Phase.LECTURE_DEFINITIVE,
}


_PHASE_TO_STR = {
    Phase.PREMIERE_LECTURE: "Première lecture",
    Phase.DEUXIEME_LECTURE: "Deuxième lecture",
    Phase.NOUVELLE_LECTURE: "Nouvelle lecture",
    Phase.LECTURE_DEFINITIVE: "Lecture définitive",
}


def is_texte_initial(summary: str) -> bool:
    if re.search("(transmis|déposé) au Sénat le", summary):
        return True
    if re.search(r"Texte (résultat des travaux )?de la commission", summary):
        return False
    logger.warning(f"Not sure if texte initial or commission: {summary}")
    return False


def create_texte_ref(dossier_id: str, entry: element.Tag) -> TexteRef:
    numero = entry.title.string.split(" n° ", 1)[1]
    type_dict = {
        "ppr": TypeTexte.PROPOSITION,
        "ppl": TypeTexte.PROPOSITION,
        "pjl": TypeTexte.PROJET,
        "plf": TypeTexte.PROJET,  # plfss
    }
    type_ = dossier_id[:3]
    # One day is added considering we have to deal with timezones
    # and we only need the date.
    # E.g.: 2019-05-21T22:00:00Z
    datetime_depot = datetime.strptime(entry.created.string, "%Y-%m-%dT%H:%M:%SZ")
    date_depot = datetime_depot.date() + timedelta(days=1)
    uid = f"{type_.upper()}SENAT{date_depot.year}X{numero}"
    return TexteRef(
        uid=uid,
        type_=type_dict[type_],
        chambre=Chambre.SENAT,
        legislature=None,
        numero=int(numero),
        titre_long="",
        titre_court="",
        date_depot=date_depot,
    )


def guess_chambre(entry: element.Tag) -> Optional[Chambre]:
    entry_id = entry.id.string or ""

    if entry_id in URL_WWW_SENAT:
        return Chambre.SENAT

    if re.search(r"www2?\.assemblee-nationale\.fr", entry_id):
        return Chambre.AN

    if "Texte transmis à l'Assemblée nationale" in entry.summary.string:
        return Chambre.AN

    if entry.summary.string.startswith("Commission mixte paritaire"):
        return None

    # Fallback on Senat given sometimes URLs are relative.
    return Chambre.SENAT
