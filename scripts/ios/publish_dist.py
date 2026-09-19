#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--dist-dir", required=True)
    parser.add_argument("--icon", required=True)
    parser.add_argument("--created-at", required=True)
    args = parser.parse_args()

    artifact = Path(args.artifact_dir)
    dist = Path(args.dist_dir)
    dist.mkdir(parents=True, exist_ok=True)
    releases = dist / "releases"
    releases.mkdir(parents=True, exist_ok=True)

    bundle = read_text(artifact / "bundle-id.txt")
    version = read_text(artifact / "version.txt")
    build = read_text(artifact / "build-version.txt")
    size = int(read_text(artifact / "size.txt"))
    sha256 = read_text(artifact / "sha256.txt")
    ipa = artifact / "NEXTGENMonitor-unsigned.ipa"
    if bundle != "com.nextgen.monitor":
        raise SystemExit(f"unexpected bundle id: {bundle}")
    if not ipa.is_file() or ipa.stat().st_size != size:
        raise SystemExit("IPA size metadata does not match artifact")

    release_name = f"NEXTGENMonitor-{version}-{build}.ipa"
    shutil.copy2(ipa, releases / release_name)
    shutil.copy2(Path(args.icon), dist / "icon.png")

    raw_base = "https://raw.githubusercontent.com/Allower1/nextgen-monitor-dist/main"
    download_url = f"{raw_base}/releases/{release_name}"
    source_path = dist / "source.json"
    old_versions: list[dict] = []
    if source_path.exists():
        previous = json.loads(source_path.read_text(encoding="utf-8"))
        apps = previous.get("apps", [])
        if apps:
            old_versions = apps[0].get("versions", [])

    release = {
        "version": version,
        "buildVersion": build,
        "date": args.created_at,
        "downloadURL": download_url,
        "size": size,
        "minOSVersion": "17.0",
        "localizedDescription": (
            "Native SwiftUI NEXTGEN Monitor build. "
            f"Unsigned IPA SHA-256: {sha256}"
        ),
    }
    versions = [
        release,
        *[
            item for item in old_versions
            if str(item.get("buildVersion")) != build
        ],
    ][:20]

    app = {
        "name": "NEXTGEN Monitor",
        "bundleIdentifier": bundle,
        "developerName": "NEXTGEN",
        "subtitle": "Native paper-trading monitor",
        "localizedDescription": (
            "Native SwiftUI monitor for the NEXTGEN adaptive paper-trading runtime. "
            "Shows status, strategy changes, decisions, portfolio, fills and charts; "
            "safe controls are limited to status, pause and resume."
        ),
        "iconURL": f"{raw_base}/icon.png",
        "tintColor": "#2563EB",
        "category": "utilities",
        "versions": versions,
        "appPermissions": {
            "entitlements": [],
            "privacy": {
                "NSLocalNetworkUsageDescription": (
                    "NEXTGEN Monitor connects to your private "
                    "NEXTGEN paper-trading monitor API."
                )
            },
        },
    }
    source = {
        "name": "NEXTGEN Monitor",
        "identifier": "com.nextgen.monitor.source",
        "subtitle": "Official unsigned builds for SideStore/AltStore",
        "description": (
            "Unsigned native iOS builds generated from the private NEXTGEN source. "
            "Your own Apple Account signs them on-device."
        ),
        "website": "https://github.com/Allower1/nextgen-monitor-dist",
        "iconURL": f"{raw_base}/icon.png",
        "apps": [app],
        "news": [],
    }
    source_path.write_text(
        json.dumps(source, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    readme = dist / "README.md"
    readme.write_text(
        "# NEXTGEN Monitor iOS distribution\n\n"
        "This repository contains only unsigned NEXTGEN Monitor IPA builds, "
        "the app icon, and an AltStore/SideStore source feed.\n\n"
        "No Apple ID credentials, signing certificates, NEXTGEN source code, "
        "exchange credentials, or monitor API tokens are stored here.\n",
        encoding="utf-8",
    )
    print(release_name)


if __name__ == "__main__":
    main()
