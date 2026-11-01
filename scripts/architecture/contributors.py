from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


PALETTE = ("#1f2937", "#334155", "#475569", "#0f766e", "#7c3aed", "#b45309")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def repository_name(root: Path) -> str:
    import os

    configured = os.getenv("GITHUB_REPOSITORY")
    if configured and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", configured):
        return configured
    try:
        remote = _git(root, "remote", "get-url", "origin")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "TheWildKaden/ArdvarkFood"
    match = re.search(
        r"(?:github\.com[:/])([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?$",
        remote,
    )
    return match.group(1) if match else "TheWildKaden/ArdvarkFood"


def _github_json(url: str, token: str | None) -> Any | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ArdvarkFood-architecture-generator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        if error.code in {403, 429}:
            remaining = error.headers.get("X-RateLimit-Remaining", "unknown")
            print(
                f"GitHub API rate limit/permission response (HTTP {error.code}, "
                f"remaining={remaining}); using local git statistics.",
                flush=True,
            )
        else:
            print(f"GitHub API returned HTTP {error.code}; using local git data.", flush=True)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        print(f"GitHub API unavailable ({error}); using local git data.", flush=True)
    return None


def _avatar_svg(name: str, color: str) -> str:
    initials = "".join(part[0] for part in name.split()[:2]).upper() or "?"
    initials = html.escape(initials[:2])
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" '
        'viewBox="0 0 96 96" role="img" aria-label="Contributor avatar">'
        f'<rect width="96" height="96" rx="48" fill="{color}"/>'
        f'<text x="48" y="58" text-anchor="middle" fill="#ffffff" '
        'font-family="Arial,sans-serif" font-size="32" font-weight="700">'
        f"{initials}</text></svg>\n"
    )


def _statistics_svg(stats: dict[str, Any]) -> str:
    fields = [
        ("Commits", stats["commits"]),
        ("Contributors", stats["contributors"]),
        ("Source files", stats["source_files"]),
        ("API routes", stats["api_routes"]),
        ("Stars", stats.get("stars", "—")),
        ("Forks", stats.get("forks", "—")),
    ]
    cells = []
    for index, (title, value) in enumerate(fields):
        column, row = index % 3, index // 3
        x, y = 24 + column * 190, 60 + row * 84
        cells.append(
            f'<text x="{x}" y="{y}" fill="#94a3b8" font-size="13">'
            f"{html.escape(str(title))}</text>"
            f'<text x="{x}" y="{y + 28}" fill="#f8fafc" font-size="23" '
            f'font-weight="700">{html.escape(str(value))}</text>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="620" height="210" '
        'viewBox="0 0 620 210" role="img" aria-label="Repository statistics">'
        '<rect width="620" height="210" rx="16" fill="#111827"/>'
        '<text x="24" y="30" fill="#e2e8f0" font-family="Arial,sans-serif" '
        'font-size="15" font-weight="700">ArdvarkFood · repository snapshot</text>'
        f'{"".join(cells)}</svg>\n'
    )


def generate(
    root: Path,
    output_dir: Path,
    *,
    token: str | None,
    repo: str | None = None,
    offline: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    import os

    repo = repo or repository_name(root)
    authors: Counter[str] = Counter()
    try:
        raw_authors = _git(root, "log", "--format=%aN", "HEAD").splitlines()
        authors.update(name.strip() for name in raw_authors if name.strip())
        commit_count = int(_git(root, "rev-list", "--count", "HEAD") or 0)
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        commit_count = 0

    contributors: list[dict[str, Any]] = []
    repository_stats: dict[str, Any] = {}
    source = "local git author names"
    if not offline and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        api_contributors = _github_json(
            f"https://api.github.com/repos/{repo}/contributors?per_page=100",
            token,
        )
        if isinstance(api_contributors, list):
            source = "GitHub contributors API (first 100 accounts)"
            contributors = [
                {
                    "login": item.get("login"),
                    "name": item.get("login") or "Contributor",
                    "profile_url": item.get("html_url"),
                    "contributions": item.get("contributions", 0),
                }
                for item in api_contributors
                if isinstance(item, dict) and not item.get("type") == "Bot"
            ]
        api_repository = _github_json(f"https://api.github.com/repos/{repo}", token)
        if isinstance(api_repository, dict):
            repository_stats = {
                "stars": api_repository.get("stargazers_count", "—"),
                "forks": api_repository.get("forks_count", "—"),
                "open_issues": api_repository.get("open_issues_count", "—"),
                "default_branch": api_repository.get("default_branch"),
            }

    if not contributors:
        contributors = [
            {
                "login": None,
                "name": name,
                "profile_url": None,
                "contributions": count,
            }
            for name, count in authors.most_common(100)
        ]

    output_dir.mkdir(parents=True, exist_ok=True)
    avatar_dir = output_dir / "contributors"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    for item in contributors:
        identity = item.get("login") or item["name"]
        slug = hashlib.sha256(identity.casefold().encode("utf-8")).hexdigest()[:12]
        item["avatar"] = f"docs/architecture/assets/contributors/{slug}.svg"
        color_index = int(slug[:4], 16) % len(PALETTE)
        (avatar_dir / f"{slug}.svg").write_text(
            _avatar_svg(item["name"], PALETTE[color_index]),
            encoding="utf-8",
        )

    stats = {
        **repository_stats,
        "repository": repo,
        "commits": commit_count,
        "contributors": len(contributors),
        "source_files": int(os.getenv("ARDVARK_SOURCE_FILE_COUNT", "0")),
        "api_routes": int(os.getenv("ARDVARK_API_ROUTE_COUNT", "0")),
        "contributors_source": source,
    }
    contributor_data = {
        "repository": repo,
        "source": source,
        "contributors": contributors,
    }
    (output_dir / "contributors.json").write_text(
        json.dumps(contributor_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "statistics.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "statistics.svg").write_text(
        _statistics_svg(stats),
        encoding="utf-8",
    )
    return contributor_data, stats
