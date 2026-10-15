# -*- coding: utf-8 -*-
"""Tests for the same-origin guard on container-HTML derived URLs.

Container markup is not ours: a release page can carry an absolute
`src`/`action` pointing at an internal host. Every server-side fetch
built from that markup has to stay on the container's origin.
"""

import pytest

from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher

BASE = "https://www.keeplinks.org/p16/6ace7168bf656"

PAGE = "https://www.example-hoster.net/download/abc123.html"

REAL_FORM = """
<html><body>
<form id="content-protector-access-form" method="post" action="/download/abc123.html">
  <input type="hidden" name="captcha_id" value="cp_9f3a">
  <input type="hidden" name="myhiddenpwd" value="deadbeef">
  <img src="/cp/captcha_9f3a.png" alt="captcha">
  <input type="text" name="captcha_answer">
  <input type="submit" value="Continue">
</form>
</body></html>
"""

FORGED_FORM = """
<html><body>
<form id="content-protector-access-form" method="post"
      action="http://169.254.169.254/latest/">
  <input type="hidden" name="captcha_id" value="cp_9f3a">
  <input type="hidden" name="myhiddenpwd" value="deadbeef">
  <img src="http://127.0.0.1:8080/evil.png">
  <input type="text" name="captcha_answer">
</form>
</body></html>
"""


class TestSameOriginAssetUrl:
    """The helper must reject anything leaving the container origin."""

    @pytest.mark.parametrize("hostile", [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:8080/",
        "http://localhost/admin",
        "http://[::1]/",
        "http://10.0.0.1/",
        "http://192.168.0.1/",
        "http://172.16.0.5/",
        "http://169.254.1.1/",
        "http://evil.example/steal",
        "//evil.example/steal",
        "file:///etc/passwd",
        "gopher://attacker/",
        "javascript:alert(1)",
    ])
    def test_rejects_foreign_targets(self, hostile):
        """Absolute, protocol-relative and non-HTTP targets are refused."""
        assert DBCDispatcher._same_origin_asset_url(BASE, hostile) is None

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_rejects_blank(self, blank):
        """A blank src must not resolve to the container page itself."""
        assert DBCDispatcher._same_origin_asset_url(BASE, blank) is None

    def test_rejects_missing_base(self):
        """Without a parseable base host nothing can be trusted."""
        assert DBCDispatcher._same_origin_asset_url("not-a-url", "/rel.png") is None

    @pytest.mark.parametrize("asset,expected", [
        ("https://www.keeplinks.org/coolcaptcha/captcha.php",
         "https://www.keeplinks.org/coolcaptcha/captcha.php"),
        ("/coolcaptcha/captcha.php",
         "https://www.keeplinks.org/coolcaptcha/captcha.php"),
        ("captcha.php", "https://www.keeplinks.org/p16/captcha.php"),
        ("//www.keeplinks.org/x.png", "https://www.keeplinks.org/x.png"),
        ("https://www.keeplinks.org:443/x.png",
         "https://www.keeplinks.org:443/x.png"),
        ("  captcha.php?x=1  ", "https://www.keeplinks.org/p16/captcha.php?x=1"),
    ])
    def test_allows_same_origin(self, asset, expected):
        """Relative paths resolve, absolute same-host URLs pass through."""
        assert DBCDispatcher._same_origin_asset_url(BASE, asset) == expected

    def test_host_comparison_is_case_insensitive(self):
        """DNS is case-insensitive; only cross-host must be refused."""
        assert DBCDispatcher._same_origin_asset_url(
            BASE, "https://WWW.KEeplinks.ORG/x.png"
        ) == "https://WWW.KEeplinks.ORG/x.png"
        assert DBCDispatcher._same_origin_asset_url(
            BASE, "https://WWW.KEeplinks.ORG.evil.com/x.png"
        ) is None


