# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial implementation plan in `plans/plan.md` covering architecture, tech choices, phased build, and open questions.
- `.gitignore` for Python tooling and local agent state.
- This changelog.
- `CLAUDE.md` with project guidance, including how to maintain this changelog.

### Changed
- Plan revised to a monorepo (`apps/api`, `apps/web`, `packages/core`) with a React + Vite + TypeScript frontend and a FastAPI backend; the web UI (file manager, chat sidebar, table browser) is now in scope from day one rather than deferred.
- Agent loop switched from a hand-rolled tool-use loop to LangChain + LangGraph (`langchain-anthropic`).
- Database target narrowed to PostgreSQL only (no SQLite path).
- Ingestion scope clarified: one file at a time, but the agent may decompose it into multiple normalized tables with foreign keys.
- Phased build restructured so each phase ships an end-to-end vertical slice (backend + matching UI) instead of leaving the UI for the final phase.

[Unreleased]: https://github.com/adityaviki/structai/commits/main
