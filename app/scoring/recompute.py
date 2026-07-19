import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.db import SessionLocal
from app.scoring.config import load_scoring_config
from app.scoring.engine import ScoringEngine
from app.scoring.service import recompute_region


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recompute versioned venue scores")
    parser.add_argument("--region", default="eryaman")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--score-version", help="Must match the config version")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    config = load_scoring_config(args.config or settings.scoring_config_path)
    if args.score_version and args.score_version != config.version:
        raise SystemExit(
            f"Requested {args.score_version!r}, config contains {config.version!r}"
        )
    with SessionLocal() as session:
        computed = recompute_region(
            session,
            region_slug=args.region,
            engine=ScoringEngine(config),
        )
    print(
        json.dumps(
            {
                "region": args.region,
                "score_version": config.version,
                "computed_venues": computed,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
