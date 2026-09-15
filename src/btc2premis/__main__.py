"""Allow running the CLI via ``python -m btc2premis``."""

from btc2premis.cli import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
