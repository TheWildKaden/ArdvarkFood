import sys
from types import SimpleNamespace

from cli.main import main


def test_serve_command_starts_the_stable_asgi_entry_point(monkeypatch) -> None:
    calls = []
    monkeypatch.setitem(
        sys.modules,
        "uvicorn",
        SimpleNamespace(run=lambda *args, **kwargs: calls.append((args, kwargs))),
    )

    assert main(["serve", "--host", "127.0.0.1", "--port", "8765", "--reload"]) == 0
    assert calls == [
        (
            ("app:app",),
            {
                "host": "127.0.0.1",
                "port": 8765,
                "reload": True,
            },
        )
    ]
