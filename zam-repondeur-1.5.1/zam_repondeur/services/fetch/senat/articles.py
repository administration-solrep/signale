import logging
from http import HTTPStatus
from typing import Any, Dict, List, Tuple

from bs4 import BeautifulSoup, element

from zam_repondeur.models.division import DIVISIONS
from zam_repondeur.models.mentions import (
    M_DEL,
    M_NO_MAJ,
    MENTIONS_DEL,
    MENTIONS_DEL_MAJ,
)
from zam_repondeur.services.clean import (
    clean_characters,
    clean_html_except_tables,
    clean_line_break_br,
    clean_line_break_n,
    clean_mention,
    clean_mention_at_end,
    clean_special_car,
)
from zam_repondeur.services.fetch.division import (
    conversion_romain_arabe,
    is_romain,
    remove_accents,
)
from zam_repondeur.services.fetch.http import get_http_session

DATA_MENTION = "data:mention"
TYPE_ARTICLE = "article"
TYPE_TEXTE = "texte"
SOUS_TYPE_ETAT = "etat"
dict_adj_numeral = {
    "PREMIER": 1,
    "PREMIERE": 1,
    "IER": 1,
    "UNIQUE": 1,
    "SECOND": 2,
    "SECONDE": 2,
}

logger = logging.getLogger(__name__)


def parse_akn(url: str) -> List[Dict]:
    akn_content = download_akn_xml(url)
    content = clean_line_break_br(akn_content)
    articles = get_articles(content)
    return articles


def download_akn_xml(url: str) -> str:
    http_session = get_http_session()
    resp = http_session.get(url)
    if resp.status_code != HTTPStatus.OK:
        raise RuntimeError(f"Failed to download AKN texte {url} from senat.fr")

    content: str = resp.content.decode("utf-8")
    return content


def get_articles(akn_content: str) -> List[Dict]:
    soup = BeautifulSoup(akn_content, "xml")
    articles = soup.find_all("article")
    list_articles = []

    titre_text = get_title_text(soup)
    if titre_text:
        list_articles.append(titre_text)

    for order, article in enumerate(articles, 1):
        etat = article.get("class")
        if etat is None or etat != SOUS_TYPE_ETAT:
            section = get_section_article(article.parent)
            get_article = extract_article(article, order, section)
            list_articles.append(get_article)
        logger.info("Récupération de l'article GUID {}".format(article.get("GUID", "")))

    return list_articles


def get_title_text(soup: BeautifulSoup) -> Dict[str, str]:
    dict_titre = dict()
    titre = soup.find("docTitle")
    if titre is not None:
        dict_titre["titre"] = titre.text.lower()
        dict_titre["type"] = TYPE_TEXTE
    return dict_titre


def extract_article(article: element.Tag, order: int, section: str) -> Dict[str, Any]:
    dict_article: Dict[str, Any] = dict()
    dict_article["type"] = TYPE_ARTICLE
    dict_article["order"] = order
    dict_article["alineas"] = get_alineas_article(article)
    dict_article["statut"] = get_status_article(article)
    dict_article["titre"] = get_title_article(article)

    logger.info("Titre de l'article: {}".format(get_title_article(article)))

    if section:
        dict_article["section"] = section

    return dict_article


def get_section_article(parent: element.Tag) -> str:
    id_parent = parent.get("eId", "")
    section = str()
    if id_parent != "":
        divisions = id_parent.split("__")[::-1]
        for division in divisions:
            div_split = division.split("_")
            if div_split[0] in DIVISIONS:
                for i, el in enumerate(div_split):
                    if i == 0:
                        section = section + DIVISIONS[el]
                    else:
                        for x, nom in enumerate(el.split(" ")):
                            if x == 0:
                                if nom.isnumeric():
                                    objet = nom
                                else:
                                    nom_maj = remove_accents(nom).upper()
                                    if is_romain(nom_maj):
                                        objet = conversion_romain_arabe(nom_maj)
                                    else:
                                        if nom_maj in dict_adj_numeral:
                                            objet = dict_adj_numeral[nom_maj]
                                        else:
                                            objet = ""
                            else:
                                objet = " " + nom
                            section = section + str(objet)
    return section


def get_title_article(article: element.Tag) -> str:
    num = article.find("num")
    name_to_formate = str(num.text)
    name = name_to_formate.replace(TYPE_ARTICLE.capitalize(), "").strip()
    if name.upper() in dict_adj_numeral:
        name = str(dict_adj_numeral[name.upper()])
    return name


def get_alineas_article(article: element.Tag) -> Dict[str, Any]:
    alineas = article.find_all("alinea")
    extracted_alineas = extract_alineas(alineas)
    assemble_alineas = assemble_alinea_doublons(extracted_alineas)
    return merge_alineas_doublons(assemble_alineas)


def get_status_article(article: element.Tag) -> str:
    mention = article.get("data:mention")
    if mention is None:
        status = "none"
    else:
        # En cas de mention multiple (ex: "(nouveau)(Supprimé)"),
        # on remplace par un espace
        mention_multi = mention.replace(")(", " ")
        # On supprime les parenthèses et on change toutes les majuscules en minuscules
        status = clean_characters(mention_multi, "[()]")
    return status.lower()


