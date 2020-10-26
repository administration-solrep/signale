from subprocess import STDOUT, CalledProcessError, check_output  # nosec
from typing import List

from pyramid.config import Configurator

VERSION = "1.5.1"


def load_version(config: Configurator) -> None:
    config.registry.settings["version"] = {
        "version": VERSION,
    }


def run(command: List[str]) -> str:
    try:
        # This is considered safe as we only run predefined git commands
        res: bytes = check_output(command, stderr=STDOUT)  # nosec
        return res.decode("utf-8").strip()
    except CalledProcessError:
        return "unknown"
