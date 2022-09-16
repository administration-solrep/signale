import multiprocessing
import subprocess
import sys
from contextlib import contextmanager
from enum import IntEnum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Generator, Iterable, Optional, Union, Sequence

import htmlmin
from pikepdf import Pdf
from pyramid.registry import Registry
from weasyprint import CSS, HTML
from weasyprint.fonts import FontConfiguration

from zam_repondeur.models import Amendement
from zam_repondeur.templating import render_template

STATIC_PATH = Path(__file__).parent.parent.parent / "static"
PDF_CSS = str(STATIC_PATH / "css" / "print.css")

GENERATION_MODE_INLINE = "inline"  # inline, no fork
GENERATION_MODE_MP = "MP"  # fork and use multiprocess
GENERATION_MODE_CMDLINE = "CMDLINE"  # fork a command line


class WritePdfSplitMode(IntEnum):
    """
    An enum defining the mode to use to generate the PDF:
        - WritePdfSplitMode.WHOLE: Create the whole PDF using one template
        - WritePdfSplitMode.MULTIPLE_PDF_MULTIPLE: Create the PDF in parts,
            each parts in a function (in the same process or not,
            see ``WritePdfGEnerationMode``)
        - WritePdfSplitMode.MULTIPLE_PDF_AT_ONCE: Create the PDF in parts,
            all parts in the same function (in the same process or not,
            see ``WritePdfGEnerationMode``)
    """

    WHOLE = 1  # Generate the full pdf as a whole
    MULTIPLE_PDF_MULTIPLE = (
        2  # Generate the PDF in parts, each parts in a function/process
    )
    MULTIPLE_PDF_AT_ONCE = (
        3  # Generate the PDF in parts, all parts in the same function/process
    )


class WritePdfGEnerationMode(IntEnum):
    """
    An enum to control the generation PDF behaviour:
        - WritePdfGEnerationMode.INLINE : generate the PDF(s) in the current process,
            may cause memory leaks
        - WritePdfGEnerationMode.MP : generate the PDF(s) in a different process
            span by multiprocess.Process
        - WritePdfGEnerationMode.CMDLINE: generate the PDF(s) in a different process
            running a different script
    """

    INLINE = 1  # inline, no fork
    MP = 2  # fork and use multiprocess
    CMDLINE = 3  # fork a command line


@contextmanager
def xvfb_if_supported() -> Generator:
    try:
        from xvfbwrapper import Xvfb

        with Xvfb():
            yield
    except (ModuleNotFoundError, EnvironmentError, OSError, RuntimeError):
        yield


def generate_html_for_pdf(
    registry: Registry,
    template_name: str,
    context: dict,
    filename: Optional[str] = None,
    minify: bool = True,
) -> str:
    """Mostly useful for testing purpose.
    :param registry: A pyramid registry
    :param template_name: The template filename
    :param context: A dict containing the value usable by the templates
    :param filename: An optional filename to output result, defaults to None
    :param minify: A flag to specify if the HTML must be minified, defaults to True
    :return: the content of the HTML if n filename was specified, else the filename
    """
    content = render_template(template_name, context, registry=registry)
    if minify:
        content = htmlmin.minify(content)
    if filename:
        with open(filename, "wb+") as _file:
            _file.write(content.encode("utf-8"))
        return filename
    return content


def write_pdf_part(
    context: dict,
    filename: str,
    template_name: str,
    registry: Registry,
    generation_mode: int,
) -> str:
    """
    Generate an HTML from the template then a PDF from the data and a template name
    :param context: a dict containing the value usable by the templates,
    :param filename: The PDF filename to produce
    :param template_name: The jinja2 template filename to use
    :param registry: A pyramid registry
    :param generation_mode: An enum to control the generation PDF behaviour
    :return: The PDF filename
    """
    content = generate_html_for_pdf(registry, template_name, context)
    if generation_mode == WritePdfGEnerationMode.INLINE:
        generate_pdf(content, filename)
    elif generation_mode == WritePdfGEnerationMode.MP:
        generate_pdf_mp(content, filename)
    elif generation_mode == WritePdfGEnerationMode.CMDLINE:
        generate_pdf_cmdline(content, filename)
    else:
        raise ValueError(f"Unssuported generation mode : {generation_mode}")
    return filename


