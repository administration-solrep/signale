import logging
import sys
from argparse import ArgumentParser, Namespace
from typing import List

from pyramid.paster import bootstrap, setup_logging

logger = logging.getLogger(__name__)


def main(argv: List[str] = sys.argv) -> None:

    args = parse_args(argv[1:])

    setup_logging(args.config_uri)

    with bootstrap(args.config_uri, options={"app": "zam_queue"}) as env:
        request = env["request"]
        huey = request.huey
        count = count_pending = huey.pending_count()
        count_scheduled = huey.scheduled_count()
        if args.include_scheduled:
            count += count_scheduled
        if args.count_only:
            print(count)
        else:
            if args.include_scheduled:
                print(f"{count} total task(s) in queue")
            print(f"{count_pending} task(s) in pending queue")
            for task in huey.pending():
                print(task)
            if args.include_scheduled:
                print(f"{count_scheduled} task(s) in scheduled queue")
                for task in huey.scheduled():
                    print(task)


def parse_args(argv: List[str]) -> Namespace:
    parser = ArgumentParser()
    parser.add_argument("config_uri")
    parser.add_argument(
        "-c",
        "--count-only",
        action="store_true",
        help="Only show the number of queued tasks",
    )
    parser.add_argument(
        "--include-scheduled",
        action="store_true",
        help="Include scheduled tasks in output",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
