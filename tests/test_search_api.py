# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork from https://github.com/rix1337/Quasarr)

"""Vertragstests fuer die Such-API (``/api/search`` und ``/api/search/download``).

Beide Routen hatten eine Antwortform, die kein Client lesen konnte:

* ``/api/search`` lieferte ``{"results": [...]}`` ohne ``data``-Huelle, waehrend
  die WebUI ueber ``fetchApi`` auf ``response.data`` zugreift - die Seite
  zeigte dauerhaft "No Results Found" und meldete keinen Fehler.
* ``/api/search/download`` erwartete ``items[]``, bekam vom Client aber nur
  ``result_id`` - jeder Download-Klick endete in HTTP 400.
"""

from base64 import urlsafe_b64encode

import pytest
from bottle import HTTPError

from kuasarr.api import search as search_api


class _FakeApp:
    """Collects whatever setup_search_routes registers."""

    def __init__(self):
        self.routes = {}

    def get(self, path):
        def decorator(fn):
            self.routes[path] = fn
            return fn
        return decorator

    post = get


class _FakeRequest:
    """Minimaler Ersatz fuer ``bottle.request`` - nur ``json`` wird gelesen."""

    def __init__(self, payload):
        self.json = payload


def _make_link(title, url, mirror, size_mb, password="", imdb_id="tt1234567"):
    """Baut einen Download-Link in der Form, die die Scraper erzeugen.

    Achtung: die Groesse im *Link-Payload* ist in MB, die ``details["size"]``
    der Treffer dagegen in Bytes (so liefern es die Scraper, z. B. dd.py).
    """
    raw = f"{title}|{url}|{mirror}|{size_mb}|{password}|{imdb_id}".encode("utf-8")
    payload = urlsafe_b64encode(raw).decode("utf-8")
    return f"http://kuasarr.local/download/?payload={payload}"


def _raw_result(title, hostname, size_bytes=1500 * 1024 * 1024, mirror="mirror.example",
                date="Wed, 15 Oct 2025 10:00:00 +0000", password="geheim", payload_size_mb=None):
    """Ein Treffer in der Rohform, wie ``get_search_results`` ihn liefert."""
    source = "https://example.org/"
    if payload_size_mb is None:
        payload_size_mb = int(size_bytes / (1024 * 1024)) if size_bytes else 0
    link = _make_link(title, source, mirror, payload_size_mb, password)
    return {
        "details": {
            "title": title,
            "hostname": hostname,
            "link": link,
            "mirror": mirror,
            "size": size_bytes,
            "date": date,
            "source": source,
        },
        "type": "protected",
    }


@pytest.fixture
def routes(monkeypatch):
    """Registriert die Such-Routen auf einer gefaelschten App."""
    app = _FakeApp()
    search_api.setup_search_routes(app)
    return app.routes


@pytest.fixture
def scraper(monkeypatch):
    """Faengt ``get_search_results`` ab und protokolliert die Aufrufargumente."""
    captured = {"calls": [], "results": []}

    def _fake_get_search_results(shared_state, request_from, search_phrase="", mirror=None, **kwargs):
        captured["calls"].append({
            "request_from": request_from,
            "search_phrase": search_phrase,
            "mirror": mirror,
            "kwargs": kwargs,
        })
        return list(captured["results"])

    monkeypatch.setattr(search_api, "get_search_results", _fake_get_search_results)
    return captured


@pytest.fixture
def downloader(monkeypatch):
    """Faengt ``download`` ab und protokolliert, welches Paket wirklich entsteht."""
    captured = {"calls": [], "result": {"package_id": "pkg-1", "success": True}}

    def _fake_download(shared_state, request_from, title, url, mirror, size_mb, password,
                       imdb_id=None):
        captured["calls"].append({
            "request_from": request_from,
            "title": title,
            "url": url,
            "mirror": mirror,
            "size_mb": size_mb,
            "password": password,
            "imdb_id": imdb_id,
        })
        return dict(captured["result"])

    monkeypatch.setattr(search_api, "download", _fake_download)
    return captured


def _call(route, monkeypatch, payload):
    monkeypatch.setattr(search_api, "request", _FakeRequest(payload))
    return route()


def _shared_state_without_captcha(monkeypatch):
    """``shared_state`` liefert einen leeren protected-Store - kein CAPTCHA."""
    class _ProtectedDb:
        def retrieve(self, package_id):
            return None

        def retrieve_all_titles(self):
            return []

    class _SharedState:
        def get_db(self, name):
            return _ProtectedDb()

    monkeypatch.setattr(search_api, "shared_state", _SharedState())


