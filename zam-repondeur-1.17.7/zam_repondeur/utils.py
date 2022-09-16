import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from webob.multidict import MultiDict

from zam_repondeur.models import AVIS


def normalize_num(num: str) -> int:
    try:
        num_int = int(num)
    except ValueError:
        num_int = int(num.split("\n")[0].strip(","))
    return num_int


def normalize_avis(avis: str) -> str:
    avis = avis.strip()
    avis_lower = avis.lower()
    if avis_lower in ("défavorable", "defavorable"):
        avis = "Défavorable"
    elif avis_lower in ("favorable",):
        avis = "Favorable"
    elif avis_lower in ("sagesse",):
        avis = "Sagesse"
    elif avis_lower in ("retrait",):
        avis = "Retrait"
    if avis and avis not in AVIS:
        pass  # print(avis)
    return avis


def normalize_reponse(reponse: str, previous_reponse: str) -> str:
    reponse = reponse.strip()
    if reponse.lower() == "id.":
        reponse = previous_reponse
    return reponse


def add_url_fragment(url: str, fragment: str) -> str:
    scheme, netloc, path, params, query, _ = urlparse(url)
    return urlunparse((scheme, netloc, path, params, query, fragment))


def add_url_params(url: str, **extra_params: str) -> str:
    scheme, netloc, path, params, query, fragment = urlparse(url)
    query_dict = MultiDict(parse_qsl(query))
    query_dict.update(**extra_params)
    query = urlencode(query_dict)
    return urlunparse((scheme, netloc, path, params, query, fragment))


class Timer:
    enter_time: float = 0.0
    exit_time: float = 0.0

    def __enter__(self) -> "Timer":
        self.enter_time = time.monotonic()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, tb: Any) -> None:
        self.exit_time = time.monotonic()

    def elapsed(self) -> float:
        return self.exit_time - self.enter_time


DICT_ROMAIN_ARABE = {"M": 1000, "D": 500, "C": 100, "L": 50, "X": 10, "V": 5, "I": 1}
UNITES = {100: "C", 10: "X", 1: "I"}


def conversion_romain_arabe(chiffres: str) -> int:
    n = old = 0
    for chiffre in reversed(chiffres):
        n = (
            n + DICT_ROMAIN_ARABE[chiffre]
            if DICT_ROMAIN_ARABE[chiffre] >= old
            else n - DICT_ROMAIN_ARABE[chiffre]
        )
        old = DICT_ROMAIN_ARABE[chiffre]
    return n


def is_romain(chaine: str) -> bool:
    for car in chaine:
        if car not in DICT_ROMAIN_ARABE:
            return False
    return True


def conversion_arabe_romain(nombre: int) -> str:
    romain: str = ""
    nb_zero: int = len(str(nombre)) - 1
    decompose = []

    for e in list(str(nombre)):
        if e != "0":
            decompose.append(e + "0" * nb_zero)
        nb_zero -= 1

    for d in decompose:
        reste: int = int(d)
        while reste > 0:
            for key, value in DICT_ROMAIN_ARABE.items():
                sous = reste - value
                if sous >= 0:
                    romain += key
                    reste -= value
                    break
                else:
                    if abs(sous) in UNITES:
                        romain += UNITES[abs(sous)] + key
                        reste = 0
                        break
    return romain
