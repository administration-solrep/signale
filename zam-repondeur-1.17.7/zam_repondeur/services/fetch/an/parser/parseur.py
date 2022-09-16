import logging
import re
from abc import ABCMeta
from http import HTTPStatus
from typing import Any, Dict, Iterable, List, Optional, Tuple

from bs4 import BeautifulSoup

from zam_repondeur.exceptions.alert import AlertOnData
from zam_repondeur.models import Lecture, Texte
from zam_repondeur.models.division import ADJECTIFS_MULTIPLICATIFS
from zam_repondeur.services.clean import (
    clean_all_html,
    clean_html_except_tables,
    clean_parser_except_tables,
)
from zam_repondeur.services.fetch.http import get_http_session

logger = logging.getLogger(__name__)

MODIFIED = [
    "(Article modifié)",
    "(Modifié)",
]
NOT_MODIFIED = [
    "(Non modifié)",
]
DELETED = [
    "(Article supprimé)",
    "(Supprimé)",
    "(Supprimés)",
    "(Suppression conforme)",
    "(Suppression maintenue)",
]
EDITED = [
    "(Article en cours d’édition)",
]
CONFORM = [
    "(Article conforme)",
    "(Conforme)",
    "(Conformes)",
]
NEW = [
    "(nouveau)",
]
MENTIONS = MODIFIED + NOT_MODIFIED + DELETED + EDITED + CONFORM

STOP_TAGS = ["div"]
STOP_CLASS = ["tome", "partie", "livre", "titre", "chapitre", "section", "paragraphe"]


