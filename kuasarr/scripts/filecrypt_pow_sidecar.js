#!/usr/bin/env node
// filecrypt PoW sidecar — runs m.js.R() and s.js.S.collect() in a sandboxed
// browser-like environment and emits JSON with the resulting tokens.
//
// Usage:
//   node filecrypt_pow_sidecar.js m.js > m_token.txt
//   node filecrypt_pow_sidecar.js s.js > s_token.txt
//   node filecrypt_pow_sidecar.js m.js s.js > both_tokens.json   # combined

const fs = require('fs');
const vm = require('vm');

function buildSandbox(overrides = {}) {
    const ua = overrides.userAgent || 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';
    const lang = overrides.language || 'en-US';
    const plat = overrides.platform || 'Linux x86_64';
    const fakeNavigator = {
        userAgent: ua,
        platform: plat,
        language: lang,
        languages: [lang, lang.split('-')[0]],
        hardwareConcurrency: 8,
        deviceMemory: 8,
        webdriver: false,
        plugins: [{ name: 'Plugin1' }],
        mimeTypes: []
    };
    const fakeWindow = {
        navigator: fakeNavigator,
        screen: { width: 1920, height: 1080, colorDepth: 24, pixelDepth: 24, availWidth: 1920, availHeight: 1080 },
        innerWidth: 1920, innerHeight: 1080, outerWidth: 1920, outerHeight: 1080,
        document: {
            createElement: tag => {
                if (tag === 'canvas') {
                    return {
                        getContext: () => new Proxy({}, {
                            get: (t, p) => {
                                if (p === 'getImageData') return () => ({ data: new Uint8ClampedArray(64 * 64 * 4), width: 64, height: 64 });
                                if (p === 'fillText' || p === 'measureText' || p === 'fillRect' || p === 'beginPath' || p === 'closePath' || p === 'moveTo' || p === 'lineTo' || p === 'arc' || p === 'stroke' || p === 'fill' || p === 'save' || p === 'restore' || p === 'translate' || p === 'scale' || p === 'rotate' || p === 'transform' || p === 'rect') return () => { };
                                if (p === 'getParameter') return () => 'fake';
                                if (p === 'getExtension') return () => ({});
                                if (p === 'getSupportedExtensions') return () => [];
                                if (p === 'createBuffer' || p === 'bindBuffer' || p === 'bufferData' || p === 'getShaderPrecisionFormat') return () => { };
                                if (p === 'getContextAttributes') return () => ({});
                                if (p === 'getProgramParameter') return () => true;
                                if (p === 'createShader' || p === 'shaderSource' || p === 'compileShader' || p === 'attachShader' || p === 'linkProgram' || p === 'useProgram' || p === 'getShaderParameter' || p === 'getProgramInfoLog' || p === 'getShaderInfoLog') return () => { };
                                return () => { };
                            }
                        }),
                        toDataURL: () => 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
                    };
                }
                return { style: {}, innerHTML: '', addEventListener: () => { }, getContext: () => ({}), toDataURL: () => '' };
            },
            body: { appendChild: () => { } },
            getElementById: () => null,
            getElementsByTagName: () => [],
            addEventListener: () => { },
            documentElement: { style: {} }
        },
        location: { href: 'http://test/', host: 'test', protocol: 'http:' },
        crypto: {
            subtle: {
                digest: async (alg, buf) => {
                    const crypto = require('crypto');
                    return crypto.createHash(alg === 'SHA-1' ? 'sha1' : 'sha256').update(Buffer.from(buf)).digest();
                }
            },
            getRandomValues: arr => { require('crypto').randomFillSync(arr); return arr; }
        },
        setTimeout, clearTimeout, Promise, Date, Math, JSON, Array, Object, RegExp, String, Number, Boolean, Error,
        Int8Array, Uint8Array, Uint8ClampedArray, Int16Array, Uint16Array, Int32Array, Uint32Array,
        Float32Array, Float64Array, ArrayBuffer, DataView, Map, Set, Symbol, Proxy, Reflect,
        TextEncoder, TextDecoder, Buffer,
        btoa: s => Buffer.from(s, 'binary').toString('base64'),
        atob: s => Buffer.from(s, 'base64').toString('binary'),
        WebGLRenderingContext: class { }, WebGL2RenderingContext: class { },
        OffscreenCanvas: class { getContext() { return {}; } },
        AudioContext: class {
            constructor() { this.destination = {}; this.state = 'running'; this.currentTime = 0; this.sampleRate = 44100; this.baseLatency = 0; this.outputLatency = 0; this.listener = { positionX: { value: 0 }, positionY: { value: 0 }, positionZ: { value: 0 } }; }
            createOscillator() { return { connect: () => { }, start: () => { }, stop: () => { }, frequency: { value: 440 }, type: 'sine' }; }
            createAnalyser() { return { connect: () => { }, frequencyBinCount: 1024, getFloatFrequencyData: () => { }, getByteFrequencyData: () => { } }; }
            createDynamicsCompressor() { return { connect: () => { } }; }
            getChannelData() { return new Float32Array(1024); }
            createMediaStreamDestination() { return { stream: { getTracks: () => [] } }; }
            resume() { return Promise.resolve(); }
            close() { return Promise.resolve(); }
        },
        HTMLCanvasElement: class { getContext() { return {}; } },
        Blob: class { constructor() { } },
        URL: { createObjectURL: () => 'blob:fake', revokeObjectURL: () => { } },
        performance: { now: () => Date.now() },
        addEventListener: () => { },
        requestAnimationFrame: cb => setTimeout(cb, 16),
        Intl: { DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: 'Europe/Berlin' }) }) },
        WebAssembly: { instantiate: () => Promise.reject('not supported') }
    };
    const sb = { window: fakeWindow, self: fakeWindow, ...fakeWindow };
    fakeWindow.window = fakeWindow;
    fakeWindow.self = fakeWindow;
    fakeWindow.globalThis = sb;
    sb.globalThis = sb;
    sb.self = fakeWindow;
    sb.window = fakeWindow;
    return sb;
}