def write_pdf(
    context: dict,
    filename: str,
    registry: Registry,
    split_mode: int = WritePdfSplitMode.MULTIPLE_PDF_MULTIPLE,
    generation_mode: int = WritePdfGEnerationMode.CMDLINE,
) -> None:
    """
    The main function to create a PDF for a *dossier*
    :param context: a dict containing the value usable by the templates,
        must contains at least a *lecture* keys with a ``Lecture``object and
        a *articles* keys with a list of *Article* objects
    :param filename: The PDF filename to output
    :param registry: A pyramid registry used to configure the template engine
    :param split_mode: An enum defining the mode to use to generate the PDF,
        see ``WritePdfSplitMode``
    :param generation_mode: An enum to control the generation PDF behaviour,
        see ``WritePdfGEnerationMode``
    """
    if split_mode == WritePdfSplitMode.WHOLE:
        write_pdf_part(context, filename, "print/all.html", registry, generation_mode)
    elif split_mode == WritePdfSplitMode.MULTIPLE_PDF_MULTIPLE:
        write_pdf_multiple_pdf_multiple(context, filename, registry, generation_mode)
    elif split_mode == WritePdfSplitMode.MULTIPLE_PDF_AT_ONCE:
        write_pdf_multiple_pdf_at_once(context, filename, registry, generation_mode)


def write_pdf_multiple_pdf_at_once(
    context: dict, filename: str, registry: Registry, generation_mode: int,
) -> None:
    """
    Generate a PDF for a *dossier* by generating a PDF for each part
        (lecture header, article header and one for each response),
        then concat all of them ensuring that each part start on an odd page.

    Generate all template HTML file in this process and may generate the PDF all at once
        in the current process or in another (spawn at most one child process)
    :param context: a dict containing the value usable by the templates,
        must contains at least a *lecture* keys with a ``Lecture``object and
        a *articles* keys with a list of *Article* objects
    :param filename: The PDF filename to output
    :param registry: A pyramid registry used to configure the template engine
    :param generation_mode: An enum to control the generation PDF behaviour,
        see ``WritePdfGEnerationMode``
    """
    html_files: list[Union[str, Path]] = []

    # generate the pdf in parts
    def get_filename() -> str:
        pfilename = Path(filename)
        return str(
            pfilename.with_stem(
                "_".join((pfilename.stem, f"{len(html_files):0>5}"))
            ).with_suffix(".html")
        )

    do_minify = True
    # First, the lecture header page
    html_files.append(
        generate_html_for_pdf(
            registry,
            "print/all_lecture_header.html",
            context,
            get_filename(),
            do_minify,
        )
    )
    # then for each article
    for article in sorted(context.get("articles", [])):
        # the article header page
        article_context = context.copy()
        article_context.update({"article": article})
        html_files.append(
            generate_html_for_pdf(
                registry,
                "print/all_article_header.html",
                article_context,
                get_filename(),
                do_minify,
            )
        )
        # and then each response
        for (
            response,
            amendements,
        ) in article.grouped_displayable_top_level_amendements():
            response_context = context.copy()
            response_context.update({"reponse": response, "amendements": amendements})
            html_files.append(
                generate_html_for_pdf(
                    registry,
                    "print/all_response.html",
                    response_context,
                    get_filename(),
                    do_minify,
                )
            )
    pdf_files = []
    for html_file in html_files:
        pdf_files.append(Path(html_file).with_suffix(".pdf"))
    if generation_mode == WritePdfGEnerationMode.INLINE:
        generate_pdfs(zip(html_files, pdf_files), filename)
    elif generation_mode == WritePdfGEnerationMode.MP:
        generate_pdfs_mp(zip(html_files, pdf_files), filename)
    elif generation_mode == WritePdfGEnerationMode.CMDLINE:
        generate_pdfs_cmdline(zip(html_files, pdf_files), filename)

    for html_file in html_files:
        Path(html_file).unlink(missing_ok=True)
    for pdf_file in pdf_files:
        Path(pdf_file).unlink(missing_ok=True)


