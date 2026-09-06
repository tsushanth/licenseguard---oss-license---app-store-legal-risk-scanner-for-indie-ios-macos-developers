#!/usr/bin/env python3
"""LicenseGuard: static OSS license/App-Store-risk scanner for iOS/macOS
dependency manifests (SPM Package.resolved, CocoaPods Podfile.lock,
Carthage Cartfile.resolved).

Usage:
    python3 scan.py <path-to-manifest-or-project-dir> [--out ATTRIBUTIONS.md]
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LICENSE_DB = os.path.join(HERE, "license_db.json")
DEFAULT_LICENSE_RULES = os.path.join(HERE, "license_rules.json")

SPM_CANDIDATES = [
    "Package.resolved",
    os.path.join(".swiftpm", "configuration", "Package.resolved"),
]
COCOAPODS_CANDIDATES = ["Podfile.lock"]
CARTHAGE_CANDIDATES = ["Cartfile.resolved"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_manifest(path):
    """Given a file path, return it as-is. Given a directory, look for a
    known manifest file inside it. Returns (manifest_path, manifest_type)."""
    if os.path.isfile(path):
        return path, detect_manifest_type(path)

    if os.path.isdir(path):
        for rel in SPM_CANDIDATES:
            candidate = os.path.join(path, rel)
            if os.path.isfile(candidate):
                return candidate, "spm"
        for rel in COCOAPODS_CANDIDATES:
            candidate = os.path.join(path, rel)
            if os.path.isfile(candidate):
                return candidate, "cocoapods"
        for rel in CARTHAGE_CANDIDATES:
            candidate = os.path.join(path, rel)
            if os.path.isfile(candidate):
                return candidate, "carthage"
        raise FileNotFoundError(
            f"No Package.resolved, Podfile.lock, or Cartfile.resolved found under {path}"
        )

    raise FileNotFoundError(f"No such file or directory: {path}")


def detect_manifest_type(path):
    name = os.path.basename(path)
    if name == "Package.resolved":
        return "spm"
    if name == "Podfile.lock":
        return "cocoapods"
    if name == "Cartfile.resolved":
        return "carthage"
    raise ValueError(
        f"Unrecognized manifest file '{name}'. Expected Package.resolved, "
        "Podfile.lock, or Cartfile.resolved."
    )


def parse_spm_resolved(path):
    """Parse SPM Package.resolved (v1 or v2 format) into (name, version) pairs."""
    data = load_json(path)
    deps = []

    if "pins" in data:
        pins = data["pins"]
    elif "object" in data and "pins" in data["object"]:
        pins = data["object"]["pins"]
    else:
        pins = []

    for pin in pins:
        name = pin.get("identity") or pin.get("package") or "unknown"
        state = pin.get("state", {}) or {}
        version = state.get("version") or state.get("revision") or "unknown"
        deps.append((name, version))

    return deps


def parse_podfile_lock(path):
    """Parse CocoaPods Podfile.lock, extracting only top-level pods (2-space
    indent) from the PODS: block, ignoring nested subspecs (4+ space indent)."""
    deps = []
    in_pods_block = False
    top_level_re = re.compile(r"^  - ([A-Za-z0-9_+.\/-]+) \(([^)]+)\)")

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.rstrip("\n")
            if stripped == "PODS:":
                in_pods_block = True
                continue
            if in_pods_block:
                if stripped and not stripped.startswith(" "):
                    # left the PODS: block (e.g. "DEPENDENCIES:")
                    break
                match = top_level_re.match(stripped)
                if match:
                    name, version = match.group(1), match.group(2)
                    # Drop CocoaPods subspec suffix, e.g. "SDWebImage/Core"
                    base_name = name.split("/")[0]
                    deps.append((base_name, version))

    return deps


def parse_cartfile_resolved(path):
    """Parse Carthage Cartfile.resolved lines like:
    github "Alamofire/Alamofire" "5.8.0"
    git "https://github.com/foo/bar" "1.0.0"
    binary "https://example.com/foo.json" "1.0.0"
    """
    deps = []
    line_re = re.compile(r'^(github|git|binary)\s+"([^"]+)"\s+"([^"]+)"')

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            match = line_re.match(line.strip())
            if not match:
                continue
            _, ref, version = match.groups()
            # ref is "org/repo" for github, a URL for git/binary
            name = ref.rstrip("/").split("/")[-1]
            name = re.sub(r"\.git$", "", name)
            deps.append((name, version))

    return deps


PARSERS = {
    "spm": parse_spm_resolved,
    "cocoapods": parse_podfile_lock,
    "carthage": parse_cartfile_resolved,
}


def classify(name, version, license_db, license_rules):
    """Look up a dependency's license and App-Store risk classification."""
    entry = license_db.get(name.lower())
    license_id = entry["license"] if entry else "Unknown"
    source_url = entry.get("source_url") if entry else None
    rule = license_rules.get(license_id, license_rules["Unknown"])

    return {
        "name": name,
        "version": version,
        "license": license_id,
        "source_url": source_url,
        "risk": rule["risk"],
        "blocks_app_store": rule["blocks_app_store"],
        "explanation": rule["apple_tos_explanation"],
    }


