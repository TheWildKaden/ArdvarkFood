import sys
from types import ModuleType, SimpleNamespace

from cli.main import main


def test_tui_is_available_with_explicit_and_legacy_default_commands(
    monkeypatch,
) -> None:
    calls = []

    class FakeTUI:
        def run(self) -> None:
            calls.append("run")

    module = ModuleType("cli.app")
    module.TUIApp = FakeTUI
    monkeypatch.setitem(sys.modules, "cli.app", module)

    assert main(["tui"]) == 0
    assert main([]) == 0
    assert calls == ["run", "run"]


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
