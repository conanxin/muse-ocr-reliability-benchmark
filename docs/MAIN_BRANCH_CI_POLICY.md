# Main branch quality gates — P21

> This document records the **enforced repository configuration as of 2026-10-24**. The GitHub ruleset, not this Markdown file, is the source of truth. Repository admins should check the live settings before changing them.

## Active main ruleset

- Scope: **`refs/heads/main` only**; release tags and experimental branches are outside the ruleset.
- GitHub Ruleset: **[P21 main: required OCR cold-start CI](https://github.com/conanxin/muse-ocr-reliability-benchmark/rules/25770572)** (ID `25770572`).
- Enforcement: `active`.
- Require a pull request to change `main`. Required approval count: **0** (this rule guards on automated checks, not peer approvals).
- Require both GitHub Actions checks from integration ID `15368`:
  - `Python 3.10 / clean fixture`
  - `Python 3.12 / clean fixture`
- Require current-base / up-to-date checks (`strict_required_status_checks_policy=true`).
- Admin-only emergency exception: repository-role admin (role ID 5), bypass **through a pull request only**. Ordinary contributors cannot bypass, and the configured exception does **not** allow admin direct-push bypass.

## Evidence: intentionally failing pull request was blocked

[P21 canary PR #4](https://github.com/conanxin/muse-ocr-reliability-benchmark/pull/4) contained a deliberately failing unit test in a temporary branch. Both required jobs concluded `FAILURE` in [Actions run #40063676085](https://github.com/conanxin/muse-ocr-reliability-benchmark/actions/runs/40063676085). GitHub returned both REST `mergeable_state=blocked` and GraphQL `mergeStateStatus=BLOCKED`.

This PR was **never merged**. It was closed, the temporary branch deleted and `main` remained unchanged. No administrator bypass was attempted.

## Normal maintenance process

1. Create a topic branch and PR into `main`.
2. Confirm all checks represent a genuinely clean runner: no pre-generated synthetic PNG files; at least 19 tests discovered.
3. Verify that **both required jobs** pass on the latest applicable commit. A retry passing after the first run failed is **not** evidence of first-run reliability; investigate its root cause.
4. Merge normally (squash is recommended for small maintenance changes), then verify that the `main` push run is green.
5. Only tag a new release after its own source/CI validation. Do not move or rewrite `v0.1.0`, `v0.2.0` or `v0.2.1`.

## If CI is broken

- Inspect failing step and exit code before retrying. The workflow uses GitHub-hosted Ubuntu 24.04, Python 3.10/3.12, read-only repository permissions and fresh fixture images.
- If a GitHub Actions outage or broken workflow makes ordinary merge impossible, a repository **admin may explicitly invoke PR-only emergency bypass** and should document the reason in the PR. Bypass is a conscious exception, not a substitute for repairing CI.
- As a last resort, the repo administrator can inspect/disable rule `25770572` in **Settings → Rules → Rulesets** to restore operations, then promptly reinstate it with the same required contexts. Avoid disabling protections for routine changes.
- Check the current ruleset through GitHub's API; this documentation can become outdated if policy changes.

## Coverage boundaries

These are **test-suite and synthetic cold-start quality gates**, not validation of private scanned PDFs, all OCR languages, a complete model evaluation, user-selected source text or human transcription fidelity. The workflow does **not** depend on private image collections or credentials.
