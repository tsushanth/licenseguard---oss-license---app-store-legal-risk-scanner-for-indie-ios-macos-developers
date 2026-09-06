# LicenseGuard (local MVP)

A static-analysis CLI that scans an iOS/macOS app's dependency lockfile,
flags GPL/AGPL/LGPL and other App-Store-incompatible licenses, explains
*specifically* what breaks Apple's distribution terms, and generates an
attribution/acknowledgments file for the dependencies that are safe to ship.

This is the local-only MVP scoped in `../plan.md`: no auth, no billing, no
hosting, no CI integration, no live license-API calls. It runs entirely
against a manifest file on your filesystem using a small curated license
database (`license_db.json`).

## What it does

1. Parses one of three dependency lockfiles:
   - Swift Package Manager `Package.resolved` (v1 and v2 format)
   - CocoaPods `Podfile.lock`
   - Carthage `Cartfile.resolved`
2. Looks up each dependency's license in `license_db.json`. Anything not in
   the table is marked `Unknown` — needs manual review, never assumed safe.
3. Classifies each license by App Store risk using `license_rules.json`:
   - **permissive** (MIT, Apache-2.0, BSD, ISC, Zlib) — OK
   - **weak-copyleft** (LGPL-2.1, LGPL-3.0, MPL-2.0) — review required
     (LGPL's relinking requirement is hard to satisfy in a statically
     linked, code-signed App Store binary)
   - **copyleft** (GPL-2.0, GPL-3.0) — blocks App Store distribution
   - **network-copyleft** (AGPL-3.0) — blocks App Store distribution
   - **unknown** — needs manual review
4. Prints a report to stdout listing every dependency, its license, and a
   plain-language explanation of the specific Apple TOS conflict for each
   flagged one.
5. Writes an `ATTRIBUTIONS.md` file containing only the permissively-licensed
   dependencies — the acknowledgments screen content you'd ship in the app.
   Flagged dependencies are excluded from that list and called out in an
   HTML comment at the bottom so they're never silently dropped.
6. Exits with status `1` if any dependency blocks App Store distribution
   (copyleft/network-copyleft), and `0` otherwise — usable as a pass/fail
   gate later in CI, even though no CI plumbing is included in this MVP.

## Requirements

Python 3, no dependencies (stdlib only).

## Usage

```bash
python3 scan.py <path-to-manifest-or-project-dir> [--out ATTRIBUTIONS.md]
```

You can point it directly at a lockfile, or at a project directory — it
will look for `Package.resolved`, `Podfile.lock`, or `Cartfile.resolved`
inside it.

### Try it against the bundled samples

```bash
python3 scan.py samples/Package.resolved
python3 scan.py samples/Podfile.lock
python3 scan.py samples/Cartfile.resolved
```

Each sample mixes clean (MIT/Apache-2.0) dependencies with seeded
LGPL/GPL/AGPL/unknown ones so you can see every risk tier flagged with its
explanation, and confirm the generated `ATTRIBUTIONS.md` only lists the
safe dependencies.

### Run it against your own app

```bash
python3 scan.py /path/to/YourApp/Package.resolved --out /path/to/YourApp/ATTRIBUTIONS.md
```

Run once per app/manifest — batch-scanning multiple apps in one invocation
is out of scope for this MVP; loop over your apps by hand (or a one-line
shell `for` loop) if you have several to check.

## Reading the report

```
DEPENDENCY                  VERSION       LICENSE       STATUS
------------------------------------------------------------------------------
x264                        0.164.3101    GPL-2.0       BLOCKS App Store distribution
MobileVLCKit                3.5.1         LGPL-2.1      REVIEW REQUIRED
Alamofire                   5.9.1         MIT           OK
```

Dependencies are sorted worst-risk-first. Every flagged dependency gets a
"Flagged dependencies — details" section explaining exactly which Apple
policy or licensing mechanism it conflicts with, and a final summary line
with counts.

## Extending the license database

`license_db.json` is a small curated seed (Alamofire, SDWebImage, Kingfisher,
SnapKit, RxSwift, Realm, lottie-ios, MobileVLCKit, FFmpegKit, x264, etc.) —
enough to prove detection, explanation, and attribution generation against
real lockfiles. Add an entry for any package you use that shows up as
`Unknown`:

```json
"packagename": { "license": "MIT", "source_url": "https://github.com/org/repo" }
```

Package names are matched case-insensitively against whatever identity each
lockfile format uses (SPM identity, CocoaPods pod name, or the last path
segment of the Carthage `github "org/repo"` reference) — the same upstream
project can appear under different names across formats, so you may need an
alias entry per format (see `ffmpegkit` vs `ffmpeg-kit` in `license_db.json`).

`license_rules.json` maps each license identifier to a risk tier and the
Apple-TOS-specific explanation shown in the report — extend it if you add a
license identifier not already covered.

## Running the tests

```bash
python3 -m unittest tests/test_scan.py -v
```

Covers all three parsers, license classification into each risk tier, and
that attribution generation includes permissive deps while excluding (but
still surfacing) flagged ones.