# ---------------------------------------------------------------------------
# Issue #93 - Antwortform von /api/search
# ---------------------------------------------------------------------------


def test_search_response_wraps_results_in_data(routes, monkeypatch, scraper):
    """``response.data`` muss die Trefferliste sein - ohne geht die Seite leer."""
    scraper["results"] = [_raw_result("Some.Release.S01", "example.org")]
    payload = _call(routes["/api/search"], monkeypatch, {"query": "release"})

    assert isinstance(payload["data"], list)
    assert len(payload["data"]) == 1
    assert "results" not in payload, "das alte Feld 'results' ist zurueckgekehrt"
    assert payload["data"][0]["title"] == "Some.Release.S01"


def test_filters_sit_next_to_data_and_not_inside_it(routes, monkeypatch, scraper):
    """``filters`` gehoert neben ``data``, nicht hinein - sonst filtert nichts."""
    scraper["results"] = [
        _raw_result("Release.A", "alpha.example", date="Wed, 15 Oct 2025 10:00:00 +0000"),
        _raw_result("Release.B", "beta.example", date="Fri, 17 Oct 2025 10:00:00 +0000"),
    ]
    payload = _call(routes["/api/search"], monkeypatch, {"query": "release"})

    assert payload["filters"]["hostnames"] == ["ALPHA.EXAMPLE", "BETA.EXAMPLE"]
    assert payload["filters"]["mirrors"] == ["mirror.example"]
    assert payload["filters"]["date"]["min"] == "2025-10-15"
    assert payload["filters"]["date"]["max"] == "2025-10-17"
    assert "filters" not in payload["data"][0]


def test_every_result_carries_a_non_empty_id(routes, monkeypatch, scraper):
    """Ohne ``id`` ist der React-Key ``undefined`` und der Download ein No-Op."""
    scraper["results"] = [_raw_result("Release.A", "alpha.example")]
    payload = _call(routes["/api/search"], monkeypatch, {"query": "release"})

    result_id = payload["data"][0]["id"]
    assert result_id, "die ID darf nicht leer sein"
    assert isinstance(result_id, str)


def test_result_id_is_stable_across_searches(routes, monkeypatch, scraper):
    """Gleicher Treffer -> gleiche ID, sonst remountet React die Zeile jedes Mal."""
    scraper["results"] = [_raw_result("Release.A", "alpha.example")]
    first = _call(routes["/api/search"], monkeypatch, {"query": "release"})["data"][0]["id"]

    scraper["results"] = [_raw_result("Release.A", "alpha.example")]
    second = _call(routes["/api/search"], monkeypatch, {"query": "release"})["data"][0]["id"]

    assert first == second


def test_two_different_results_get_two_different_ids(routes, monkeypatch, scraper):
    scraper["results"] = [
        _raw_result("Release.A", "alpha.example"),
        _raw_result("Release.B", "alpha.example"),
    ]
    payload = _call(routes["/api/search"], monkeypatch, {"query": "release"})

    ids = [entry["id"] for entry in payload["data"]]
    assert len(set(ids)) == 2, f"IDs sind nicht eindeutig: {ids}"


def test_no_field_is_none_where_the_type_demands_a_number_or_string(routes, monkeypatch, scraper):
    """formatBytes(result.size) und result.age.localeCompare(...) duerfen nicht crashen."""
    scraper["results"] = [_raw_result("Release.A", "alpha.example")]
    payload = _call(routes["/api/search"], monkeypatch, {"query": "release"})
    result = payload["data"][0]

    assert isinstance(result["size"], int)
    assert isinstance(result["grabs"], int)
    assert isinstance(result["age"], str) and result["age"]
    for field in ("title", "id", "hoster", "hostname", "category", "url", "link", "source"):
        assert isinstance(result[field], str), f"{field} ist kein String: {result[field]!r}"

    # Was Search.tsx sortiert, muss rechnen koennen - kein None wuerde NaN liefern.
    assert result["size"] - 0 == result["size"]
    assert result["grabs"] - 0 == result["grabs"]
    assert sorted([result["age"], result["age"]]) == [result["age"]] * 2