class TestOriginOf:
    """An origin is scheme + host + port, not just the host."""

    def test_default_ports_are_filled_in(self):
        """An omitted port means the scheme default, not "any port"."""
        assert DBCDispatcher._origin_of("https://host/x") == ("https", "host", 443)
        assert DBCDispatcher._origin_of("http://host/x") == ("http", "host", 80)

    @pytest.mark.parametrize("url", ["", "not-a-url", "/relative", "//host/x"])
    def test_rejects_unusable_urls(self, url):
        """Without scheme and host there is no origin to compare against."""
        assert DBCDispatcher._origin_of(url) is None

    @pytest.mark.parametrize("same_host_different_origin", [
        "https://www.keeplinks.org:8443/x.png",   # other port
        "http://www.keeplinks.org/p16/x.png",      # other scheme
        "https://www.keeplinks.org:80/x.png",      # other port
    ])
    def test_same_host_other_port_or_scheme_is_rejected(self, same_host_different_origin):
        """A different port or scheme is a different origin.

        ``https://host`` and ``https://host:8443`` may well be an internal
        service on the same machine - host equality is not enough.
        """
        assert DBCDispatcher._same_origin_asset_url(BASE, same_host_different_origin) is None

    def test_explicit_default_port_equals_implicit(self):
        """:443 and the implicit default are the same origin."""
        assert DBCDispatcher._origin_of("https://host:443/x") == DBCDispatcher._origin_of(
            "https://host/x")


class TestHeFormSnapshot:
    """he.to snapshots must not carry a foreign action or image URL."""

    def test_real_form_is_accepted(self):
        """A genuine Content Protector form still resolves correctly."""
        snapshot = DBCDispatcher._he_form_snapshot_from_html(REAL_FORM, PAGE)
        assert snapshot is not None
        assert snapshot["action"] == "https://www.example-hoster.net/download/abc123.html"
        assert snapshot["image_url"] == "https://www.example-hoster.net/cp/captcha_9f3a.png"
        assert snapshot["captcha_id"] == "cp_9f3a"
        assert ("myhiddenpwd", "deadbeef") in snapshot["fields"]

    def test_action_posting_to_the_page_itself_is_allowed(self):
        """An action resolving to the page URL is normal, not suspicious."""
        form = REAL_FORM.replace('action="/download/abc123.html"',
                                 'action="/download/abc123.html"')
        snapshot = DBCDispatcher._he_form_snapshot_from_html(form, PAGE)
        assert snapshot is not None

    def test_forged_form_is_rejected(self):
        """A form pointing at link-local metadata is refused outright."""
        assert DBCDispatcher._he_form_snapshot_from_html(FORGED_FORM, PAGE) is None

    def test_foreign_image_is_dropped_but_snapshot_survives(self):
        """A bad image URL is cleared; the rest of the form stays usable."""
        form = REAL_FORM.replace(
            'src="/cp/captcha_9f3a.png"', 'src="http://127.0.0.1:8080/evil.png"')
        snapshot = DBCDispatcher._he_form_snapshot_from_html(form, PAGE)
        assert snapshot is not None
        assert snapshot["image_url"] == ""

    def test_flaresolverr_snapshot_image_is_revalidated_downstream(self):
        """A snapshot built in the browser can carry an unchecked image_url.

        The HTML path validates the URL while parsing; the FlareSolverr path
        cannot, so _he_solve_with_snapshot re-checks it before fetching.
        """
        browser_snapshot = {
            'action': 'https://www.example-hoster.net/download/abc123.html',
            'fields': [('captcha_id', 'cp_9f3a'), ('captcha_answer', '')],
            'captcha_id': 'cp_9f3a',
            'image': b'',
            'image_url': 'http://169.254.169.254/latest/meta-data/',
        }
        # The guard the solver applies to that value:
        assert DBCDispatcher._same_origin_asset_url(
            PAGE, browser_snapshot['image_url']) is None
        # A legitimate one still passes:
        browser_snapshot['image_url'] = 'https://www.example-hoster.net/cp/captcha_9f3a.png'
        assert DBCDispatcher._same_origin_asset_url(
            PAGE, browser_snapshot['image_url']) is not None