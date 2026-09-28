#!/usr/bin/env python3
"""check_profile_health.py — Validiert Profil-Vollständigkeit, Asset-Integrität, Badges und Repo-Index von lukisch/lukisch."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)


def check_local_assets(repo_root: Path) -> list[str]:
    errors = []
    readme_path = repo_root / "README.md"
    if not readme_path.exists():
        return ["README.md existiert nicht!"]

    content = readme_path.read_text(encoding="utf-8", errors="replace")

    # Finde alle relativen Asset-Pfade wie src="assets/..." oder (assets/...)
    asset_refs = re.findall(r'(?:src=["\']|\]\()((?:assets/[^"\'\)]+))', content)
    for ref in asset_refs:
        target = repo_root / ref
        if not target.exists():
            errors.append(f"Fehlendes Asset: {ref}")
        elif target.stat().st_size == 0:
            errors.append(f"Leeres Asset: {ref}")

    return errors


def check_badges(repo_root: Path) -> list[str]:
    """Validiert Shield-Badges und lokale SVG-Badges in README.md."""
    errors = []
    readme_path = repo_root / "README.md"
    if not readme_path.exists():
        return ["README.md existiert nicht!"]

    content = readme_path.read_text(encoding="utf-8", errors="replace")

    # 1. Prüfe img.shields.io Badges
    shields = re.findall(r'https://img\.shields\.io/badge/([^"\'\s>]+)', content)
    for badge in shields:
        # Format ist typischerweise label-message-color
        parts = badge.split("?")[0].split("-")
        if len(parts) < 2:
            errors.append(f"Ungültige Shield-Badge-Syntax: {badge}")

    # 2. Prüfe lokale Badge-Assets
    badge_assets = list((repo_root / "assets").glob("badge-*.svg"))
    if not badge_assets:
        errors.append("Keine lokalen badge-*.svg Dateien in assets/ gefunden.")
    else:
        for b in badge_assets:
            if b.stat().st_size == 0:
                errors.append(f"Badge-Datei ist leer: {b.name}")

    return errors


def check_public_repos_index(repo_root: Path) -> list[str]:
    """Prüft, ob alle öffentlichen lukisch-Repositories im README oder llms.txt gelistet sind."""
    errors = []
    readme_path = repo_root / "README.md"
    llms_path = repo_root / "llms.txt"

    content = ""
    if readme_path.exists():
        content += readme_path.read_text(encoding="utf-8", errors="replace")
    if llms_path.exists():
        content += llms_path.read_text(encoding="utf-8", errors="replace")

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repos = []

    # Prüfe ob gh CLI vorhanden ist
    try:
        res = subprocess.run(
            ["gh", "repo", "list", "lukisch", "--limit", "100", "--visibility", "public", "--json", "name"],
            capture_output=True, text=True, timeout=15, check=False
        )
        if res.returncode == 0:
            data = json.loads(res.stdout)
            repos = [r["name"] for r in data]
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
        logger.debug("gh CLI Aufruf fehlgeschlagen: %s", e)

    if not repos and token:
        # Fallback auf GitHub REST API
        try:
            req = urllib.request.Request(
                "https://api.github.com/users/lukisch/repos?type=public&per_page=100",
                headers={"Authorization": f"Bearer {token}", "User-Agent": "lukisch-profile-health"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                repos = [r["name"] for r in data]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            print(f"[WARNUNG] GitHub API nicht erreichbar: {e}")

    if repos:
        for r in repos:
            if r.lower() == "lukisch":  # Profil-Repo selbst muss nicht zwingend im eigenen Text verlinkt sein
                continue
            if r not in content:
                print(f"[DRIFT] Öffentliches Repository '{r}' fehlt möglicherweise im Profil-Index.")

    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    print(f"=== Prüfe Profile Health in {repo_root} ===")

    asset_errors = check_local_assets(repo_root)
    if asset_errors:
        print("[FEHLER] Lokale Asset-Fehler:")
        for err in asset_errors:
            print(f"  - {err}")
        return 1
    print("[OK] Alle referenzierten Assets existieren und sind nicht leer.")

    badge_errors = check_badges(repo_root)
    if badge_errors:
        print("[FEHLER] Badge-Fehler:")
        for err in badge_errors:
            print(f"  - {err}")
        return 1
    print("[OK] Alle Badges (Shields & lokale SVGs) sind syntaktisch valide.")

    repo_errors = check_public_repos_index(repo_root)
    if repo_errors:
        print("[FEHLER] Repo-Index-Fehler:")
        for err in repo_errors:
            print(f"  - {err}")
        return 1

    print("[OK] Profile Health Check erfolgreich abgeschlossen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
