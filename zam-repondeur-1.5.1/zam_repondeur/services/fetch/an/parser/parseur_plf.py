import re
from typing import Any, Dict, Iterable, List, Tuple

from bs4 import BeautifulSoup
from tlfp.tools.parse_texte import parse

from zam_repondeur.models import Lecture, Phase, Texte
from zam_repondeur.services.clean import clean_all_html, clean_html_except_tables

from .parseur import Parseur

SUFFIXE_URL = {
    # ( partie, phase ) : SUFFIXE
    (1, Phase.PREMIERE_LECTURE): "A",
    (1, Phase.DEUXIEME_LECTURE): "B",
    (2, Phase.PREMIERE_LECTURE): "C",
    (2, Phase.DEUXIEME_LECTURE): "D",
    (None, Phase.NOUVELLE_LECTURE): "",
    (None, Phase.LECTURE_DEFINITIVE): "",
}

STOP_TAGS = ["h1", "h2", "h3", "h4", "h5"]


class ParseurPLF(Parseur):
    """
    Parser to handle Projet de loi de finance
    """

    def __init__(self, lecture: Lecture):
        self.suffixe = SUFFIXE_URL[(lecture.partie, lecture.phase)]
        super().__init__(lecture)
        if not self.suffixe:
            self.parseur_type = "TLFP"
        else:
            self.parseur_type = "PLF"

    def get_texte_url(self, lecture: Lecture) -> str:
        """
        Infos de l'AN pour la construction d'urls:
        La règle concernant le nommage des PLF est la suivante :
        A : 1ere partie, 1ere délibération
        B : 1ere partie, 2e délibération
        C : 2e partie, 1ere délibération
        D : 2e partie, 2e délibération
        """
        self.lecture = lecture
        texte: Texte = lecture.texte
        prefix = f"{self.an_url}{texte.legislature}"
        numero = f"{texte.numero:04}"
        url = f"{prefix}/textes/{numero}{self.suffixe}.asp"
        return url

    def get_num_article(self, article: BeautifulSoup) -> str:

        words = re.compile(r"\W+")
        article_title_raw = clean_all_html(f"{article}").replace("\n", "")
        matched_list = words.split(article_title_raw)
        if not matched_list[0] == "Article":
            raise ValueError(f"Numéro d'article non récupérable {matched_list}")
        clean_num = ""
        num = re.compile(r"\d+")
        for index, value in enumerate(matched_list[1:]):
            match = num.match(value)
            if not match and index > 0:
                clean_num += " "
            clean_num += value
        return clean_num

    def clean_pastille_content(self, pastille: BeautifulSoup) -> str:
        if "</table>" in f"{pastille}":
            content_raw = clean_html_except_tables(f"{pastille}").replace("\n", "")
        else:
            content_raw = clean_all_html(f"{pastille}").replace("\n", "")
        return re.sub(" {2,}", " ", content_raw).strip()

    def is_new_pastille(self, pastille_raw: str) -> bool:
        p = re.compile(r"\(\d+\)")
        m = p.match(pastille_raw)
        if m:
            return True
        return False

    def is_next_article(self, element: BeautifulSoup) -> bool:
        if "attrs" in element.__dict__.keys():
            if "class" in element.attrs.keys():
                return "aFPFTprojetitrarticle" in element["class"]
        return False

    def is_next_titre(self, element: BeautifulSoup) -> bool:
        if "attrs" in element.__dict__.keys():
            if "class" in element.attrs.keys():
                return (
                    "titre" in element["class"][0] and "projet" in element["class"][0]
                )
        return False

    def is_condition_arret(self, element: BeautifulSoup) -> bool:
        if element.name in STOP_TAGS:
            return True
        if self.is_next_article(element):
            return True
        if self.is_next_titre(element):
            return True
        if element.name == "p":
            return False
        for child in element.children:
            if child.name in STOP_TAGS:
                return True
            if self.is_next_article(element):
                return True
            if self.is_next_titre(child):
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
            if not current:
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

    def get_articles(self) -> Iterable[Tuple]:

        dict_article: Dict[Any, Any] = dict()

        content = self.download_html()
        soup = BeautifulSoup(content, features="lxml")
        dict_article["textes"] = []
        dict_article["titre"] = ""

        list_articles = soup.find_all("p", attrs={"class": ["aFPFTprojetitrarticle"]})

        for article in list_articles:
            dict_article["titre"] = self.get_num_article(article)
            dict_article["textes"] = []

            for pastille in self.get_next_pastille(article.find_next_siblings()):
                p = re.compile(r"\(\d+\)")
                m = p.match(pastille)
                if m:
                    last_pastille_caractere = m.end()
                    dict_article["textes"].append(
                        pastille[last_pastille_caractere:].strip()
                    )
                else:
                    dict_article["textes"].append(pastille)

            tuple_article = (dict_article["titre"], dict_article["textes"])
            del dict_article["textes"]

            yield tuple_article

    def transform(self) -> List[Dict[Any, Any]]:
        if self.suffixe == "":
            self.logger.info("article sans suffixe, utilisation du parseur tlfp")
            articles: List[Dict[Any, Any]] = parse(self.url, include_annexes=True)
            return articles
        else:
            self.logger.info("article avec un suffixe")
            return super().transform()