function cleanScript(src) {
    // Strip HTML <pre> wrapper if Cloudflare returned an error page.
    const m = src.match(/<pre[^>]*>([\s\S]*?)<\/pre>/);
    if (m) src = m[1].replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
    // Strip ESM exports — the sidecar uses CommonJS globals.
    src = src.replace(/\bexport\s+const\s+/g, 'globalThis.');
    src = src.replace(/\bexport\s+default\s+/g, 'globalThis.__default = ');
    src = src.replace(/\bexport\s*\{[^}]+\}\s*;?/g, '');
    return src;
}

// Invoke the right entry point depending on which file we're given:
//   *m.js → R is an async function         → call R()
//   *s.js → S is an object                 → call S.collect()
async function callExport(sb, basename) {
    if (/m\.js$/.test(basename)) {
        if (typeof sb.R !== 'function') throw new Error(`${basename}: did not export R function`);
        return String(await sb.R());
    }
    if (/s\.js$/.test(basename)) {
        if (!sb.S || typeof sb.S.collect !== 'function') throw new Error(`${basename}: did not export S.collect`);
        return String(await sb.S.collect());
    }
    throw new Error(`Unknown script: ${basename} (expected *m.js or *s.js)`);
}

(async () => {
    const args = process.argv.slice(2);
    if (args.length === 0) {
        console.error('Usage: filecrypt_pow_sidecar.js <m.js|s.js> [<m.js|s.js> ...]');
        process.exit(2);
    }
    // Optional environment overrides (set by Kuasarr):
    //   SIDECAR_USER_AGENT – UA string the sandbox should report (matches the
    //                        one FlareSolverr presented to filecrypt.cc so the
    //                        fingerprint lines up server-side)
    //   SIDECAR_LANGUAGE   – primary language (defaults to en-US)
    //   SIDECAR_PLATFORM   – "Win32" or "Linux x86_64"
    const overrides = {
        userAgent: process.env.SIDECAR_USER_AGENT,
        language: process.env.SIDECAR_LANGUAGE,
        platform: process.env.SIDECAR_PLATFORM,
    };
    try {
        const tokens = {};
        for (const arg of args) {
            const basename = require('path').basename(arg);
            const raw = fs.readFileSync(arg, 'utf-8');
            const js = cleanScript(raw);
            const sb = buildSandbox(overrides);
            vm.createContext(sb);
            vm.runInContext(js, sb, { timeout: 10000 });
            // For s.js, emit a small mouse sequence so the signal sampler
            // has non-empty state when collect() runs (filecrypt's server
            // validates that the signature contains at least one click).
            if (/s\.js$/.test(basename) && sb.S && typeof sb.S.start === 'function') {
                try { sb.S.start(); } catch (_) {}
                for (let i = 0; i < 6; i++) {
                    try {
                        sb.S.recordPointer({
                            clientX: 120 + i * 6,
                            clientY: 220 + (i % 3) * 8,
                            timeStamp: Date.now() + i * 30,
                            pointerType: 'mouse',
                            target: { tagName: 'DIV' },
                        });
                    } catch (_) {}
                }
                try {
                    sb.S.recordClick({
                        clientX: 156, clientY: 232,
                        timeStamp: Date.now() + 200,
                        target: { tagName: 'DIV' },
                    });
                } catch (_) {}
                await new Promise(r => setTimeout(r, 50));
            }
            const token = await callExport(sb, basename);
            if (/m\.js$/.test(basename)) tokens.pow_x = token;
            else if (/s\.js$/.test(basename)) tokens.pow_data = token;
        }
        if (args.length === 1) {
            // Single-file mode: emit just the raw token string (backwards compatible)
            const only = args[0];
            const key = /m\.js$/.test(only) ? 'pow_x' : 'pow_data';
            process.stdout.write(tokens[key]);
        } else {
            console.log(JSON.stringify(tokens));
        }
    } catch (e) {
        console.error('Sidecar error:', e.message);
        process.exit(1);
    }
})();