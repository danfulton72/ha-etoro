#!/usr/bin/env python3
"""Semantic version helpers for CI/release automation.

Git tags are the source of truth. The Home Assistant manifest mirrors the
version that will be released next.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

TAG_RE = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
MANIFEST = Path("custom_components/etoro/manifest.json")


def semantic_tags() -> list[tuple[tuple[int, int, int], str]]:
    tags = subprocess.check_output(["git", "tag", "--list"], text=True).splitlines()
    parsed: list[tuple[tuple[int, int, int], str]] = []
    for tag in tags:
        match = TAG_RE.fullmatch(tag.strip())
        if match:
            version = tuple(int(match.group(part)) for part in ("major", "minor", "patch"))
            parsed.append((version, tag))
    return parsed


def highest() -> tuple[tuple[int, int, int], str]:
    tags = semantic_tags()
    if not tags:
        return (0, 0, 0), "v0.0.0"
    return max(tags, key=lambda item: item[0])


def version_text(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


def next_patch() -> tuple[int, int, int]:
    current, _ = highest()
    return current[0], current[1], current[2] + 1


def read_manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def sync_manifest(version: tuple[int, int, int]) -> bool:
    data = read_manifest()
    expected = version_text(version)
    if data.get("version") == expected:
        return False
    data["version"] = expected
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("highest")
    subparsers.add_parser("next")
    subparsers.add_parser("check-manifest-next")
    subparsers.add_parser("sync-manifest-next")
    args = parser.parse_args()

    current, current_tag = highest()
    upcoming = next_patch()
    upcoming_text = version_text(upcoming)

    if args.command == "highest":
        print(version_text(current))
        return
    if args.command == "next":
        print(upcoming_text)
        return
    if args.command == "check-manifest-next":
        manifest_version = str(read_manifest().get("version", ""))
        if manifest_version != upcoming_text:
            raise SystemExit(
                f"manifest.json version {manifest_version!r} is out of sync: "
                f"highest semantic tag is {current_tag}, so next release is v{upcoming_text}"
            )
        print(f"Version sync OK: {current_tag} -> v{upcoming_text}; manifest={manifest_version}")
        return
    if args.command == "sync-manifest-next":
        changed = sync_manifest(upcoming)
        print(upcoming_text)
        if changed:
            print(f"Synced manifest.json to {upcoming_text}", file=__import__("sys").stderr)
        return


if __name__ == "__main__":
    main()
