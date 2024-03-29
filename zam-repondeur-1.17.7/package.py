import shlex
import subprocess
from itertools import chain

from setuptools import Command

WHEELHOUSE = "wheelhouse"
PIP = "pip"


class Package(Command):
    """Package Code and Dependencies into wheelhouse"""

    description = "Run wheels for dependencies and submodules dependencies"
    user_options = []

    def __init__(self, dist):
        Command.__init__(self, dist)

    def initialize_options(self):
        """Set default values for options."""
        pass

    def finalize_options(self):
        """Post-process options."""

    pass

    def localize_requirements(self):
        """
        After the package is unpacked at the target destination, the requirements can
        be installed locally from the wheelhouse folder using the option --no-index on
        pip install which ignores package index (only looking at --find-links
        URLs instead).  --find-links <url | path> looks for archive from url or path
        Since the original requirements.txt might have links to a non pip repo such as
        github (https) it will parse the links for the archive from a url and not from
        the wheelhouse. This functions creates a new requirements.txt with the only name
        and version for each of the packages, thus eliminating the need to fetch / parse
        links from http sources and install all archives from the wheelhouse.
        """
        main_dependencies = (
            line.strip() for line in open("requirements.txt", "r").readlines()
        )
        prod_dependencies = (
            line.strip() for line in open("requirements-prod.txt", "r").readlines()
        )

        local_dependencies = []
        for dependency in chain(main_dependencies, prod_dependencies):
            if dependency:
                if "idlv-nexus-01.lyon-dev2" in dependency:
                    continue
                if "egg=" in dependency:
                    pkg_name = dependency.split("egg=")[-1]
                    local_dependencies.append(pkg_name)
                elif "git+" in dependency:
                    pkg_name = dependency.split("/")[-1].split(".")[0]
                    local_dependencies.append(pkg_name)
                else:
                    local_dependencies.append(dependency)
        print("local packages in wheel:", "\r\n".join(local_dependencies))
        with open("deploy_requirements.txt", "w") as requirements_file:
            # filter is used to remove empty list members (None).
            requirements_file.write("\n".join(filter(None, local_dependencies)))

    def execute(self, command, capture_output=False):
        """
        The execute command will loop and keep on reading the stdout and check for the
        return code and displays the output in real time.
        """
        print("Running shell command: ", command)
        if capture_output:
            return subprocess.check_output(shlex.split(command))
        process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)
        while True:
            output = process.stdout.readline()
            if output == b"" and process.poll() is not None:
                break
            if output:
                print(output.strip())
        return_code = process.poll()
        if return_code != 0:
            print("Error running command ", command, return_code)
            raise IOError("Shell Commmand Failed")
        return return_code

    def run_commands(self, commands):
        for command in commands:
            self.execute(command)

    def run(self):
        commands = []
        # le nommage du package cryptography bloque l'installation
        # il faut le rebuilder pour avoir un nom de package correct
        commands.extend(
            [
                "rm -rf {dir}".format(dir=PIP),
                "mkdir -p {dir}".format(dir=PIP),
                "pip wheel --no-cache-dir --wheel-dir={dir} \
                 -r pip_packaging_requirements.txt".format(
                    dir=PIP
                ),
                "rm -rf {dir}".format(dir=WHEELHOUSE),
                "mkdir -p {dir}".format(dir=WHEELHOUSE),
                "pip wheel --no-cache-dir \
                 --wheel-dir={dir} -r requirements.txt".format(
                    dir=WHEELHOUSE
                ),
                "pip wheel --no-cache-dir --wheel-dir={dir} \
                 -r requirements-prod.txt".format(
                    dir=WHEELHOUSE
                ),
            ]
        )

        print("Packing requirements.txt into wheelhouse")
        for command in commands:
            self.execute(command)
        print("Generating local requirements.txt")
        self.localize_requirements()
        print("Packing code and wheelhouse into dist")
        self.run_command("sdist")
