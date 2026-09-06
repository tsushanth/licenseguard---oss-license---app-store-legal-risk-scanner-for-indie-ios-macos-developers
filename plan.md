# LicenseGuard — Local MVP Scaffold Plan

## Goal of this MVP

Prove the core value locally: point the tool at a dependency manifest from an
iOS/macOS project (SPM `Package.resolved`, CocoaPods `Podfile.lock`, or
Carthage `Cartfile.resolved`), get back a report that:

1. Lists every resolved dependency and its license.
2. Flags GPL/AGPL/LGPL and other App-Store-incompatible licenses.
3. Explains in plain language what specifically breaks Apple's distribution
   terms for each flagged dependency.
4. Auto-generates an attribution/acknowledgments file listing all
   permissively-licensed deps (the artifact an app would ship).

No deployment, no server, no CI integration yet — just a script the author
can run against their own 15 apps' lockfiles and get a real answer.

## 1. Stack choice

**Python 3, stdlib-only, single-file-first CLI.** No npm/pip install step,
no build, no compiled binary, no framework. Rationale over alternatives:

- Node/TS would require a `package.json` + `tsc`/`ts-node` step for
  something this small — extra ceremony with zero payoff at MVP size.
- Go gives a single binary (nice for later distribution) but slower to
  iterate on parsing three different lockfile formats during scoping.
- Python's stdlib (`json`, `re`, basic text parsing) is enough to parse all
  three manifest formats without adding a YAML dependency — CocoaPods'
  `Podfile.lock` is YAML but only needs a few well-known lines
  (`PODS:` block, name + version) pulled out with simple line parsing,
  not a full YAML parser.

Run as: `python3 scan.py <path-to-project-or-manifest>`

## 2. Explicitly out of scope for this MVP

- **Auth / accounts** — single local user, no login.
- **Billing / pricing enforcement** — irrelevant to proving the core scan.
- **Hosting / deploy / SaaS backend** — everything runs on the local
  filesystem.
- **CI GitHub Action** — "re-check on every dependency bump" is a
  distribution mechanism for the same core script, not new logic; skip the
  YAML workflow file and GitHub App plumbing entirely.
- **Live license lookup via GitHub/NPM/CocoaPods-trunk APIs** — no network
  calls. License data comes from a small curated static JSON file of known
  common iOS/macOS OSS packages (Alamofire, SDWebImage, Realm, etc.) plus an
  explicit "unknown — needs manual review" fallback for anything not in the
  table. This is enough to prove the detection + explanation + attribution
  pipeline against real lockfiles; swapping in a live license API is a
  post-MVP concern, not a blocker to demoing the value.
- **Real Xcode UI integration** — the "attribution screen" is generated as a
  Markdown/JSON/plist file the user could drop into a Settings.bundle or an
  in-app screen, not an actual compiled UI.
- **Batch scanning across all 15 apps in one run** — the CLI takes one
  manifest path per invocation; running it 15 times by hand is fine for
  proving the idea.

None of these are needed to demonstrate the core value: "does this tool
correctly detect and explain App-Store-incompatible licenses in a real
dependency tree, and can it produce a usable attribution list."

## 3. File / directory layout

```
licenseguard/
├── scan.py                  # CLI entry point: parse manifest -> classify -> report
├── license_db.json          # curated map: package name -> { license, source_url }
├── license_rules.json       # map: license id -> { risk, apple_tos_explanation }
├── samples/
│   ├── Package.resolved     # sample SPM manifest (mix of clean + flagged deps)
│   ├── Podfile.lock         # sample CocoaPods manifest
│   └── Cartfile.resolved    # sample Carthage manifest
├── tests/
│   └── test_scan.py         # unittest covering parsing + classification + attribution output
└── README.md                # what it is, how to run it, how to read the report
```

## 4. Verification plan

- **Unit tests** (`python3 -m unittest tests/test_scan.py`):
  - Each of the three manifest parsers correctly extracts (name, version)
    pairs from its sample file.
  - License classification correctly sorts known packages into
    permissive / weak-copyleft / copyleft / unknown buckets using
    `license_rules.json`.
  - Attribution file generation includes all permissive deps and excludes
    ones the tool flagged as blocking (or includes them with a warning,
    depending on how the report is designed — decided during
    implementation).
- **Manual run-through**: run `python3 scan.py samples/Package.resolved`,
  `python3 scan.py samples/Podfile.lock`, and
  `python3 scan.py samples/Cartfile.resolved`, and confirm by eye that:
  - At least one seeded GPL/AGPL/LGPL dependency in the samples is flagged
    with a specific, correct explanation of the Apple TOS conflict.
  - Permissively-licensed deps are not flagged.
  - An attribution file is written to disk and its contents match the
    permissive deps in the sample manifest.
- Once this passes against the hand-built samples, the real test is running
  it against the author's actual 15 apps' lockfiles and sanity-checking the
  output against what's actually in those dependency trees.
