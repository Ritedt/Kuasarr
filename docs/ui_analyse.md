Ui analyse

---
  Kuasarr UI-Analyse

  Das Fundament ist solide

  - CSS Custom Properties mit Light/Dark-Mode ✓
  - Responsive Layout (max-width: 600px) ✓
  - PWA-Unterstützung ✓
  - Modales System ✓
  - Semantische Statusfarben ✓

  ---
  Probleme nach Priorität

  🔴 KRITISCH — Emojis als strukturelle Icons

  Fundstellen: Dashboard (api/__init__.py), CAPTCHA-UI (ui_components.py)

  📖 Setup Instructions   🔧 API Configuration   ☁️ JDownloader
  ⚡ Quick Actions        🌍 Update Hostnames     🚫 Manage Hosters
  📊 Statistics          🔑 Captcha Settings     ⚙️ Global Settings
  📋 Copy                👁️ Show                 🔄 Regenerate

  Emojis sind plattformabhängig, nicht themebar, keine Accessibility-Labels und sehen auf verschiedenen Systemen
  unterschiedlich aus. Laut UI/UX-Regel #4 müssen SVG-Icons (z.B. Lucide) verwendet werden.

  ---
  🔴 KRITISCH — Fehlende focus-visible-Styles

  button:focus ist nicht definiert. Nur input:focus hat einen Ring. Buttons sind per Tastatur nicht erkennbar
  navigierbar — WCAG-Verstoß.

  ---
  🟡 HOCH — Dark-Mode Primary-Farbe zu dunkel

  /* Dark Mode */
  --primary: #375a7f;  /* auf --card-bg: #1e1e1e */

  #375a7f mit weißem Text auf #1e1e1e Hintergrund: Der Button-Hintergrund #375a7f hat mit weißem Text (#ffffff) ein
  Kontrast-Verhältnis von ~4.8:1 — gerade noch AA. Aber die muted-blaue Farbe wirkt visuell schwach. Empfehlung: #4a7ab5
   für bessere Sichtbarkeit.

  ---
  🟡 HOCH — Textarea Dark-Mode-Bruch

  In ui_components.py:90:
  style="... border: 1px solid #ced4da; ..."
  Hardcodierter Hex-Wert statt var(--card-border). Im Dark Mode erscheint ein heller grauer Rand auf dunklem Hintergrund
   — sieht gebrochen aus.

  ---
  🟡 HOCH — prefers-reduced-motion fehlt vollständig

  Alle Transitions (0.2s ease, transform, opacity) ignorieren @media (prefers-reduced-motion: reduce).
  Accessibility-Pflicht.

  ---
  🟡 HOCH — button:active ist eine No-Op

  button:active {
      transform: translateY(0);  /* kein Effekt, da kein Hover-translateY definiert */
  }

  Die .action-btn haben translateY(-2px) auf hover, aber das active-Reset ist am globalen button statt an .action-btn.
  Kein physisches Klick-Feedback.

  ---
  🟠 MITTEL — min-height: 100vh auf Mobile

  min-height: 100vh;
  Sollte min-height: 100dvh sein (dynamic viewport height), da 100vh auf iOS/Android die Browser-Chrome-Leiste nicht
  einrechnet und Content abschneiden kann.

  ---
  🟠 MITTEL — autocomplete-Attribute fehlen

  JDownloader-Formular (:213-216):
  <input type="email" id="jd_user" placeholder="your@email.com" ...>
  <input type="password" id="jd_pass" ...>
  Kein autocomplete="email" / autocomplete="current-password". Browser kann nicht sinnvoll autofüllen.

  ---
  🟠 MITTEL — Page-Titel und lang-Attribut

  <title>kuasarr</title>         <!-- sollte "Kuasarr" sein -->
  <html lang="en">               <!-- alle Unterseiten gleicher Titel -->
  Unterseiten sollten differenzierte Titel haben: "Kuasarr – Statistics", "Kuasarr – Captcha Settings" etc.

  ---
  🟠 MITTEL — Inline-Styles überall

  In api/__init__.py gibt es viele style="..." direkt im HTML-String (:212, :216, :219, :223, :229 etc.). Sollte in
  CSS-Klassen verschoben werden, um Wartbarkeit zu verbessern.

  ---
  Zusammenfassung nach Impact

  ┌─────────────────────────────┬───────────┬─────────────┐
  │           Problem           │  Impact   │   Aufwand   │
  ├─────────────────────────────┼───────────┼─────────────┤
  │ Emojis → SVG-Icons ersetzen │ Sehr hoch │ Mittel      │
  ├─────────────────────────────┼───────────┼─────────────┤
  │ focus-visible für Buttons   │ Hoch      │ Gering      │
  ├─────────────────────────────┼───────────┼─────────────┤
  │ Textarea var(--card-border) │ Mittel    │ Sehr gering │
  ├─────────────────────────────┼───────────┼─────────────┤
  │ prefers-reduced-motion      │ Mittel    │ Gering      │
  ├─────────────────────────────┼───────────┼─────────────┤
  │ button:active Fix           │ Gering    │ Sehr gering │
  ├─────────────────────────────┼───────────┼─────────────┤
  │ 100vh → 100dvh              │ Gering    │ Sehr gering │
  ├─────────────────────────────┼───────────┼─────────────┤
  │ autocomplete Attribute      │ Gering    │ Sehr gering │
  ├─────────────────────────────┼───────────┼─────────────┤
  │ Page-Titel differenzieren   │ Gering    │ Gering      │
  └─────────────────────────────┴───────────┴─────────────┘
