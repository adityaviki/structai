# Project guidance

## Maintaining the changelog

This repo uses [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) (see `CHANGELOG.md`) with [Semantic Versioning](https://semver.org/).

When you make a notable change:

- Add a bullet under `## [Unreleased]` in `CHANGELOG.md` **in the same commit as the code change** — not as a follow-up.
- Pick the right section: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, or `Security`. Create the heading if it doesn't exist yet under `[Unreleased]`.
- Keep entries short and user-facing — describe the impact, not the implementation.
- When cutting a release: rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`, add a fresh empty `[Unreleased]` on top, and add a comparison link at the bottom of the file.

What counts as "notable": user-visible behavior changes, new features, dependency changes, breaking API changes, schema migrations, plan/architecture revisions in `plans/`. Pure refactors and internal-only changes can be skipped.
