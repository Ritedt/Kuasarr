# -*- coding: utf-8 -*-
"""Tests fuer die Paket-Aktionen der WebUI-API (Issue #92).

Der React-Client (``kuasarr/webui/src/lib/api.ts``) sendet durchgaengig
``package_ids`` als **Liste**. Das Backend lasst dagegen nur das skalare
``package_id`` und fiel bei jedem unbekannten Feld in den globalen
Zweig - ein Tippfehler im Feldnamen stoppte damit die *gesamte* Queue.

Die Tests fangen genau das ab: ``device.downloadcontroller.set_pause`` darf
nicht aufgerufen werden, wenn der Client einzelne Pakete adressiert.
"""

import io
import json
from unittest.mock import MagicMock

import pytest

from kuasarr.api import packages as packages_api


class _FakeApp:
    """Collects whatever setup_packages_routes registers."""

    def __init__(self):
        self.routes = {}

    def get(self, path):
        def decorator(fn):
            self.routes[path] = fn
            return fn
        return decorator

    post = get


class _FakeRequest:
    """Minimaler Ersatz fuer bottle.request - nur ``body.read()`` wird gebraucht."""

    def __init__(self, raw: bytes = b"{}"):
        self.body = io.BytesIO(raw)


class _FakeResponse:
    """Minimaler Ersatz fuer bottle.response."""

    def __init__(self):
        self.status = 200
        self.content_type = "text/html"


class _FakeDB:
    def __init__(self, name, deleted):
        self.name = name
        self.deleted = deleted

    def delete(self, package_id):
        self.deleted.append((self.name, package_id))


class _FakeSharedState:
    def __init__(self, device, deleted):
        self.values = {"device": device}
        self._deleted = deleted

    def get_device(self):
        return self.values.get("device")

    def get_db(self, name):
        return _FakeDB(name, self._deleted)


def _queue_item(nzo_id="pkg-1", package_type="downloader", uuid="uuid-1"):
    return {"nzo_id": nzo_id, "type": package_type, "uuid": uuid}


@pytest.fixture
def api(monkeypatch):
    """Registriert die Routen und legt Request/Response/Device bereit."""
    app = _FakeApp()
    packages_api.setup_packages_routes(app)

    device = MagicMock()
    device.downloads.query_links.return_value = [
        {"uuid": "link-1", "packageUUID": "uuid-1"},
    ]
    deleted_db = []

    fake_response = _FakeResponse()
    monkeypatch.setattr(packages_api, "response", fake_response)
    monkeypatch.setattr(
        packages_api, "shared_state", _FakeSharedState(device, deleted_db)
    )
    monkeypatch.setattr(
        packages_api,
        "get_packages",
        lambda *_args, **_kwargs: {
            "queue": [_queue_item()],
            "history": [],
        },
    )
    monkeypatch.setattr(packages_api, "delete_package", MagicMock(return_value=True))

    class _Ctx:
        def __init__(self):
            self.device = device
            self.response = fake_response
            self.deleted_db = deleted_db
            self.delete_package = packages_api.delete_package

        def post(self, path, payload):
            """Ruft eine POST-Route mit einem JSON-Body auf."""
            raw = json.dumps(payload).encode("utf-8") if payload is not None else b""
            return self.post_raw(path, raw)

        def post_raw(self, path, raw):
            monkeypatch.setattr(packages_api, "request", _FakeRequest(raw))
            self.response.status = 200
            body = app.routes[path]()
            return self.response.status, body

    return _Ctx()


# ---------------------------------------------------------------------------
# pause
# ---------------------------------------------------------------------------


def test_pause_with_package_ids_list_pauses_only_that_package(api):
    """Regressionstest fuer Issue #92: die Liste landet bei set_enabled."""
    status, body = api.post("/api/packages/pause", {"package_ids": ["pkg-1"]})

    assert status == 200
    assert json.loads(body) == {"success": True}
    api.device.downloads.set_enabled.assert_called_once_with(
        package_ids=["pkg-1"], enabled=False
    )
    # Das ist der eigentliche Assert: die ganze Queue darf nicht stehen.
    api.device.downloadcontroller.set_pause.assert_not_called()


def test_pause_with_multiple_package_ids_passes_the_whole_list(api):
    status, _ = api.post("/api/packages/pause", {"package_ids": ["a", "b"]})

    assert status == 200
    api.device.downloads.set_enabled.assert_called_once_with(
        package_ids=["a", "b"], enabled=False
    )
    api.device.downloadcontroller.set_pause.assert_not_called()


