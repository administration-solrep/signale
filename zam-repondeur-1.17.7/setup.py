from setuptools import find_packages, setup

from package import Package

requires = [
    "alembic",
    "bleach",
    "cachecontrol[filecache]",
    "dataclasses",
    "defusedxml",
    "huey[redis]",
    "inscriptis",
    "lxml",
    "more-itertools",
    "openpyxl",
    "parsy",
    "pathvalidate",
    "progressist",
    "psycopg2-binary",
    "pyramid",
    "pyramid-default-cors",
    "pyramid-jinja2",
    "pyramid-mailer",
    "pyramid-retry",
    "pyramid-tm",
    "python-redis-lock",
    "python-slugify",
    "python-throttle",
    "redis",
    "requests",
    "rollbar",
    "selectolax",
    "SQLAlchemy>=1.3",
    "SQLAlchemy-Utils",
    "transaction",
    "ujson",
    "weasyprint",
    "xmltodict",
    "xvfbwrapper",
    "zope.sqlalchemy",
]

setup(
    name="zam-repondeur",
    version="1.17.7",
    install_requires=requires,
    packages=find_packages(),
    include_package_data=True,
    cmdclass={"package": Package},
    entry_points={
        "paste.app_factory": ["main = zam_repondeur:make_app"],
        "console_scripts": [
            "zam_worker = zam_repondeur.scripts.worker:main",
            "zam_fetch_amendements = zam_repondeur.scripts.fetch_amendements:main",
            "zam_load_data = zam_repondeur.scripts.load_data:main",
            "zam_reset_data_locks = zam_repondeur.scripts.reset_data_locks:main",
            "zam_whitelist = zam_repondeur.scripts.whitelist:main",
            "zam_admin = zam_repondeur.scripts.admin:main",
            "zam_queue = zam_repondeur.scripts.queue_monitor:main",
            "zam_update_dossiers = zam_repondeur.scripts.update_dossiers:main",
            "zam_version = zam_repondeur.scripts.version:main",
            "zam_force_amdts_an = zam_repondeur.scripts.recup_amdts_an:main",
            "zam_suppression_non_admin = zam_repondeur.scripts.\
suppression_non_admins:main",
            "zam_archivage_dossiers = zam_repondeur.scripts.archivage_dossiers:main",
            "zam_suppression_dossiers = zam_repondeur.scripts.\
suppression_dossiers:main",
            "zam_generate_pdf_from_html = zam_repondeur.scripts.generate_pdf_from_html:main",

        ],
    },
)