def test_size_is_bytes_so_formatbytes_gets_a_number(routes, monkeypatch, scraper):
    """``formatBytes`` erwartet Bytes; der Scraper liefert sie bereits so."""
    scraper["results"] = [_raw_result("Release.A", "alpha.example", size_bytes=1500 * 1024 * 1024)]
    result = _call(routes["/api/search"], monkeypatch, {"query": "release"})["data"][0]

    assert result["size"] == 1500 * 1024 * 1024
    assert result["size_bytes"] == result["size"]


def test_result_without_size_or_date_still_has_typed_fields(routes, monkeypatch, scraper):
    """Auch ein Treffer ohne Groesse/Datum darf keine ``None`` in typisierte Felder legen."""
    raw = _raw_result("Release.A", "alpha.example", size_bytes=None, payload_size_mb=0)
    raw["details"]["date"] = None
    raw["details"]["mirror"] = None
    scraper["results"] = [raw]

    result = _call(routes["/api/search"], monkeypatch, {"query": "release"})["data"][0]

    assert result["size"] == 0
    assert isinstance(result["grabs"], int)
    assert result["age"] == "Unbekannt"
    assert result["size_formatted"] == "Unbekannt"


def test_seeders_and_leechers_are_absent_so_the_ui_hides_them(routes, monkeypatch, scraper):
    """Die WebUI blendet sie nur bei ``undefined`` aus - ``null`` wuerde als Text erscheinen."""
    scraper["results"] = [_raw_result("Release.A", "alpha.example")]
    result = _call(routes["/api/search"], monkeypatch, {"query": "release"})["data"][0]

    assert "seeders" not in result
    assert "leechers" not in result


def test_rich_fields_survive_the_rename(routes, monkeypatch, scraper):
    """Die Anzeige braucht Mirror, Quelle, IMDb-ID und Passwort weiterhin."""
    scraper["results"] = [_raw_result("Release.A", "alpha.example")]
    result = _call(routes["/api/search"], monkeypatch, {"query": "release"})["data"][0]

    assert result["mirror"] == "mirror.example"
    assert result["source"] == "https://example.org/"
    assert result["imdb_id"] == "tt1234567"
    assert result["password"] == "geheim"
    assert result["size_formatted"] == "1.5 GB"
    assert result["date"]["iso"] == "2025-10-15"
    assert result["date"]["label"] == "15.10.2025 10:00"


# ---------------------------------------------------------------------------
# Anfragefelder - nichts darf stillschweigend verworfen werden
# ---------------------------------------------------------------------------


def test_limit_actually_narrows_the_result_list(routes, monkeypatch, scraper):
    scraper["results"] = [_raw_result(f"Release.{i}", "alpha.example") for i in range(5)]
    payload = _call(routes["/api/search"], monkeypatch, {"query": "release", "limit": 2})

    assert len(payload["data"]) == 2
    assert payload["meta"] == {"total": 5, "offset": 0, "limit": 2, "returned": 2}
    assert "unsupported" not in payload


def test_offset_walks_through_the_result_list(routes, monkeypatch, scraper):
    scraper["results"] = [_raw_result(f"Release.{i}", "alpha.example") for i in range(5)]
    payload = _call(routes["/api/search"], monkeypatch, {"query": "release", "offset": 3, "limit": 2})

    assert [entry["title"] for entry in payload["data"]] == ["Release.3", "Release.4"]
    assert payload["meta"]["offset"] == 3


def test_min_and_max_size_narrow_the_result_list(routes, monkeypatch, scraper):
    scraper["results"] = [
        _raw_result("Klein", "alpha.example", size_bytes=100 * 1024 * 1024),
        _raw_result("Mittel", "alpha.example", size_bytes=2048 * 1024 * 1024),
        _raw_result("Gross", "alpha.example", size_bytes=8192 * 1024 * 1024),
    ]
    payload = _call(routes["/api/search"], monkeypatch, {
        "query": "release",
        "min_size": 1024 * 1024 * 1024,          # 1 GB
        "max_size": 4096 * 1024 * 1024,         # 4 GB
    })

    assert [entry["title"] for entry in payload["data"]] == ["Mittel"]
    assert "unsupported" not in payload


def test_sort_by_size_and_sort_order(routes, monkeypatch, scraper):
    scraper["results"] = [
        _raw_result("A", "alpha.example", size_bytes=300 * 1024 * 1024),
        _raw_result("B", "alpha.example", size_bytes=100 * 1024 * 1024),
        _raw_result("C", "alpha.example", size_bytes=200 * 1024 * 1024),
    ]

    aufsteigend = _call(routes["/api/search"], monkeypatch, {"query": "r", "sort_by": "size"})["data"]
    assert [entry["title"] for entry in aufsteigend] == ["B", "C", "A"]

    absteigend = _call(routes["/api/search"], monkeypatch,
                       {"query": "r", "sort_by": "size", "sort_order": "desc"})["data"]
    assert [entry["title"] for entry in absteigend] == ["A", "C", "B"]