def assemble_alinea_doublons(
    alineas: List[Tuple[str, Any, Any]]
) -> List[Tuple[str, Any, Any]]:
    list_alineas, list_content = [], []
    len_alineas = len(alineas) - 1

    for i, alinea in enumerate(alineas):
        pastille = alinea[0]
        mention = alinea[1]
        contenu = alinea[2]

        # La mention est None, on doit fusionner le contenu de tous les doublons
        # pastille/mention
        if mention is not None and (
            (i != 0 and pastille == alineas[i - 1][0] and mention == alineas[i - 1][1])
            or (
                i != len_alineas
                and pastille == alineas[i + 1][0]
                and mention == alineas[i + 1][1]
            )
        ):
            # On a trouvé un doublon avant ou après l'index actuel,
            # on rassemble son contenu à fusionner
            list_content.append(contenu)

            # On se retrouve au dernier doublon OU à la fin de la liste
            if i == len_alineas or (
                i != len_alineas
                and (pastille != alineas[i + 1][0] or mention != alineas[i + 1][1])
            ):
                list_alineas.append((pastille, mention, list_content))
                list_content = []
        else:
            # Si la mention est None, on considère que le contenu n'a
            # pas besoin d'être fusionné
            list_alineas.append((pastille, mention, contenu))
    return list_alineas


def merge_alineas_doublons(alineas: List[Tuple[str, Any, Any]]) -> Dict[str, Any]:
    dict_alineas = {}
    for alinea in alineas:
        contenu = str()

        if alinea[1] is None:
            contenu = alinea[2]
        else:
            if alinea[2] is None or alinea[2] == "":
                contenu = alinea[1]
            else:
                if isinstance(alinea[2], list):
                    if len(alinea[2]) > 2:
                        contenu = alinea[2][0] + " à " + alinea[2][-1]
                    elif len(alinea[2]) == 2:
                        contenu = alinea[2][0] + " et " + alinea[2][1]
                    else:
                        contenu = alinea[2][0]
                else:
                    contenu = alinea[2]

                if contenu is not None or contenu != "":
                    contenu = contenu + ". – " + alinea[1]
                else:
                    contenu = alinea[1]
        dict_alineas[alinea[0]] = contenu
    return dict_alineas


def extract_alineas(alineas: element.ResultSet) -> List[Tuple[str, Any, Any]]:
    list_alineas = []
    for child in alineas:
        eId = child.get("eId", "")
        if eId.startswith("aldiv_") is False:
            pastille = extract_alinea_pastillage(child)
            content = extract_alinea_content(child)
            mention = get_mention(child, content)
            cleaned_content = clean_content(content, mention)

            list_alineas.append((pastille, mention, cleaned_content))
    return list_alineas


def get_content(alinea: element.Tag, mention: str) -> element.ResultSet:
    if mention is not None and mention == MENTIONS_DEL:
        balise_num = alinea.find_all("num")
        if balise_num:
            contents = balise_num
        else:
            contents = alinea.find_all("content")
    else:
        contents = alinea.find_all("content")
    return contents


def get_mention(alinea: element.Tag, content: Any) -> Any:
    mention = alinea.get(DATA_MENTION, None)
    taille_mention = len(mention or "")
    # Si la mention est (Non modifié) ET que le contenu ne se termine pas par elle,
    # on la passe à "None"
    # Ou si la mention n'est ni égale à (Non modifié) ni égale à (Supprimé)
    if (
        mention == M_NO_MAJ and content[-taille_mention:] != mention
    ) or mention not in MENTIONS_DEL_MAJ:
        mention = None
    elif mention in MENTIONS_DEL:
        # Si on trouve une mention concernant une suppression, on la remplace
        # par "(Supprimé)"
        mention = M_DEL
    return mention


def clean_content(content: Any, mention: Any) -> Any:
    if content is not None:
        if mention is not None:
            if mention not in MENTIONS_DEL_MAJ:
                content = clean_mention(content, mention)
            content_sans_guillemet = clean_characters(content, "[«»]")
            content_sans_mention = clean_mention_at_end(content_sans_guillemet, mention)
            content = clean_special_car(content_sans_mention)
    return content


def extract_alinea_content(alinea: element.Tag) -> Any:
    mention = alinea.get(DATA_MENTION)
    contents = get_content(alinea, mention)
    texte = str()
    if contents:
        for content in contents:
            if content.parent == alinea:
                if "</table>" not in str(content.contents):
                    # On split le texte afin de supprimer les retours chariots et
                    # espaces inutiles
                    texte_brut = " ".join(content.text.split())
                    texte = texte_brut.strip()

                    # On supprime les caractères . – à la fin de la string
                    texte = clean_special_car(texte)

                    # Autres formatages du texte
                    if mention is not None:
                        if mention in MENTIONS_DEL_MAJ:
                            if texte[-1:] == ".":
                                # Si l'alinéa a une mention (Non modifié) ou
                                # (Supprimé), on enlève le point à la fin s'il y en a
                                texte = texte[:-1]
                            if mention in MENTIONS_DEL:
                                # Si on trouve une mention concernant une suppression,
                                # on la remplace par "(Supprimé)"
                                texte = texte.replace(mention, M_DEL)
                        else:
                            # Dans le cas des autres mentions, si on trouve
                            # la mention dans le texte, on la supprime
                            texte = clean_mention_at_end(texte, mention)
                            texte = clean_mention(texte, mention)
                else:
                    # Le contenu contient un tableau, on nettoie les balises HTML pour
                    # ne garder que les balises et attributs colspan/rowspan
                    texte_brut = str(content.contents[1])
                    texte_a_formater = clean_line_break_n(texte_brut)
                    texte = clean_html_except_tables(texte_a_formater)
    if not texte:
        return None
    return texte


def extract_alinea_pastillage(alinea: element.Tag) -> str:
    attributes = alinea.attrs.keys()
    if alinea.isSelfClosing and DATA_MENTION not in attributes:
        raise ValueError("Self closing alinea tag {}".format(alinea.get("GUID", "")))
    num = int(alinea.get("data:pastille", "1"))
    return f"{num:03}"