def test_pause_still_accepts_the_legacy_scalar_package_id(api):
    """Die Legacy-Inline-JS derselben Datei sendet weiterhin package_id."""
    status, _ = api.post("/api/packages/pause", {"package_id": "pkg-1"})

    assert status == 200
    api.device.downloads.set_enabled.assert_called_once_with(
        package_ids=["pkg-1"], enabled=False
    )
    api.device.downloadcontroller.set_pause.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {},                                  # leeres Objekt
        {"packageId": "pkg-1"},              # Tippfehler
        {"package_ids": []},                 # leere Liste
        {"package_ids": ""},                 # leerer String
        {"package_ids": [""]},               # nur Leerzeichen
        {"package_ids": {"id": "pkg-1"}},    # Objekt statt Liste
        {"global": False},                   # kein Opt-in
        {"global": "true"},                  # Opt-in als String zaehlt nicht
        None,                                # komplett leerer Body
    ],
)
def test_pause_without_recognized_action_is_400_and_never_pauses_globally(api, payload):
    status, body = api.post("/api/packages/pause", payload)

    assert status == 400
    assert api.device.downloadcontroller.set_pause.call_count == 0
    assert api.device.downloads.set_enabled.call_count == 0

    error = json.loads(body)["error"]
    assert error["code"] == "bad_request"
    assert error["message"]


def test_pause_with_invalid_json_is_400(api):
    status, body = api.post_raw("/api/packages/pause", b"{{not json")

    assert status == 400
    assert "not valid JSON" in json.loads(body)["error"]["message"]
    assert api.device.downloadcontroller.set_pause.call_count == 0


def test_global_opt_in_pauses_everything(api):
    """Das ausdrueckliche Opt-in funktioniert weiter."""
    status, _ = api.post("/api/packages/pause", {"global": True})

    assert status == 200
    api.device.downloadcontroller.set_pause.assert_called_once_with(True)
    api.device.downloads.set_enabled.assert_not_called()


def test_pause_reports_jdownloader_errors_as_502(api):
    api.device.downloads.set_enabled.side_effect = RuntimeError("connection reset")

    status, body = api.post("/api/packages/pause", {"package_ids": ["pkg-1"]})

    assert status == 502
    assert json.loads(body)["error"]["code"] == "bad_gateway"


def test_pause_without_device_is_502(api):
    packages_api.shared_state.values = {}

    status, body = api.post("/api/packages/pause", {"package_ids": ["pkg-1"]})

    assert status == 502
    assert "not connected" in json.loads(body)["error"]["message"]


# ---------------------------------------------------------------------------
# resume
# ---------------------------------------------------------------------------


def test_resume_with_package_ids_list_enables_only_those_packages(api):
    status, _ = api.post("/api/packages/resume", {"package_ids": ["pkg-1", "b"]})

    assert status == 200
    api.device.downloads.set_enabled.assert_called_once_with(
        package_ids=["pkg-1", "b"], enabled=True
    )
    api.device.downloadcontroller.set_pause.assert_not_called()


def test_resume_still_accepts_the_legacy_scalar_package_id(api):
    status, _ = api.post("/api/packages/resume", {"package_id": "pkg-1"})

    assert status == 200
    api.device.downloads.set_enabled.assert_called_once_with(
        package_ids=["pkg-1"], enabled=True
    )
    api.device.downloadcontroller.set_pause.assert_not_called()


def test_resume_without_recognized_action_is_400_and_never_resumes_globally(api):
    status, _ = api.post("/api/packages/resume", {"packageId": "pkg-1"})

    assert status == 400
    api.device.downloadcontroller.set_pause.assert_not_called()
    api.device.downloads.set_enabled.assert_not_called()


def test_global_opt_in_resumes_everything(api):
    status, _ = api.post("/api/packages/resume", {"global": True})

    assert status == 200
    api.device.downloadcontroller.set_pause.assert_called_once_with(False)
    api.device.downloads.set_enabled.assert_not_called()


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_without_recognized_id_returns_an_error_status(api):
    """Ohne ID gab es previously HTTP 200 + success:false - die UI meldete Erfolg."""
    status, body = api.post("/api/packages/delete", {})

    assert status == 400
    assert api.delete_package.call_count == 0
    assert "success" not in json.loads(body)
    assert json.loads(body)["error"]["code"] == "bad_request"


def test_delete_is_atomic_when_one_id_is_unknown(api):
    """Ein unbekanntes Paket darf kein halb geloeschter Auftrag werden."""
    status, body = api.post("/api/packages/delete", {"package_ids": ["pkg-1", "weg"]})

    assert status == 404
    assert api.delete_package.call_count == 0
    assert "weg" in json.loads(body)["error"]["message"]


