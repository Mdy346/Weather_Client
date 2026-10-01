"""Allow ``python -m weather_client`` to run the CLI."""

from weather_client.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
