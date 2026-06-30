// filecrypt PoW diagnostic probe — runs inside flaresolverr-next's Chrome via
// executeJs. Reports every step's outcome (DOM presence, fetch status, global
// surface, R()/S.collect() result) as JSON. Loaded as `new Function(exec)` is
// the canonical way to inject a script body into the page from executeJs — we
// keep that one call site and use eval-via-script-element injection for m.js
// and s.js themselves.

(async function() {
    const out = {steps: [], errors: []};
    const log = (step, payload) => out.steps.push({step, ...payload});

    function rec(exc) {
        return {ok: false, error: String(exc && (exc.message || exc) || 'unknown'),
                stack: (exc && exc.stack ? String(exc.stack).slice(0, 400) : '')};
    }

    try {
        // ── Step 1: surface-level diagnostics ─────────────────────────────
        log('surface', {
            ok: true,
            url: location.href,
            title: document.title,
            dcl: document.readyState,
            hasEval: typeof eval === 'function',
            cdf: !!window.crypto && !!window.crypto.subtle,
            hasGlobalThis: typeof globalThis === 'object',
        });

        // ── Step 2: pow-captcha div presence ──────────────────────────────
        let powDiv = null;
        try {
            powDiv = document.querySelector('#pow-captcha, .pow-captcha, [class*="pow-captcha"]');
        } catch (e) { log('pow-div-find', rec(e)); }
        log('pow-div', {ok: !!powDiv,
                        tag: powDiv ? powDiv.tagName : null,
                        id: powDiv ? powDiv.id : null,
                        cls: powDiv ? powDiv.className : null,
                        challenge: powDiv ? powDiv.getAttribute('data-challenge') : null,
                        difficulty: powDiv ? powDiv.getAttribute('data-difficulty') : null,
                        scriptSrcs: Array.from(document.querySelectorAll('script[src]')).map(s => s.src).filter(s => /\/js\/(m|s)\.js/.test(s))});

        if (!powDiv) {
            out.ok = false;
            out.reason = 'no pow-captcha div in DOM';
            return JSON.stringify(out);
        }

        const challenge = powDiv.getAttribute('data-challenge');
        const difficulty = parseInt(powDiv.getAttribute('data-difficulty'), 10) || 0;
        const powIdInput = powDiv.querySelector('input[name="pow_id"]');
        const pow_id = powIdInput ? powIdInput.value : '';

        out.pow_id = pow_id;
        out.challenge = challenge;
        out.difficulty = difficulty;

        // ── Step 3: m.js / s.js fetch via same-origin credentials ─────────
        async function fetchScript(path) {
            try {
                const r = await fetch(path, {credentials: 'same-origin', cache: 'no-cache'});
                const txt = await r.text();
                return {ok: r.ok, status: r.status, len: txt.length,
                        head: txt.slice(0, 80)};
            } catch (e) { return rec(e); }
        }

        const mRes = await fetchScript('/js/m.js?v=0f174e67');
        log('fetch-m', mRes);
        if (!mRes.ok) { out.ok = false; out.reason = 'm.js fetch failed'; return JSON.stringify(out); }

        const sRes = await fetchScript('/js/s.js?v=82c3f32b');
        log('fetch-s', sRes);
        if (!sRes.ok) { out.ok = false; out.reason = 's.js fetch failed'; return JSON.stringify(out); }

        // ── Step 4: load globals via direct script-element injection ────
        // filecrypt itself loads m.js/s.js as <script src=…> in the live page.
        // The same-origin Page-context grants it the page's globals. We mimic
        // that by appending a <script> with the cleaned source as text — this
        // runs in the page's VM context, not the executeJs isolated world.
        function cleanForGlobal(src) {
            return src
                .replace(/\bexport\s+const\s+/g, 'globalThis.')
                .replace(/\bexport\s+default\s+/g, 'globalThis.__default = ')
                .replace(/\bexport\s*\{[^}]+\}\s*;?/g, '');
        }

        function injectScript(scriptText, label) {
            try {
                const s = document.createElement('script');
                s.textContent = cleanForGlobal(scriptText);
                document.head.appendChild(s);
                s.remove();
                return {ok: true, path: 'script-append', label,
                        hasR: typeof globalThis.R, hasS: typeof globalThis.S};
            } catch (e) { return rec(e); }
        }

        async function loadGlobal(path) {
            const r = await fetch(path, {credentials: 'same-origin', cache: 'no-cache'});
            const txt = await r.text();
            return injectScript(txt, path);
        }

        const mLoad = await loadGlobal('/js/m.js?v=0f174e67');
        log('load-m', mLoad);
        const sLoad = await loadGlobal('/js/s.js?v=82c3f32b');
        log('load-s', sLoad);

        // ── Step 5: poll for R and S.collect to appear ─────────────────────
        let pollTries = 0;
        while ((typeof globalThis.R !== 'function' ||
                typeof globalThis.S !== 'object' ||
                typeof globalThis.S.collect !== 'function') && pollTries < 30) {
            await new Promise(r => setTimeout(r, 100));
            pollTries++;
        }
        log('wait-globals', {
            ok: typeof globalThis.R === 'function' && typeof globalThis.S === 'object' && typeof globalThis.S.collect === 'function',
            tries: pollTries,
            R: typeof globalThis.R,
            S: typeof globalThis.S,
            S_collect: globalThis.S && typeof globalThis.S.collect,
            S_start: globalThis.S && typeof globalThis.S.start,
            S_recordClick: globalThis.S && typeof globalThis.S.recordClick,
        });

        const powBox = powDiv.querySelector('.pow-captcha__box, [class*="pow-captcha__box"]');

        let pow_x = '';
        let pow_data = '';
        try {
            if (typeof globalThis.S === 'object' && typeof globalThis.S.start === 'function') {
                try { globalThis.S.start(); } catch (e) { log('S-start', rec(e)); }
            }
            if (powBox && globalThis.S && typeof globalThis.S.recordClick === 'function') {
                try {
                    globalThis.S.recordClick({
                        clientX: 200, clientY: 220,
                        timeStamp: performance.now(),
                        target: powBox, bubbles: true
                    });
                    log('S-recordClick', {ok: true});
                } catch (e) { log('S-recordClick', rec(e)); }
            }
            await new Promise(r => setTimeout(r, 250));

            if (typeof globalThis.R === 'function') {
                try { pow_x = String(await globalThis.R()); } catch (e) { log('R-call', rec(e)); }
            }
            if (globalThis.S && typeof globalThis.S.collect === 'function') {
                try { pow_data = String(await globalThis.S.collect()); } catch (e) { log('S-collect', rec(e)); }
            }
        } catch (e) { log('eval-block', rec(e)); }

        out.pow_x_len = pow_x.length;
        out.pow_data_len = pow_data.length;
        out.pow_x_head = pow_x.slice(0, 30);
        out.pow_data_head = pow_data.slice(0, 30);
        out.ok = !!(pow_x && pow_data);
    } catch (e) {
        out.ok = false;
        out.errors.push({where: 'top', msg: String(e && (e.message || e) || 'unknown'),
                         stack: (e && e.stack ? String(e.stack).slice(0, 500) : '')});
    }
    return JSON.stringify(out);
})();
