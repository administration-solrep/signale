import logging
from datetime import datetime
from time import struct_time
from typing import Any

from pytz import timezone, utc


def tz_europe_paris(*args: Any) -> struct_time:
    utc_dt = utc.localize(datetime.utcnow())
    my_tz = timezone("Europe/Paris")
    converted = utc_dt.astimezone(my_tz)
    return converted.timetuple()


class SignaleFormatter(logging.Formatter):
    converter = tz_europe_paris
