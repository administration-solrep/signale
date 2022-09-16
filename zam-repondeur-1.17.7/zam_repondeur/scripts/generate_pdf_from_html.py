"""
Stand alone script to generate a PDF from a list of html files
"""

import datetime
import sys
from pathlib import Path
from typing import List, Optional, Union, Iterable

import htmlmin
from pikepdf import Pdf
from weasyprint import CSS, HTML
from weasyprint.fonts import FontConfiguration
import argparse

STATIC_PATH = Path(__file__).parent.parent / "static"
PDF_CSS = str(STATIC_PATH / "css" / "print.css")


def merge_pdfs(filename: str, pdf_files: List[Union[str, Path]]) -> None:
    """
    Merge all pdf as one and ensure that each pdf starts on a odd page
        (starting page count from 1)
    """
    main_pdf = Pdf.open(pdf_files[0])
    page_size = (
        main_pdf.pages[0].mediabox[2] - main_pdf.pages[0].mediabox[0],  # type: ignore
        main_pdf.pages[0].mediabox[3] - main_pdf.pages[0].mediabox[1],  # type: ignore
    )
    if len(main_pdf.pages) % 2 != 0:
        main_pdf.add_blank_page(page_size=page_size)
    for pdf_file in pdf_files[1:]:
        pdf = Pdf.open(pdf_file)
        main_pdf.pages.extend(pdf.pages)
        if len(main_pdf.pages) % 2 != 0:
            main_pdf.add_blank_page(page_size=page_size)
    main_pdf.save(filename)


def generate_pdfs(
    input_outputs: Iterable[tuple[Union[str, Path], Union[str, Path]]], filename: str
) -> None:
    font_config = FontConfiguration()
    css = CSS(PDF_CSS, font_config=font_config)

    pdf_files = []
    for (input_filename, output_filename) in input_outputs:
        HTML(
            string=Path(input_filename).read_text("utf-8"), encoding="utf-8"
        ).write_pdf(output_filename, stylesheets=[css], font_config=font_config)
        pdf_files.append(output_filename)
    if filename:
        # and merge everything
        merge_pdfs(filename, pdf_files)
        for pdf_file in pdf_files:
            Path(pdf_file).unlink(missing_ok=True)


def generate_pdf(
    content: str, filename: str, input_filename: Optional[str] = None
) -> None:
    print(datetime.datetime.now())
    font_config = FontConfiguration()
    print(datetime.datetime.now())
    css = CSS(PDF_CSS, font_config=font_config)
    print(datetime.datetime.now())
    if content is None and input_filename:
        content = Path(input_filename).read_text(encoding="utf-8")
    else:
        content = htmlmin.minify(content)
    print(datetime.datetime.now())
    HTML(string=content, encoding="utf-8").write_pdf(
        filename, stylesheets=[css], font_config=font_config
    )
    print(datetime.datetime.now())


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", dest="output_file", help="PDF file to output")
    parser.add_argument(
        "-i",
        dest="input_file",
        help="File containing the input and output files to output",
        required=False,
        default=None,
    )
    parser.add_argument("html_file", nargs="?", help="HTML file to convert to PDF")
    args = parser.parse_args(argv)

    input_outputs = []
    if args.input_file:
        with open(args.input_file, "r") as _file:
            for l in _file:
                input_file, sep, output_file = l.strip().partition(":")
                if not output_file:
                    input_suffix = Path(input_file).suffix.lower()
                    if input_suffix in (".htm", ".html"):
                        output_file = str(Path(input_file).with_suffix(".pdf"))
                    elif input_suffix in (".pdf"):
                        output_file = input_file
                        input_file = str(Path(input_file).with_suffix(".html"))
                    else:
                        raise ValueError(f"Unsupported format for line {l}")
                input_outputs.append((input_file, output_file))
    else:
        input_outputs = [
            (args.html_file, str(Path(args.html_file).with_suffix(".pdf"))),
        ]
    generate_pdfs(input_outputs, args.output_file)
    # else:
    #    generate_pdf(None, argv[1], argv[2])


if __name__ == "__main__":
    main(sys.argv)
