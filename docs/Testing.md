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

For black-box testing of a **running container** (Newznab/SABnzbd API, log
interpretation, known pitfalls), see [Container-Test-Playbook.md](Container-Test-Playbook.md).

## Committing Tests

`tests/` is listed in `.gitignore`, so a new test file is invisible to
`git add .`. Add it explicitly:

```bash
git add -f tests/test_<area>.py
```

A test that exists only in the working tree runs locally and in no CI job.

## Testing Bottle Routes

Never test a route by calling `route.callback()` directly. That skips the
API-key guard, the CSRF decorator, the registered error handlers and the
status code, so the test asserts the handler body while the response a client
would actually get goes unexamined — a `200 {"error": ...}` reads as a pass.

Dispatch through the app instead, so the full WSGI stack runs:

```python
app = Bottle()
with patch("kuasarr.api.Bottle", return_value=app), patch("kuasarr.api.Server"):
    get_api(shared_state, lock)

status, headers, body = app(environ, start_response)
```

Two details bite here. `wsgi.errors` must be an `io.StringIO()`, not
`io.BytesIO()`. And `require_csrf_token` reads the module-global
`bottle.request`, so patching a module's own `request` attribute does not
affect it — outside a real dispatch it sees `GET` and the write branch never
runs, which is why such tests pass without ever exercising the guard.
`tests/test_api_contract_core.py` has a working harness for all of this.

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
