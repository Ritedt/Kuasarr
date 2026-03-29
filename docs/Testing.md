# Testing

Kuasarr uses the standard library `unittest` framework for automated tests.

## Test Layout

- Put tests in `tests/`
- Name files `test_*.py`
- Name test methods `test_*`
- Prefer focused unit tests with mocks around network calls, JDownloader interactions, and external integrations

## Commands

Run the full test suite:

```bash
python -X utf8 -m unittest discover -s tests
```

The `-X utf8` flag avoids noisy Windows console encoding issues in log output.

## When to Change Tests

Unit tests should change only when:

- The intended behavior in the covered area changed
- The existing test is incorrect

Do not rewrite tests just because nearby code changed shape.

## Mocking

Mock external dependencies at the boundary:

- HTTP requests to FlareSolverr, DDL sites, CAPTCHA services
- My-JDownloader API calls
- File system operations for config/database

Keep tests fast and deterministic by isolating them from real network calls and external services.
