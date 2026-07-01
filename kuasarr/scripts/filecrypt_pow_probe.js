// filecrypt PoW — click-and-let-page-solve via flaresolverr-next executeJs.
//
// MECHANIC (reverse-engineered from rix1337/sponsors-helper `_POW_SOLVE_JS`):
// We do NOT brute-force the SHA-1 nonce, do NOT read pow_x/pow_data, and do
// NOT POST a token ourselves. Instead we drive filecrypt's OWN PoW UI:
//   1. Intercept the form's native submit (filecrypt would navigate away and
//      the executeJs context would lose the page).
//   2. Synthesize a cubic-Bézier pointer/mouse glide onto the PoW box, then a
//      full pointerover/down/up + click sequence — so filecrypt's own s.js
//      records a human-like motion vector and the click reads as a gesture.
//   3. filecrypt's OWN m.js/s.js + SHA-1 worker run in the page MAIN WORLD with
//      the real (headed-Xvfb) Chrome fingerprint, compute the clean PoW token,
//      and fill the hidden form inputs (pow_id/pow_nonce/pow_data/pow_x/...).
//   4. Poll for data-state="done" AND a populated pow_data hidden input.
//   5. Re-submit the form via fetch() with credentials:'include' — the POST
//      happens INSIDE the browser, so cf_clearance + TLS + fingerprint stay
//      consistent. We capture the unlocked-page HTML from the fetch response.
//   6. Return {status, code, url, haspow, html}. haspow=true means filecrypt
//      re-shows the PoW → caller retries (up to 3×).
//
// This is browser automation (synthetic input events triggering filecrypt's own
// legitimate PoW flow), NOT detection-evasion — no window.chrome / navigator /
// matchMedia properties are touched.
//
// PROMISE-RETURN CONVENTION (Versuch 7): flaresolverr-next wraps this snippet as
// `(() => { <script> })()` and runs it via CDP Runtime.evaluate with
// awaitPromise=true. Ending with `return new Promise(...)` makes the outer arrow
// return the promise so executeJsResult is non-empty.

