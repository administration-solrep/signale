from typing import Any, Dict, Optional

import jinja2
from pyramid.config import Configurator
from pyramid.registry import Registry
from pyramid.settings import asbool
from pyramid.threadlocal import get_current_registry
from pyramid_jinja2 import Environment, IJinja2Environment

FILTERS_PATH = "zam_repondeur.views.jinja2_filters"

JINJA2_SETTINGS = {
    "jinja2.filters": {
        "paragriphy": f"{FILTERS_PATH}:paragriphy",
        "amendement_matches": f"{FILTERS_PATH}:amendement_matches",
        "filter_out_empty_additionals": f"{FILTERS_PATH}:filter_out_empty_additionals",
        "group_by_day": f"{FILTERS_PATH}:group_by_day",
        "h3_to_h5": f"{FILTERS_PATH}:h3_to_h5",
        "enumeration": f"{FILTERS_PATH}:enumeration",
        "length_including_batches": f"{FILTERS_PATH}:length_including_batches",
        "human_readable_day_of_month": f"{FILTERS_PATH}:human_readable_day_of_month",
        "human_readable_time": f"{FILTERS_PATH}:human_readable_time",
        "human_readable_date_and_time": f"{FILTERS_PATH}:human_readable_date_and_time",
    },
    "jinja2.undefined": "strict",
    "jinja2.trim_blocks": "true",
    "jinja2.lstrip_blocks": "true",
}


def includeme(config: Configurator) -> None:
    config.add_settings(JINJA2_SETTINGS)
    config.include("pyramid_jinja2")
    config.add_jinja2_renderer(".html")
    config.add_jinja2_search_path("zam_repondeur:templates", name=".html")
    config.add_jinja2_renderer(".txt")
    config.add_jinja2_search_path("zam_repondeur:templates", name=".txt")


def render_template(
    name: str, context: Dict[str, Any], registry: Optional[Registry] = None
) -> str:
    env = get_jinja2_environment(registry)
    template = env.get_template(name)
    content: str = template.render(**context)
    return content


def get_jinja2_environment_pyramidless() -> Environment:
    import jinja2
    from importlib import import_module

    jinja2_settings = {}
    filters = {}
    for setting_name in (n for n in JINJA2_SETTINGS if n.startswith("jinja2.")):
        setting_value = JINJA2_SETTINGS[setting_name]
        setting_name = setting_name[7:]
        if setting_name == "filters":
            for filter_name, filter_value in setting_value.items():  # type: ignore
                module, func = filter_value.split(":", 1)
                mod = import_module(module)
                filters[filter_name] = getattr(mod, func)
        else:
            setting_value = cast_jinja2_setting(setting_name, setting_value)
            jinja2_settings[setting_name] = setting_value

    env = jinja2.Environment(
        loader=jinja2.PackageLoader("zam_repondeur"),
        autoescape=True,
        **jinja2_settings,  # type: ignore
    )
    env.filters.update(filters)
    return env


def cast_jinja2_setting(setting_name, setting_value):
    if setting_name in ("autoescape", "trim_blocks", "optimized", "lstrip_blocks",):
        setting_value = asbool(setting_value)
    elif setting_name == "undefined":
        if setting_value == "strict":
            setting_value = jinja2.StrictUndefined  # type: ignore
        elif setting_value == "debug":
            setting_value = jinja2.DebugUndefined  # type: ignore
        else:
            setting_value = jinja2.Undefined  # type: ignore
    return setting_value


def get_jinja2_environment(registry: Optional[Registry] = None) -> Environment:
    if registry is None:
        registry = get_current_registry()
    env: Optional[Environment] = registry.queryUtility(IJinja2Environment, name=".html")
    if env is None:
        env = get_jinja2_environment_pyramidless()
    if env is None:
        raise RuntimeError("No Jinja2 environment configured")
    return env
