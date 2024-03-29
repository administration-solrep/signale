from enum import Enum


class Phase(Enum):
    INCONNUE = 0
    PREMIERE_LECTURE = 1
    DEUXIEME_LECTURE = 2
    NOUVELLE_LECTURE = 3
    LECTURE_DEFINITIVE = 4


# All phase, in order
ALL_PHASES = [
    Phase.PREMIERE_LECTURE,
    Phase.DEUXIEME_LECTURE,
    Phase.NOUVELLE_LECTURE,
    Phase.LECTURE_DEFINITIVE,
]
