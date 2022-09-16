import csv
import io
from collections import Counter
from typing import BinaryIO, Dict, List, Set, TextIO, Tuple

from pyramid.request import Request

from zam_repondeur.models import Amendement, Lecture, Team

from .common import create_batches, import_amendement, unbatch_amendements
from .spreadsheet import (
    BOOL_FIELDS,
    FIELDS,
    HEADERS,
    column_name_to_field,
    export_amendement_for_spreadsheet,
)


def export_csv(lecture: Lecture, filename: str, request: Request) -> Counter:
    counter = Counter({"amendements": 0})
    with open(filename, "w", encoding="utf-8-sig") as file_:
        file_.write(";".join(HEADERS) + "\n")
        writer = csv.DictWriter(
            file_,
            fieldnames=list(FIELDS.keys()),
            delimiter=";",
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        for amendement in sorted(lecture.amendements):
            writer.writerow(export_amendement_for_spreadsheet(amendement))
            counter["amendements"] += 1
    return counter


class CSVImportError(Exception):
    pass


def import_csv(
    request: Request,
    reponses_file: BinaryIO,
    lecture: Lecture,
    amendements: Dict[int, Amendement],
    team: Team,
) -> Counter:
    previous_reponse = ""
    counter = Counter({"reponses": 0, "reponses_errors": 0})

    reponses_text_file = io.TextIOWrapper(reponses_file, encoding="utf-8-sig")
    batch_to_create: Set[Tuple[int, ...]] = set()

    delimiter = _guess_csv_delimiter(reponses_text_file)

    for line in csv.DictReader(reponses_text_file, delimiter=delimiter):
        item = {
            column_name_to_field(column_name): value
            for column_name, value in line.items()
            if column_name is not None
        }
        for field in BOOL_FIELDS:
            value = item.get(field)
            if value is not None:
                item[field] = value.lower() == "oui"  # type: ignore
        import_amendement(
            request, lecture, amendements, item, counter, previous_reponse, team
        )
        if item.get("computed_batch", None):
            try:
                batch_to_create.add(
                    tuple(int(num) for num in item["computed_batch"].split(","))
                )
            except ValueError:
                continue

    for batch in batch_to_create:
        amdts_batch: List[Amendement] = []
        for num in batch:
            amdt = lecture.find_amendement(num)
            if amdt is not None:
                amdts_batch.append(amdt)
        unbatch_amendements(request, amdts_batch)
        create_batches(request, amdts_batch)

    return counter


def _guess_csv_delimiter(text_file: TextIO) -> str:
    try:
        sample = text_file.readline()
    except UnicodeDecodeError:
        raise CSVImportError("Le fichier n’est pas encodé en UTF-8")
    except Exception:
        raise CSVImportError("Le format du fichier n’est pas reconnu")

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        raise CSVImportError(
            "Le fichier CSV n’utilise pas un délimiteur reconnu "
            "(virgule, point-virgule ou tabulation)"
        )

    text_file.seek(0)

    return dialect.delimiter