def test_delete_with_package_ids_list_calls_delete_package_per_id(api, monkeypatch):
    monkeypatch.setattr(
        packages_api,
        "get_packages",
        lambda *_args, **_kwargs: {
            "queue": [_queue_item("a"), _queue_item("b", uuid="uuid-2")],
            "history": [],
        },
    )

    status, body = api.post("/api/packages/delete", {"package_ids": ["a", "b"]})

    assert status == 200
    assert json.loads(body) == {"success": True}
    assert [call.args[1] for call in api.delete_package.call_args_list] == ["a", "b"]


def test_delete_still_accepts_the_legacy_scalar_package_id(api):
    status, body = api.post("/api/packages/delete", {"package_id": "pkg-1"})

    assert status == 200
    assert json.loads(body) == {"success": True}
    api.delete_package.assert_called_once_with(packages_api.shared_state, "pkg-1")


def test_delete_of_an_unknown_package_is_404_and_deletes_nothing(api):
    status, body = api.post("/api/packages/delete", {"package_ids": ["weg"]})

    assert status == 404
    assert api.delete_package.call_count == 0
    assert json.loads(body)["error"]["code"] == "not_found"
    assert "weg" in json.loads(body)["error"]["message"]


def test_delete_rejects_a_global_request(api):
    """'Alles loeschen' wird bewusst nicht angeboten."""
    status, body = api.post("/api/packages/delete", {"global": True})

    assert status == 400
    assert api.delete_package.call_count == 0
    assert "not supported" in json.loads(body)["error"]["message"]


def test_delete_rejects_a_non_boolean_delete_files(api):
    status, _ = api.post(
        "/api/packages/delete", {"package_ids": ["pkg-1"], "delete_files": "yes"}
    )

    assert status == 400
    assert api.delete_package.call_count == 0


def test_delete_files_true_goes_through_delete_package_and_removes_the_files(api):
    """delete_package() nutzt REMOVE_LINKS_AND_DELETE_FILES - Datei weg."""
    status, _ = api.post(
        "/api/packages/delete", {"package_ids": ["pkg-1"], "delete_files": True}
    )

    assert status == 200
    api.delete_package.assert_called_once_with(packages_api.shared_state, "pkg-1")
    assert api.device.downloads.cleanup.call_count == 0


def test_delete_files_false_keeps_the_files_via_remove_links_only(api):
    """delete_files: false darf nicht als wirkungslos getarnt werden."""
    status, _ = api.post(
        "/api/packages/delete", {"package_ids": ["pkg-1"], "delete_files": False}
    )

    assert status == 200
    assert api.delete_package.call_count == 0, "haette die Dateien mit geloescht"
    api.device.downloads.cleanup.assert_called_once_with(
        "DELETE_ALL", "REMOVE_LINKS_ONLY", "SELECTED", ["link-1"], ["uuid-1"]
    )
    assert api.device.linkgrabber.cleanup.call_count == 0
    assert ("failed", "pkg-1") in api.deleted_db
    assert ("protected", "pkg-1") in api.deleted_db


def test_delete_files_false_on_a_linkgrabber_package_uses_the_linkgrabber(api, monkeypatch):
    monkeypatch.setattr(
        packages_api,
        "get_packages",
        lambda *_args, **_kwargs: {
            "queue": [_queue_item("pkg-1", package_type="linkgrabber")],
            "history": [],
        },
    )
    api.device.linkgrabber.query_links.return_value = [
        {"uuid": "link-1", "packageUUID": "uuid-1"},
    ]

    status, _ = api.post(
        "/api/packages/delete", {"package_ids": ["pkg-1"], "delete_files": False}
    )

    assert status == 200
    api.device.linkgrabber.cleanup.assert_called_once_with(
        "DELETE_ALL", "REMOVE_LINKS_ONLY", "SELECTED", ["link-1"], ["uuid-1"]
    )
    assert api.device.downloads.cleanup.call_count == 0


def test_delete_files_defaults_to_true_when_absent(api):
    """Der React-Client schickt das Feld immer - aber ein Aufruf ohne es
    darf die Dateien nicht ungefragt behalten."""
    status, _ = api.post("/api/packages/delete", {"package_ids": ["pkg-1"]})

    assert status == 200
    api.delete_package.assert_called_once()


def test_delete_reports_a_jdownloader_refusal_as_502(api):
    api.delete_package.return_value = False

    status, body = api.post("/api/packages/delete", {"package_ids": ["pkg-1"]})

    assert status == 502
    assert json.loads(body)["error"]["code"] == "bad_gateway"