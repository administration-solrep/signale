import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AlertOnData(Exception):
    """Exception raised unexpected error during data scrapping.

    Attributes:
        message -- explanation of the error
        error_type:str 'http' | 'data'
        error_code:int 'http' => code http
                        'data' => custom
        url -- optional resource url
    """

    def __init__(
        self,
        message: str,
        error_type: str,
        error_code: int,
        url: Optional[str] = None,
        **kwargs: Any,
    ):

        super().__init__(message)
        self.message = message
        self.error = (error_type, error_code)
        self.url = url