def test_sort_by_age_uses_the_iso_date(routes, monkeypatch, scraper):
    scraper["results"] = [
        _raw_result("Alt", "alpha.example", date="Mon, 13 Oct 2025 10:00:00 +0000"),
        _raw_result("Neu", "alpha.example", date="Fri, 17 Oct 2025 10:00:00 +0000"),
    ]
    payload = _call(routes["/api/search"], monkeypatch, {"query": "r", "sort_by": "age"})

    assert [entry["title"] for entry in payload["data"]] == ["Alt", "Neu"]


def test_category_is_reported_as_unsupported_instead_of_being_dropped(routes, monkeypatch, scraper):
    """Der Scraper kann nicht nach Kategorie suchen - das muss der Client erfahren."""
    scraper["results"] = [_raw_result("Release.A", "alpha.example")]
    payload = _call(routes["/api/search"], monkeypatch,
                    {"query": "release", "category": "movies"})

    reported = {entry["field"]: entry["reason"] for entry in payload["unsupported"]}
    assert "category" in reported, "category wird stillschweigend verworfen"
    assert "get_search_results" in reported["category"]

    # Die Kategorie darf die Liste nicht verhehlen: alle Treffer bleiben sichtbar.
    assert len(payload["data"]) == 1
    assert payload["data"][0]["category"] == "movies"


def test_sort_by_grabs_is_reported_as_unsupported(routes, monkeypatch, scraper):
    """DDL-Portale liefern keine Grab-Zaehlung - Sortieren danach waere eine Attrappe."""
    scraper["results"] = [_raw_result("Release.A", "alpha.example")]
    payload = _call(routes["/api/search"], monkeypatch, {"query": "release", "sort_by": "grabs"})

    reported = {entry["field"]: entry["reason"] for entry in payload["unsupported"]}
    assert "sort_by" in reported
    assert "Grab" in reported["sort_by"]


def test_unsupported_fields_are_flagged_per_request_only(routes, monkeypatch, scraper):
    """Ohne Filterfelder darf kein ``unsupported`` im Response stehen."""
    scraper["results"] = [_raw_result("Release.A", "alpha.example")]
    payload = _call(routes["/api/search"], monkeypatch, {"query": "release"})

    assert "unsupported" not in payload


def test_unknown_request_fields_are_reported(routes, monkeypatch, scraper):
    scraper["results"] = []
    payload = _call(routes["/api/search"], monkeypatch, {"query": "release", "seeders": "5"})

    reported = {entry["field"] for entry in payload["unsupported"]}
    assert "seeders" in reported


def test_mirror_is_forwarded_to_the_scraper(routes, monkeypatch, scraper):
    _call(routes["/api/search"], monkeypatch, {"query": "release", "mirror": "mirror.example"})

    assert scraper["calls"][0]["mirror"] == "mirror.example"


def test_empty_query_is_a_bad_request(routes, monkeypatch, scraper):
    with pytest.raises(HTTPError) as excinfo:
        _call(routes["/api/search"], monkeypatch, {"query": "   "})

    assert excinfo.value.status_code == 400


# ---------------------------------------------------------------------------
# Issue #94 - POST /api/search/download
# ---------------------------------------------------------------------------


@pytest.fixture
def searched(routes, monkeypatch, scraper, downloader):
    """Fuehrt eine Suche aus und liefert die gefaelschte Route plus die Trefferliste."""
    _shared_state_without_captcha(monkeypatch)
    scraper["results"] = [
        _raw_result("Release.A", "alpha.example", mirror="mirror-a.example"),
        _raw_result("Release.B", "beta.example", mirror="mirror-b.example"),
    ]
    payload = _call(routes["/api/search"], monkeypatch, {"query": "release"})
    return routes["/api/search/download"], payload["data"]


def test_download_with_result_id_creates_the_right_package(searched, monkeypatch):
    """Der Client schickt nur ``result_id`` - genau das Paket muss entstehen."""
    route, results = searched

    payload = _call(route, monkeypatch, {"result_id": results[1]["id"]})

    assert set(payload) == {"data"}
    data = payload["data"]
    assert data["total"] == 1
    assert data["succeeded"] == 1
    assert data["failed"] == 0
    assert data["results"][0]["title"] == "Release.B"
    assert data["results"][0]["package_id"] == "pkg-1"
    assert data["results"][0]["success"] is True
    assert data["results"][0]["captcha_required"] is False


