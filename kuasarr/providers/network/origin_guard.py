# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""Pin a requests session to the origin of the container it talks to.

Every link crypter posts secrets - the container password, the captcha answer,
and on keeplinks the form's hidden ``myhiddenpwd`` field. ``requests`` follows
302 redirects by default and carries the request body along, so a hostile
container can answer with a redirect to an internal host and receive all of
it. This module closes that off for every crypter, not just the ones that
happened to be written with the guard in mind.
"""

from typing import Optional
from urllib.parse import urljoin, urlparse

import requests

# requests' own default. Wrapping ``send`` bypasses its ``max_redirects``
# handling, so the bound has to be reapplied by hand.
_DEFAULT_MAX_REDIRECTS = 30


def origin_of(url: str) -> Optional[tuple]:
    """Normalize a URL to (scheme, host, port) for origin comparison.

    Host alone is not an origin: ``http://container:9999`` is a different
    origin than ``https://container`` and may well be an internal service
    on the same machine. Comparing the triple keeps those apart.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    if not scheme or not host:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        port = {"http": 80, "https": 443}.get(scheme)
    return (scheme, host, port)


def same_origin_guard_for(session: requests.Session, base_url: str) -> requests.Session:
    """Pin a session to the container origin, redirects included.

    Checking only the initial URL is not enough: with
    ``allow_redirects=True`` a container can answer 302 pointing at an
    internal host and ``requests`` follows it, carrying along whatever the
    session sends. ``requests`` has no redirect hook, so ``send`` is wrapped
    and every hop is checked before it is followed.

    The hop count is bounded here because wrapping ``send`` bypasses
    ``requests``' own ``max_redirects`` handling - an open redirect chain
    on a hostile container would otherwise spin forever.
    """
    origin = origin_of(base_url)
    if origin is None:
        return session

    max_hops = session.max_redirects or _DEFAULT_MAX_REDIRECTS
    original_send = session.send

    def send(request, **kwargs):
        allow_redirects = kwargs.pop("allow_redirects", True)
        response = original_send(request, allow_redirects=False, **kwargs)

        history = []
        while allow_redirects and response.is_redirect:
            if len(history) >= max_hops:
                raise requests.TooManyRedirects(
                    f"Exceeded {max_hops} redirects on the container origin")
            target = urljoin(response.url, response.headers.get("Location", ""))
            target_origin = origin_of(target)
            if target_origin != origin:
                raise requests.TooManyRedirects(
                    f"Refusing to follow redirect off the container origin: {target_origin}")
            history.append(response)
            next_request = requests.Request(
                "GET", target, headers=response.request.headers).prepare()
            response = original_send(next_request, allow_redirects=False, **kwargs)

        if history:
            response.history = history
        return response

    session.send = send
    return session