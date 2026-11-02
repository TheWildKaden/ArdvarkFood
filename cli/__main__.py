"""Entry point: ``python -m tuiapp``."""

from .app import TUIApp


def main() -> None:
    TUIApp().run()


if __name__ == "__main__":
    main()