def merge_pdfs(
    filename: Union[str, Path], pdf_files: Sequence[Union[str, Path]]
) -> None:
    """
    Merge all pdf_files as one.

    Ensure that each pdf starts on an odd page (by inserting a blank page if necessary)
    :param filename: The final PDF to genera
    :param pdf_files: The PDF file to concat
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


def write_pdf_multiple_pdf_multiple(
    context: dict, filename: str, registry: Registry, generation_mode: int,
) -> None:
    """
    Generate a PDF for a *dossier* by generating a PDF for each part
        (lecture header, article header and one for each response),
        then concat all of them ensuring that each part start on an odd page.

    Generate all template HTML file in this process and may generate each PDF
        in the current process or in another (may spawn a child process by PDF parts),
        and merge all PDF in the current process
    :param context: a dict containing the value usable by the templates,
        must contains at least a *lecture* keys with a ``Lecture``object and
        a *articles* keys with a list of *Article* objects
    :param filename: The PDF filename to output
    :param registry: A pyramid registry used to configure the template engine
    :param generation_mode: An enum to control the generation PDF behaviour,
        see ``WritePdfGEnerationMode``
    """
    contents: list[Union[str, Path]] = []

    # generate the pdf in parts
    def get_filename() -> str:
        pfilename = Path(filename)
        return str(
            pfilename.with_stem("_".join((pfilename.stem, f"{len(contents):0>5}")))
        )

    # First, the lecture header page
    contents.append(
        write_pdf_part(
            context,
            get_filename(),
            "print/all_lecture_header.html",
            registry,
            generation_mode,
        )
    )
    # then for each article
    for article in sorted(context.get("articles", [])):
        # the article header page
        article_context = context.copy()
        article_context.update({"article": article})
        contents.append(
            write_pdf_part(
                article_context,
                get_filename(),
                "print/all_article_header.html",
                registry,
                generation_mode,
            )
        )
        # and then each response
        for (
            response,
            amendements,
        ) in article.grouped_displayable_top_level_amendements():
            response_context = context.copy()
            response_context.update({"reponse": response, "amendements": amendements})
            contents.append(
                write_pdf_part(
                    response_context,
                    get_filename(),
                    "print/all_response.html",
                    registry,
                    generation_mode,
                )
            )
    # and merge everything
    merge_pdfs(filename, contents)
    for pdf_file in contents:
        Path(pdf_file).unlink(missing_ok=True)


def write_pdf_multiple(
    amendements: Iterable[Amendement], filename: str, registry: Registry
) -> None:
    content = generate_html_for_pdf(
        registry, "print/multiple.html", {"amendements": amendements}
    )
    generate_pdf(content, filename)


def generate_pdfs(
    input_outputs: Iterable[tuple[Union[str, Path], Union[str, Path]]], filename: str
) -> None:
    """
    Convert html file to pdf and concat all pdf into a unique pdf file
    :param input_outputs: Array of tuple (html input file, pdf output file)
    :param filename: The PDF filename to create as the concatenation of
        all converted html files
    """

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


def generate_pdfs_mp(
    input_outputs: Iterable[tuple[Union[str, Path], Union[str, Path]]], filename: str
) -> None:
    """
    Convert html file to pdf and concat all pdf into a unique pdf file.

    Do it in another process spawn by multiprocessing
    :param input_outputs: Array of tuple (html input file, pdf output file)
    :type input_outputs: [tuple[str or Path, str or Path]]
    :param filename: The PDF filename to create as the concatenation of all
        converted html files
    :type filename: str
    """

    p = multiprocessing.Process(target=generate_pdfs, args=(input_outputs, filename))
    p.start()
    p.join()


def generate_pdfs_cmdline(
    input_outputs: Iterable[tuple[Union[str, Path], Union[str, Path]]], filename: str
) -> None:
    """
    Call an external python script to convert html file to pdf
        and concat all pdf into a unique pdf file.
    Calls a python executable with the script name for multiple reasons :
        - to spawn a child to prevent memory leak by using OS mechanism to really free
            the memory when the process die
        - to not use an entry point to avoid pkg_resources overhead (more than 1 second)
        :param input_outputs: Array of tuple (html input file, pdf output file)
        :type input_outputs: [tuple[str or Path, str or Path]]
        :param filename: The PDF filename to create as the concatenation of all
            converted html files
        :type filename: str
    """
    with NamedTemporaryFile() as fp:
        fp.write(
            "\n".join([":".join((str(i), str(o))) for i, o in input_outputs]).encode(
                "utf-8"
            )
        )
        fp.flush()
        # subprocess.run(["zam_generate_pdf_from_html", fp.name])
        subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).parent.parent.parent
                    / "scripts"
                    / "generate_pdf_from_html.py"
                ),
                "-i",
                fp.name,
                "-o",
                filename,
            ]
        )


def generate_pdf(content: str, filename: str) -> None:
    font_config = FontConfiguration()
    css = CSS(PDF_CSS, font_config=font_config)
    HTML(string=htmlmin.minify(content), encoding="utf-8").write_pdf(
        filename, stylesheets=[css], font_config=font_config
    )


def generate_pdf_mp(content: str, filename: str) -> None:
    # Use multiprocessing to minimize weasyprint memory leak
    # generate_pdf(content, filename)
    p = multiprocessing.Process(
        target=generate_pdf, args=(htmlmin.minify(content), filename)
    )
    p.start()
    p.join()


def generate_pdf_cmdline(content: str, filename: str) -> None:
    # Use multiprocessing to minimize weasyprint memory leak
    # generate_pdf(content, filename)
    with NamedTemporaryFile() as fp:
        fp.write(htmlmin.minify(content).encode("utf-8"))
        fp.flush()
        subprocess.run(
            [
                sys.executable,
                "-m",
                "weasyprint",
                "-f",
                "pdf",
                "-s",
                PDF_CSS,
                fp.name,
                filename,
            ]
        )
