# -*- coding: utf-8 -*-
"""Regressionstest: keine globale Such-Deadline.

Hintergrund
-----------
PR67 (P2-A) fuehrte eine globale Deadline von 8s ein, die den ThreadPool per
``as_completed(futures, timeout=deadline)`` abbricht. Sie war kuerzer als das,
was eine einzelne Suchfunktion braucht, und hat dadurch funktionierende
Suchen als leer gemeldet:

* Jeder Scraper loest zuerst den IMDb-Titel auf. Ist imdb.com durch die
  AWS WAF blockiert (HTTP 202), wartet der FlareSolverr-Pfad
  ``IMDB_WAF_SETTLE_SECONDS`` (8s) - exakt das Deadline-Budget.
* Danach braucht der Scraper selbst noch ``SEARCH_TIMEOUT_SECONDS`` (15s)
  fuer seinen eigenen HTTP-Aufruf.

8s < 8s + 15s heisst: der Pool brach ab, bevor der erste Scraper antworten
konnte. Im Log:

    10:01:43 Starting 1 search functions for IMDb-ID "tt0182576"...
    10:01:43 IMDb request blocked for tt0182576 (status 202), retrying via FlareSolverr
    10:01:51 Search deadline (8s) reached - returning 0 partial results

Zum Vergleich derselbe Aufruf ohne Deadline (main):

    10:16:38 IMDb request blocked for tt0149460 (status 202), retrying via FlareSolverr
    10:16:50 Providing 7 releases ... Time taken: 12.30 seconds

Der Test haelt fest, dass es keine globale Deadline gibt: langsame Quellen
tragen ihre eigenen Timeouts und beenden sich selbst.
"""

import inspect

from kuasarr import search
from kuasarr import constants


def test_no_global_search_deadline_constant():
    """Es gibt keine globale Such-Deadline mehr."""
    assert not hasattr(constants, "SEARCH_DEADLINE_SECONDS"), (
        "SEARCH_DEADLINE_SECONDS ist zurueck - sie war kuerzer als "
        "IMDB_WAF_SETTLE_SECONDS (8s) plus SEARCH_TIMEOUT_SECONDS (15s) und hat "
        "jede Suche bei blockiertem imdb.com auf 0 Ergebnisse gebracht."
    )


def test_no_search_deadline_helper():
    """Der slow-mode-Helper fuer die Deadline existiert nicht mehr."""
    assert not hasattr(constants, "get_search_deadline"), (
        "get_search_deadline() gehoert zu SEARCH_DEADLINE_SECONDS und wird "
        "mit entfernt."
    )


def test_search_loop_does_not_cut_the_pool_short():
    """Der Suchloop darf den ThreadPool nicht per Timeout abbrechen."""
    source = inspect.getsource(search)
    assert "timeout=deadline" not in source, (
        "as_completed(..., timeout=deadline) bricht den Pool ab, waehrend die "
        "langsamen aber funktionierenden Quellen noch laufen."
    )
    assert "FuturesTimeoutError" not in source, (
        "Der Deadline-Abbruchpfad ist ueberfluessig, wenn es keine Deadline "
        "mehr gibt."
    )


def test_search_loop_still_bounds_workers():
    """Der Worker-Pool bleibt begrenzt - nur die Zeitkappung entfaellt.

    SEARCH_MAX_WORKERS ist eine echte Begrenzung (bounded pool) und nicht
    dasselbe wie ein Abbruch nach Zeit. Sie bleibt erhalten.
    """
    source = inspect.getsource(search)
    assert "SEARCH_MAX_WORKERS" in source, (
        "Der Pool soll weiterhin begrenzt sein - nur die zeitliche Kappung "
        "der Suche entfaellt."
    )
    assert "max_workers=" in source