class Parseur(metaclass=ABCMeta):
    """
    Main factory to create a proper parser for AN content
    """

    def __init__(self, lecture: Lecture):
        self.logger = logging.getLogger(__name__)
        self.an_url = "http://www.assemblee-nationale.fr/"
        self.lecture = lecture
        self.url = self.get_texte_url(lecture)
        self.parseur_type = "DEFAULT"

    def __repr__(self) -> str:
        return f"<Parseur AN: {self.parseur_type} URL: {self.url}>"

    def download_html(self) -> str:
        http_session = get_http_session()
        resp = http_session.get(self.url)
        if resp.status_code != HTTPStatus.OK:
            raise AlertOnData(
                f"Impossibe de récupérer le texte {self.url} de l'AN \
code http:{resp.status_code}",
                "http",
                resp.status_code,
            )

        try:
            content: str = resp.content.decode("utf-8")
        except Exception:
            logger.error(
                f"Scraping of lecture {self.lecture}, {self.url} : \
Erreur d'encodage de la réponse"
            )
            raise AlertOnData(
                f"Scraping of lecture {self.lecture}, {self.url} : \
Erreur d'encodage de la réponse",
                "data",
                1,
            )
        return content

    def get_texte_url(self, lecture: Lecture) -> str:
        texte: Texte = lecture.texte
        prefix = f"{self.an_url}{texte.legislature}"
        numero = f"{texte.numero:04}"
        url = f"{prefix}/textes/{numero}.asp"
        return url

    def get_num_article(self, article: BeautifulSoup) -> Optional[str]:
        split_article = clean_all_html(f"{article}").split()
        article_title_raw = " ".join(split_article)

        if not article_title_raw.startswith("Article "):
            return None

        title = article_title_raw.replace(" ", "")
        searched = re.compile(r"\d+[a-z]*[A-Z,İ]*[a-z]*").search(title)
        if not searched:
            liminaire = re.compile(r"(liminaire)").search(title)
            if liminaire:
                return "0"
            unique = re.compile(r"(unique)").search(title)
            return "1" if unique else None

        all_num = []
        malformed_num = searched.group(0)
        match_num = re.compile(r"\d+").search(malformed_num)

        if not match_num:
            return None

        all_num.append(match_num.group(0))
        malformed_num = re.sub(r"\d+(er)?", "", malformed_num)

        # On regarde si on a une ou plusieurs lettres majuscule en première position
        letters = ""
        while len(malformed_num) > 0:
            if malformed_num[0] in "ABCDEFGHIJKLMNOPQRSTUVWXYZİ":
                letters += malformed_num[0]
                malformed_num = malformed_num[1:]
            else:
                break
        if letters:
            all_num.append(letters)

        # On regarde si un adjectif multiplicatif est présent
        for adj in reversed([a for a in ADJECTIFS_MULTIPLICATIFS.keys()]):
            if adj in malformed_num:
                all_num.append(adj)
                malformed_num = malformed_num.replace(adj, "")

        # On récupére les éléments restant
        if malformed_num:
            all_num.append(malformed_num)

        return " ".join(all_num)

    def is_next_article(self, element: BeautifulSoup) -> bool:
        if "attrs" in element.__dict__.keys():
            if "class" in element.attrs.keys():
                return "a9ArticleNum" in element["class"]
        if element.text.strip().startswith("Article "):
            return True
        return False

    @staticmethod
    def is_mention(element: BeautifulSoup) -> bool:
        for mention in MENTIONS:
            texte = " ".join(element.text.split()).lower()
            if texte.startswith(mention.lower()):
                return True
        if "attrs" in element.__dict__.keys():
            if "class" in element.attrs.keys():
                return "aMentionsousarticle" in element["class"]
        return False

    def is_title(self, element: BeautifulSoup) -> bool:
        if "attrs" in element.__dict__.keys():
            if "class" in element.attrs.keys():
                for stop_class in STOP_CLASS:
                    if stop_class in element["class"][0].lower():
                        return True
        for stop_class in STOP_CLASS:
            title = element.text.strip().lower()
            if title.startswith(stop_class) or title.startswith("sous-" + stop_class):
                return True
        return False

    def is_condition_arret(self, element: BeautifulSoup) -> bool:
        if element.name == "div":
            if element.findChild().name == "table":
                return False
        if element.name in STOP_TAGS:
            return True
        if self.is_next_article(element):
            return True
        if not self.is_new_pastille(element.text.strip()):
            return self.is_title(element)
        return False

    def clean_pastille_content(self, pastille: BeautifulSoup) -> str:
        if "</table>" in f"{pastille}":
            content_raw = clean_html_except_tables(f"{pastille}").replace("\n", "")
        elif pastille.img:
            pastille_replaced = f"{pastille}".replace(f"{pastille.img}", "(1) ")
            content_raw = clean_all_html(pastille_replaced).replace("\n", "")
        else:
            content_raw = clean_all_html(f"{pastille}").replace("\n", "")
        return re.sub(" {2,}", " ", content_raw).strip()

    def is_new_pastille(self, pastille_raw: str) -> bool:
        p = re.compile(r"\(\d+\)")
        m = p.match(pastille_raw)
        if m:
            return True
        return False

    def get_next_pastille(self, elements: BeautifulSoup) -> Iterable[str]:
        result: List = []
        for element in elements:
            if self.is_condition_arret(element):
                if result:
                    yield " ".join(result)
                result = []
                break
            current = self.clean_pastille_content(element)
            if not current or self.is_mention(element):
                continue
            new_pastille = self.is_new_pastille(current)
            if new_pastille:
                if result:
                    yield " ".join(result)
                result = [current]
            else:
                result.append(current)
        if result:
            yield " ".join(result)

    @staticmethod
    def clean_txt(pastille: str) -> str:
        # Clean articles and numbers, ex "L. 312‑13‑2" or "vingt-quatre"
        while True:
            s_tirets = re.compile(r"[a-z0-9]+( ‑ [a-z0-9]+)+").search(pastille)
            if s_tirets:
                del_spaces = s_tirets.group(0).replace(" ", "")
                pastille = pastille.replace(s_tirets.group(0), del_spaces)
            else:
                break

        # Clean spaces between symbols , . () []
        while True:
            s_ponctu = re.compile(r"[^«] [,.)\]<]|[(\[>] [^»]").search(pastille)
            if s_ponctu:
                del_spaces = s_ponctu.group(0).replace(" ", "")
                pastille = pastille.replace(s_ponctu.group(0), del_spaces)
            else:
                break

        return pastille

    def get_articles(self) -> Iterable[Tuple]:
        """
        Return a generator of tuple:
        ( numero_art, [ pastille_content, ..., pastille_content ] )
        """

        dict_article: Dict[Any, Any] = dict()

        content = self.download_html()
        try:
            cleaned_content = clean_parser_except_tables(content).replace("\n", "")
            soup = BeautifulSoup(cleaned_content, features="lxml")
        except AlertOnData:
            raise
        except Exception:
            logger.error(
                f"Scraping of lecture {self.lecture}, {self.url} : \
Erreur lors de l'initialisation de BeautifulSoup"
            )
            raise AlertOnData(
                f"Scraping of lecture {self.lecture}, {self.url} : \
Erreur lors de l'initialisation de BeautifulSoup",
                "data",
                2,
            )
        dict_article["textes"] = []
        dict_article["titre"] = ""

        list_articles = soup.find_all("p")
        for article in list_articles:
            numero = self.get_num_article(article)
            if not numero:
                continue

            dict_article["titre"] = numero
            dict_article["textes"] = []

            for pastille in self.get_next_pastille(article.find_next_siblings()):
                p = re.compile(r"\(\d+\)")
                m = p.match(pastille)
                if m:
                    last_pastille_caractere = m.end()
                    alinea = self.clean_txt(pastille[last_pastille_caractere:].strip())
                else:
                    alinea = self.clean_txt(pastille)
                if not alinea:
                    continue
                dict_article["textes"].append(alinea)

            tuple_article = (dict_article["titre"], dict_article["textes"])
            del dict_article["textes"]

            yield tuple_article

    def transform(self) -> List[Dict[Any, Any]]:
        """
        Use the generator get_article_content to create a list of dict
        """
        list_articles = []

        try:
            for order, (num_art, alineas) in enumerate(self.get_articles(), 1):
                article: Dict[Any, Any] = dict()
                article["alineas"] = {}
                article["type"] = "article"
                article["order"] = order
                article["titre"] = num_art
                article["status"] = "none"

                for pastille, alinea in enumerate(alineas, 1):
                    article["alineas"][f"{pastille:03}"] = alinea

                    if alinea in EDITED:
                        article["status"] = "edited"
                    elif alinea in DELETED:
                        article["status"] = "deleted"
                    elif alinea in MODIFIED:
                        article["status"] = "modified"

                list_articles.append(article)
                del article
        except AlertOnData:
            raise
        except Exception:
            logger.error(
                f"Scraping of lecture {self.lecture}, {self.url} : \
Erreur du parseur {self.parseur_type}"
            )
            raise AlertOnData(
                f"Scraping of lecture {self.lecture}, {self.url} : \
Erreur du parseur {self.parseur_type}",
                "data",
                3,
            )

        return list_articles