def test_download_with_result_id_reaches_the_correct_target(searched, monkeypatch, downloader):
    """Der Beweis, dass wirklich der angeklickte Treffer dispatcht wurde."""
    route, results = searched

    _call(route, monkeypatch, {"result_id": results[1]["id"]})

    assert len(downloader["calls"]) == 1
    call = downloader["calls"][0]
    assert call["title"] == "Release.B"
    assert call["mirror"] == "mirror-b.example"
    assert call["password"] == "geheim"
    assert call["imdb_id"] == "tt1234567"


def test_download_accepts_the_legacy_items_list(searched, monkeypatch, downloader):
    """Die Langform muss weiterhin funktionieren - sonst brechen bestehende Aufrufer."""
    route, results = searched

    payload = _call(route, monkeypatch, {"items": [{"link": results[0]["link"], "title": "Release.A"}]})

    assert payload["data"]["total"] == 1
    assert payload["data"]["succeeded"] == 1
    assert downloader["calls"][0]["title"] == "Release.A"


def test_download_summarises_a_mixed_batch(searched, monkeypatch, downloader):
    """Ein Paket scheitert, das andere startet - die Gesamtsicht muss beides zeigen."""
    route, results = searched
    calls = {"n": 0}

    def _flaky(shared_state, request_from, title, url, mirror, size_mb, password, imdb_id=None):
        calls["n"] += 1
        return {"package_id": None, "success": calls["n"] == 2}

    monkeypatch.setattr(search_api, "download", _flaky)

    payload = _call(route, monkeypatch, {
        "result_id": results[0]["id"],
        "items": [{"link": results[1]["link"], "title": "Release.B"}],
    })

    data = payload["data"]
    assert data["total"] == 2
    assert data["succeeded"] == 1
    assert data["failed"] == 1
    assert {entry["success"] for entry in data["results"]} == {True, False}


def test_unknown_result_id_is_a_404_not_a_silent_no_op(searched, monkeypatch, downloader):
    """Ein toter Klick darf kein HTTP 200 mit ``success: false`` sein."""
    route, _ = searched

    with pytest.raises(HTTPError) as excinfo:
        _call(route, monkeypatch, {"result_id": "gibtesnicht"})

    assert excinfo.value.status_code == 404
    assert "gibtesnicht" in str(excinfo.value.body)
    assert downloader["calls"] == []


def test_download_without_any_selection_is_a_bad_request(searched, monkeypatch):
    route, _ = searched

    with pytest.raises(HTTPError) as excinfo:
        _call(route, monkeypatch, {})

    assert excinfo.value.status_code == 400


def test_download_reports_captcha_requirement(routes, monkeypatch, scraper, downloader):
    """Ein Paket im protected-Store wartet auf eine CAPTCHA-Loesung."""
    class _ProtectedDb:
        def retrieve(self, package_id):
            return {"title": "pending"}

    class _SharedState:
        def get_db(self, name):
            return _ProtectedDb()

    monkeypatch.setattr(search_api, "shared_state", _SharedState())
    scraper["results"] = [_raw_result("Release.A", "alpha.example")]
    results = _call(routes["/api/search"], monkeypatch, {"query": "release"})["data"]

    payload = _call(routes["/api/search/download"], monkeypatch, {"result_id": results[0]["id"]})

    assert payload["data"]["results"][0]["captcha_required"] is True


def test_package_name_and_password_override_the_search_result(searched, monkeypatch, downloader):
    """``package_name``/``password`` duerfen den Titel und das Passwort ueberschreiben."""
    route, results = searched

    _call(route, monkeypatch, {
        "result_id": results[0]["id"],
        "package_name": "Eigener Titel",
        "password": "anderes-passwort",
    })

    assert downloader["calls"][0]["title"] == "Eigener Titel"
    assert downloader["calls"][0]["password"] == "anderes-passwort"


def test_category_id_is_reported_as_unsupported(searched, monkeypatch):
    """``download()`` kennt keine Kategorie - das wird gemeldet, nicht verworfen."""
    route, results = searched

    payload = _call(route, monkeypatch, {"result_id": results[0]["id"], "category_id": "movies"})

    reported = {entry["field"] for entry in payload["data"]["unsupported"]}
    assert reported == {"category_id"}