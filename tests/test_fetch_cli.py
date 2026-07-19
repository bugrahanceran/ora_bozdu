import logging

from app.fetch import build_parser, configure_logging


def test_fetch_cli_can_disable_retries() -> None:
    args = build_parser().parse_args(["--region", "eryaman", "--no-retries"])

    assert args.region == "eryaman"
    assert args.no_retries is True


def test_fetch_logging_suppresses_http_request_urls() -> None:
    configure_logging("INFO")

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
