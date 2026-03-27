# Coding Style

## Language

Python 3 — keep compatible with the versions used in the Docker base image.

## Naming Conventions

- `snake_case` for modules, functions, variables, and test methods
- `PascalCase` for classes
- `SCREAMING_SNAKE_CASE` for environment variable names
- `lowercase_with_underscores` for INI config keys
- Match existing naming patterns for source integrations

## Indentation

4 spaces. No tabs.

## Module Responsibility

Keep modules focused on one responsibility. Place shared helpers in the existing `helpers/` packages instead of duplicating logic across files.

## Style Guidelines

- Follow existing Python style in `kuasarr/` — keep consistent with surrounding code
- No enforced linter config is present, but the code follows PEP 8
- Prefer Pythonic idioms (list comprehensions, context managers, f-strings)

## Security

- Sensitive values (passwords, tokens, API keys) must **never** be hardcoded
- Always read credentials from ENV vars or from `kuasarr.ini`
- Validate input at system boundaries (user input, external APIs); trust internal code and framework guarantees

## General Principle

Maintain consistency with the surrounding codebase rather than introducing divergent styling within individual files. When in doubt, follow what the existing code does.
