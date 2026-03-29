# Contributing

## Commit Messages

Use short, imperative subject lines. Examples:

- `Fix Windows build issue`
- `Add 2Captcha retry backoff`
- `chore: upgrade dependencies`

Key rules:

- Keep subjects scannable but descriptive enough to summarize the actual change
- Avoid underselling large multi-file changes with narrowly-focused subjects
- For multi-area commits, use a shared theme with a brief body if needed
- Prefix maintenance-only work with `chore:` while still describing the work
- Keep feature or bug-fix commits focused on one concern

## Pull Requests

Pull requests should:

- Describe user-visible changes
- Highlight configuration or hostname impacts
- Separate functional work from unrelated cleanup
- Include proof of behavior (screenshots, logs, or reproduction steps) for UI or integration changes

## Change Discipline

- Do not change more code than necessary
- Refactors must be proposed and explicitly requested — not performed opportunistically
- Keep commit deltas low; avoid creating refactor overhead like rewriting unrelated tests
- Unit tests should change only when intended behavior changed, or when an existing test is incorrect

## Coordination

For large features or architectural changes, open an issue or reach out on Matrix at [@kuasarr-support:envs.net](https://matrix.to/#/@kuasarr-support:envs.net) before starting work, to avoid duplicate effort.