return new Promise(function (resolve) {
    var out_diag = {
        // Cheap fingerprint diagnostics — settles the Code-605 question on the
        // first run. If hasChromeRuntime is false here, filecrypt's own m.js
        // would ALSO see it and reject — meaning the FS-next browser itself is
        // the problem (needs headed mode / different browser), not this snippet.
        hasChrome: typeof window.chrome === 'object',
        hasChromeRuntime: !!(window.chrome && window.chrome.runtime),
        hasChromeWebstore: !!(window.chrome && window.chrome.webstore),
        pointer: (window.matchMedia && window.matchMedia('(pointer: fine)').matches) ? 'fine' : 'none',
        hover: (window.matchMedia && window.matchMedia('(hover: hover)').matches) ? 'hover' : 'none',
        url: location.href
    };

    var el = document.getElementById('pow-captcha');
    if (!el) { resolve(JSON.stringify({ status: 'no-pow', diag: out_diag })); return; }

    var box = el.querySelector('.pow-captcha__box') || el;
    var form = el.closest('form');

    // (1) Intercept the form's native submit. filecrypt's click handler would
    // submit+navigate, destroying the executeJs page context. We clobber the
    // submit entry points and preventDefault on capture so OUR fetch() below is
    // the only thing that actually POSTs.
    if (form) {
        form.addEventListener('submit', function (e) {
            e.preventDefault(); e.stopImmediatePropagation();
        }, true);
        form.requestSubmit = function () {};
        form.submit = function () {};
    }

    try { box.scrollIntoView({ block: 'center' }); } catch (e) {}
    var rect = box.getBoundingClientRect();
    var tx = rect.left + rect.width / 2, ty = rect.top + rect.height / 2;

    var rnd = function (a, b) { return a + Math.random() * (b - a); };
    // Busy-wait via performance.now() — setTimeout can't tick reliably inside a
    // synchronous CDP Runtime.evaluate event loop.
    var spin = function (ms) { var t = performance.now(); while (performance.now() - t < ms) {} };

    var px = null, py = null;
    var fire = function (type, x, y, extra) {
        var Ctor = type.indexOf('pointer') === 0 ? PointerEvent : MouseEvent;
        var init = Object.assign({
            bubbles: true, cancelable: true, composed: true, view: window,
            clientX: x, clientY: y, screenX: x, screenY: y + 80,
            button: 0,
            buttons: type.indexOf('move') >= 0 ? 0 : 1
        }, extra || {});
        if (Ctor === PointerEvent) {
            init.pointerId = 1; init.pointerType = 'mouse'; init.isPrimary = true;
        }
        var target;
        try { target = document.elementFromPoint(x, y); } catch (e) {}
        (target || box).dispatchEvent(new Ctor(type, init));
    };

    // (2) Cubic-Bézier glide with two control points + per-step jitter +
    // velocity-aware dwell (slower at start/end) + ease-in-out timing.
    var cubic = function (p0, p1, p2, p3, t) {
        var u = 1 - t;
        return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3;
    };
    var glide = function (x0, y0, x1, y1, steps, jit) {
        var c1x = x0 + (x1 - x0) * rnd(0.2, 0.4) + rnd(-40, 40);
        var c1y = y0 + (y1 - y0) * rnd(0.2, 0.4) + rnd(-40, 40);
        var c2x = x0 + (x1 - x0) * rnd(0.6, 0.8) + rnd(-30, 30);
        var c2y = y0 + (y1 - y0) * rnd(0.6, 0.8) + rnd(-30, 30);
        if (px == null) { px = x0; py = y0; }
        for (var i = 1; i <= steps; i++) {
            var t = i / steps;
            var te = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;   // ease-in-out
            var x = cubic(x0, c1x, c2x, x1, te) + rnd(-jit, jit);
            var y = cubic(y0, c1y, c2y, y1, te) + rnd(-jit, jit);
            fire('pointermove', x, y, { movementX: x - px, movementY: y - py });
            fire('mousemove', x, y, { movementX: x - px, movementY: y - py });
            px = x; py = y;
            var speed = Math.abs(0.5 - t) * 2;          // slower toward the ends
            spin(rnd(6, 12) + speed * rnd(8, 20));
        }
    };

    // (2a) Wobbly approach from off-box, (2b) precise landing on the box center.
    var sx = tx + rnd(-180, -120), sy = ty + rnd(-150, -90);
    var ovx = tx + rnd(8, 22) * (Math.random() < 0.5 ? -1 : 1);
    var ovy = ty + rnd(6, 16) * (Math.random() < 0.5 ? -1 : 1);
    glide(sx, sy, ovx, ovy, 20 + Math.floor(rnd(0, 8)), 2.2);
    spin(rnd(20, 50));
    glide(ovx, ovy, tx, ty, 6 + Math.floor(rnd(0, 5)), 1.0);
    spin(rnd(50, 90));

    // (3) Full click sequence — triggers filecrypt's own PoW worker.
    fire('pointerover', tx, ty); fire('pointerenter', tx, ty);
    fire('mouseover', tx, ty);
    fire('pointerdown', tx, ty); fire('mousedown', tx, ty);
    spin(rnd(60, 140));
    fire('pointerup', tx, ty); fire('mouseup', tx, ty);
    try { box.click(); } catch (e) {}

    // (4) Poll for data-state="done" AND populated pow_data, max 6s.
    var start = Date.now();
    var DEADLINE_MS = 6000;
    var iv = setInterval(function () {
        var f = {};
        el.querySelectorAll('input[type=hidden]').forEach(function (i) { f[i.name] = i.value; });
        var st = el.getAttribute('data-state');
        var ready = (st === 'done' && f.pow_data);
        if (!ready && Date.now() - start <= DEADLINE_MS) { return; }
        clearInterval(iv);
        if (!ready) { resolve(JSON.stringify({ status: 'timeout', state: st, diag: out_diag })); return; }

        // (5) Re-submit the form via fetch() — POST runs in the browser so
        // cf_clearance + TLS stay consistent. We capture the unlocked HTML.
        if (!form) { resolve(JSON.stringify({ status: 'no-form', diag: out_diag })); return; }
        var body = new URLSearchParams();
        new FormData(form).forEach(function (v, k) { body.append(k, v); });
        fetch(form.getAttribute('action') || location.href, {
            method: 'POST', body: body,
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            credentials: 'include'
        }).then(function (r) {
            return r.text().then(function (txt) { return { code: r.status, url: r.url, text: txt }; });
        }).then(function (o) {
            // (6) haspow=true → filecrypt re-shows the PoW → caller retries.
            resolve(JSON.stringify({
                status: 'ok',
                code: o.code,
                url: o.url,
                haspow: o.text.indexOf('pow-captcha') >= 0,
                html: o.text,
                diag: out_diag
            }));
        }).catch(function (e) {
            resolve(JSON.stringify({ status: 'error', error: String(e), diag: out_diag }));
        });
    }, 80);
});