RISK_ORDER = {
    "copyleft": 0,
    "network-copyleft": 0,
    "weak-copyleft": 1,
    "unknown": 2,
    "permissive": 3,
}

RISK_LABEL = {
    "copyleft": "BLOCKS App Store distribution",
    "network-copyleft": "BLOCKS App Store distribution",
    "weak-copyleft": "REVIEW REQUIRED",
    "unknown": "NEEDS MANUAL REVIEW",
    "permissive": "OK",
}


def generate_report(manifest_path, manifest_type, classified_deps):
    lines = []
    lines.append(f"LicenseGuard scan report — {manifest_path} ({manifest_type})")
    lines.append("=" * len(lines[0]))
    lines.append("")

    sorted_deps = sorted(classified_deps, key=lambda d: RISK_ORDER[d["risk"]])

    lines.append(f"{'DEPENDENCY':<28}{'VERSION':<14}{'LICENSE':<14}{'STATUS'}")
    lines.append("-" * 78)
    for dep in sorted_deps:
        lines.append(
            f"{dep['name']:<28}{dep['version']:<14}{dep['license']:<14}{RISK_LABEL[dep['risk']]}"
        )
    lines.append("")

    flagged = [d for d in sorted_deps if d["risk"] != "permissive"]
    if flagged:
        lines.append("Flagged dependencies — details")
        lines.append("-" * 31)
        for dep in flagged:
            lines.append(f"* {dep['name']} {dep['version']} — {dep['license']} ({RISK_LABEL[dep['risk']]})")
            lines.append(f"  {dep['explanation']}")
            lines.append("")
    else:
        lines.append("No copyleft, network-copyleft, or unknown-license dependencies found.")
        lines.append("")

    blocking = [d for d in sorted_deps if d["blocks_app_store"]]
    permissive_count = len(sorted_deps) - len(flagged)
    lines.append(
        f"Summary: {len(sorted_deps)} dependencies scanned, "
        f"{permissive_count} permissive, {len(flagged)} flagged, "
        f"{len(blocking)} blocking App Store distribution."
    )

    return "\n".join(lines)


def generate_attribution(classified_deps):
    """Markdown attribution/acknowledgments file listing permissively-licensed
    dependencies. Flagged (copyleft/network-copyleft/unknown) dependencies are
    excluded from the acknowledgments list and called out separately so they
    are not accidentally shipped without resolving their risk first."""
    permissive = [d for d in classified_deps if d["risk"] == "permissive"]
    other = [d for d in classified_deps if d["risk"] != "permissive"]

    lines = ["# Acknowledgements", "", "This app uses the following open-source software:", ""]
    for dep in sorted(permissive, key=lambda d: d["name"].lower()):
        if dep["source_url"]:
            lines.append(f"- **{dep['name']}** {dep['version']} — {dep['license']} ({dep['source_url']})")
        else:
            lines.append(f"- **{dep['name']}** {dep['version']} — {dep['license']}")

    if other:
        lines.append("")
        lines.append(
            "<!-- The following dependencies were EXCLUDED from this list because "
            "LicenseGuard flagged them (copyleft, network-copyleft, or unknown "
            "license). Resolve their status before shipping: "
            + ", ".join(f"{d['name']} ({d['license']})" for d in other)
            + " -->"
        )

    return "\n".join(lines) + "\n"


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2

    target = argv[0]
    out_path = "ATTRIBUTIONS.md"
    if "--out" in argv:
        out_path = argv[argv.index("--out") + 1]

    license_db = load_json(DEFAULT_LICENSE_DB)
    license_rules = load_json(DEFAULT_LICENSE_RULES)

    manifest_path, manifest_type = find_manifest(target)
    deps = PARSERS[manifest_type](manifest_path)

    if not deps:
        print(f"No dependencies found in {manifest_path}", file=sys.stderr)
        return 1

    classified = [classify(name, version, license_db, license_rules) for name, version in deps]

    report = generate_report(manifest_path, manifest_type, classified)
    print(report)

    attribution = generate_attribution(classified)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(attribution)
    print(f"\nAttribution file written to {out_path}")

    blocking = any(d["blocks_app_store"] for d in classified)
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
