import logging
from abc import ABCMeta, abstractmethod
from http import HTTPStatus
from typing import Any, Dict, Iterable, List, Tuple

from tlfp.tools.parse_texte import parse

from zam_repondeur.models import Lecture, Texte
from zam_repondeur.services.fetch.http import get_http_session

MODIFIED = [
    "(Article modifié)",
]
DELETED = [
    "(Article supprimé)",
]
EDITED = [
    "(Article en cours d’édition)",
]


class Parseur(metaclass=ABCMeta):
    """
    Main factory to create a proper parser for AN content
    """

    def __init__(self, lecture: Lecture):
        self.logger = logging.getLogger(__name__)
        self.an_url = "http://www.assemblee-nationale.fr/"
        self.lecture = lecture
        self.url = self.get_texte_url(lecture)
        self.parseur_type = ""

    def __repr__(self) -> str:
        return f"<Parseur AN: {self.parseur_type} URL: {self.url}>"

    def download_html(self) -> str:
        http_session = get_http_session()
        resp = http_session.get(self.url)
        if resp.status_code != HTTPStatus.OK:
            raise RuntimeError(f"Failed to download texte {self.url} from assemblée")

        content: str = resp.content.decode("utf-8")
        return content

    def get_texte_url(self, lecture: Lecture) -> str:
        texte: Texte = lecture.texte
        prefix = f"{self.an_url}{texte.legislature}"
        numero = f"{texte.numero:04}"
        url = f"{prefix}/textes/{numero}.asp"
        return url

    @abstractmethod
    def get_articles(self) -> Iterable[Tuple]:
        """
        Return a generator of tuple:
        ( numero_art, [ pastille_content, ..., pastille_content ] )
        """
        pass

    def transform(self) -> List[Dict[Any, Any]]:
        """
        Use the generator get_article_content to create a list of dict
        """
        list_articles = []

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

        return list_articles


class ParseurAN(Parseur):
    """
    Default parser will use the tlfp parser
    """

    def __init__(self, lecture: Lecture):
        super().__init__(lecture)
        self.parseur_type = "TLFP"

    def get_articles(self) -> Iterable[Tuple]:
        ...  # Body omitted

    def transform(self) -> List[Dict[Any, Any]]:
        articles: List[Dict[Any, Any]] = parse(self.url, include_annexes=True)
        return articles
