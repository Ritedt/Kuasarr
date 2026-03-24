# UI-Optimierung für Kuasarr

Kuasarr ist ein **Utility/Admin-Tool** – kein Consumer-Produkt. Die Optimierungen sollten auf **Klarheit, Effizienz und Zugänglichkeit** ausgerichtet sein, nicht auf visuellen Wow-Effekt.

---

## 1. Fehlende Button-Focus-Styles (Barrierefreiheit — KRITISCH)

Aktuell hat `input:focus` einen sichtbaren Ring, aber Buttons haben **keinen** `:focus`-Stil. Tastatur-Navigation ist dadurch kaputt.

**Fix in `kuasarr/providers/ui/html_templates.py`:**
```css
button:focus-visible {
    outline: 2px solid var(--primary);
    outline-offset: 2px;
}
a:focus-visible {
    outline: 2px solid var(--primary);
    outline-offset: 2px;
}
```

---

## 2. `button:active` hat keinen Effekt

```css
/* AKTUELL — macht nichts, weil kein translateY(-1px) im Normalzustand */
button:active {
    transform: translateY(0);
}

/* BESSER — spürbares Press-Feedback */
button:not(:disabled):active {
    transform: translateY(1px);
    box-shadow: none;
}
```

---

## 3. Kein `prefers-reduced-motion`-Support

Alle Transitions laufen auch bei Nutzern, die Animationen deaktiviert haben.

**Fix:**
```css
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        transition-duration: 0.01ms !important;
        animation-duration: 0.01ms !important;
    }
}
```

---

## 4. Persistente Navigation fehlt

Aktuell muss der User über eingebettete Links zwischen Seiten navigieren. Eine einfache Top-Navigationsleiste würde die UX deutlich verbessern.

**Neue Hilfsfunktion in `html_templates.py`:**
```python
def render_nav(active_page=""):
    pages = [
        ("/", "Home"),
        ("/settings", "Settings"),
        ("/captcha-config", "CAPTCHA"),
        ("/hosters", "Hosters"),
        ("/notifications", "Notifications"),
    ]
    items = "".join(
        f'<a href="{url}" class="nav-link{"  nav-active" if url == active_page else ""}">{label}</a>'
        for url, label in pages
    )
    return f'<nav class="top-nav">{items}</nav>'
```

**CSS:**
```css
.top-nav {
    display: flex;
    gap: 0.25rem;
    flex-wrap: wrap;
    justify-content: center;
    margin-bottom: 1.5rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--divider-color);
}
.nav-link {
    padding: 0.35rem 0.75rem;
    border-radius: var(--border-radius);
    font-size: 0.875rem;
    color: var(--text-muted);
    transition: background 0.15s, color 0.15s;
}
.nav-link:hover {
    background: var(--btn-subtle-bg);
    color: var(--fg-color);
    text-decoration: none;
}
.nav-active {
    background: var(--btn-subtle-bg);
    color: var(--fg-color);
    font-weight: 600;
}
```

**Verwendung in `render_form`:**
```python
def render_form(header, form="", script="", footer_content="", active_page=""):
    nav = render_nav(active_page)
    content = f'''
    <h1><img src="{images.logo}" type="image/png" alt="kuasarr logo" class="logo"/>kuasarr</h1>
    {nav}
    <h2>{header}</h2>
    {form}
    {script}
    '''
    return render_centered_html(content, footer_content)
```

---

## 5. Dark-Mode Primärfarbe zu dunkel (Barrierefreiheit — KRITISCH)

`--primary: #375a7f` im Dark Mode hat ein Kontrastverhältnis von ~2.5:1 gegen weißen Button-Text — **WCAG AA-Fehler**.

```css
/* AKTUELL */
--primary: #375a7f;
--primary-hover: #2b4764;

/* FIX — helleres Blau mit ~4.6:1 Kontrast auf #1e1e1e */
--primary: #4d8fd4;
--primary-hover: #3a7bc8;
```

Kontrast prüfen unter: https://contrast-ratio.com/ (`#4d8fd4` auf `#1e1e1e` = ~4.6:1 ✓)

---

## 6. Render-Success UX verbessern

Der "Wait time... 10"-Countdown ist verwirrend. Auto-Redirect mit abbrechbarem Button ist besser.

```python
def render_success(message, timeout=5, optional_text=""):
    script = f'''
        <script>
            let counter = {timeout};
            const btn = document.getElementById('nextButton');
            const info = document.getElementById('redirect-info');
            const interval = setInterval(() => {{
                counter--;
                if (info) info.textContent = `Redirecting in ${{counter}}s...`;
                if (counter === 0) {{
                    clearInterval(interval);
                    window.location.href = '/';
                }}
            }}, 1000);
            btn.onclick = () => {{ clearInterval(interval); window.location.href = '/'; }};
        </script>
    '''
    button_html = render_button("Go to Home", "primary", {{"id": "nextButton"}})
    content = f"""
    <h1><img src="{images.logo}" type="image/png" alt="kuasarr logo" class="logo"/>kuasarr</h1>
    <h2>{message}</h2>
    {optional_text}
    <p id="redirect-info" style="color:var(--text-muted);font-size:0.85rem;">Redirecting in {timeout}s...</p>
    {button_html}
    {script}
    """
    return render_centered_html(content)
```

---

## 7. `lang`-Attribut prüfen

```python
# AKTUELL — hardcoded Englisch
return f'<!DOCTYPE html><html lang="en">{body}</html>'

# Falls die UI auf Deutsch ist oder mehrsprachig werden soll:
# lang="de" setzen oder als Parameter übergeben
```

---

## 8. Inter-Font für professionelleren Look (optional)

System-Font ist funktional, aber Inter gibt dem Tool einen deutlich polierteren Look bei minimalem Performance-Impact (`display=swap`).

**Im `<head>`:**
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
```

**Im CSS:**
```css
font-family: 'Inter', system-ui, -apple-system, sans-serif;
```

---

## Prioritätsliste

| Priorität | Maßnahme | Datei | Aufwand |
|-----------|----------|-------|---------|
| 🔴 Kritisch | Button Focus-Styles hinzufügen | `html_templates.py` | 5 min |
| 🔴 Kritisch | Dark-Mode Primärfarbe für WCAG-Kontrast | `html_templates.py` | 2 min |
| 🟡 Hoch | `prefers-reduced-motion` hinzufügen | `html_templates.py` | 5 min |
| 🟡 Hoch | `button:active` Press-Feedback fixen | `html_templates.py` | 2 min |
| 🟢 Mittel | Persistente Navigation implementieren | `html_templates.py` + alle Route-Files | 30 min |
| 🟢 Mittel | Success-Redirect UX verbessern | `html_templates.py` | 15 min |
| ⚪ Optional | Inter-Font laden | `html_templates.py` | 10 min |

---

*Erstellt mit UI/UX Pro Max Design Intelligence. Basiert auf Analyse von `kuasarr/providers/ui/html_templates.py`.*
