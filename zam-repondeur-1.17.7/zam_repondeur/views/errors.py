import logging
import uuid
from typing import Any

from pyramid.request import Request
from pyramid.view import notfound_view_config, view_config

from zam_repondeur import IS_PRODUCTION

logger = logging.getLogger(__name__)


@notfound_view_config(renderer="not_found_error.html")
def not_found_view(request: Request) -> dict:
    request.response.status = 404  # type: ignore
    return {"current_tab": "notfound"}


if IS_PRODUCTION:

    @view_config(context=Exception, renderer="uncaught_error.html")
    def error_view(exc: Any, request: Request) -> dict:
        code = uuid.uuid4()
        logger.error(f"UNCAUGHT ERROR : {code}")
        logger.error(exc)
        logger.error(request)
        return {"code": code}
