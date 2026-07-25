import logging
from pathlib import Path

from app.fetch import build_parser, configure_logging


def test_fetch_cli_can_disable_retries() -> None:
    args = build_parser().parse_args(["--region", "eryaman", "--no-retries"])

    assert args.region == "eryaman"
    assert args.no_retries is True


def test_fetch_cli_supports_plan_flag() -> None:
    args = build_parser().parse_args(["--region", "eryaman", "--plan"])

    assert args.plan is True


def test_fetch_cli_accepts_a_per_region_data_collection_config() -> None:
    args = build_parser().parse_args(
        [
            "--region",
            "armada",
            "--data-collection-config",
            "config/data_collection.armada.yaml",
        ]
    )

    assert args.data_collection_config == Path("config/data_collection.armada.yaml")


def test_fetch_logging_suppresses_http_request_urls() -> None:
    configure_logging("INFO")

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
