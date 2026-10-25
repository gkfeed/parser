Use `make lint` for linting.
Use `make test` for testing.
Use Conventional Commits for commit messages.
Do not make unit tests that hard depends on implementation. Do not overuse monkeypatches
Do not change tests they must remain integration
Fewer levels of nesting are always better; prefer flat control flow.
After any code change, invoke `$parser-verification` from `.agents/skills/parser-verification/SKILL.md` before marking the task complete.
