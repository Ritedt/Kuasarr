# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""UI components for CAPTCHA pages."""

from urllib.parse import quote

from bottle import request

from kuasarr.providers.ui.html_templates import render_button


def render_bypass_section(url, package_id, title, password, provider_name="FileCrypt", storage_key="hideSetupInstructions", userscript_url="/captcha/kuasarr.user.js"):
    """Render the bypass UI section for CAPTCHA pages."""
    base_url = request.urlparts.scheme + '://' + request.urlparts.netloc
    transfer_url = f"{base_url}/captcha/quick-transfer"

    url_with_quick_transfer_params = (
        f"{url}?"
        f"transfer_url={quote(transfer_url)}&"
        f"pkg_id={quote(package_id)}&"
        f"pkg_title={quote(title)}&"
        f"pkg_pass={quote(password)}"
    )

    submit_button = render_button("Submit", "primary", {"type": "submit"})

    return f'''
    <div style="margin-top: 2.5rem; padding-top: 1.5rem; border-top: 2px solid var(--code-bg); max-width: 400px; margin-left: auto; margin-right: auto;">
        <details id="bypassDetails" style="background: var(--code-bg); border-radius: var(--border-radius); padding: 0.5rem 1rem;">
            <summary id="bypassSummary" style="cursor: pointer; font-weight: 600; padding: 0.5rem 0;">Show CAPTCHA Bypass</summary>

            <!-- Info section explaining the process -->
            <div class="info-box">
                <h3>ℹ️ How This Works:</h3>
                <p style="margin-bottom: 0.5rem; font-size: 0.9rem;">
                    1. Click the button below to open {provider_name} directly
                </p>
                <p style="margin-top: 0; margin-bottom: 0.5rem; font-size: 0.9rem;">
                    2. Solve any CAPTCHAs on their site to reveal the download links
                </p>
                <p style="margin-top: 0; margin-bottom: 0; font-size: 0.9rem;">
                    3. <b>With the userscript installed</b>, links are automatically sent back to Kuasarr!
                </p>
            </div>

            <!-- One-time setup section - visually separated -->
            <div id="setup-instructions" class="setup-box">
                <h3>📦 First Time Setup:</h3>
                <p style="margin-bottom: 0.5rem; font-size: 0.9rem;">
                    <a href="https://www.tampermonkey.net/" target="_blank" rel="noopener noreferrer">1. Install Tampermonkey</a>
                </p>
                <p style="margin-top: 0; margin-bottom: 0.75rem; font-size: 0.9rem;">
                    <a href="{userscript_url}" target="_blank">2. Install the {provider_name} userscript</a>
                </p>
                <p style="margin-top: 0;">
                    <button id="hide-setup-btn" type="button" class="btn-subtle">
                        ✅ Don't show this again
                    </button>
                </p>
            </div>

            <!-- Hidden "show instructions" button -->
            <div id="show-instructions-link" style="display: none; margin-bottom: 1rem;">
                <button id="show-setup-btn" type="button" class="btn-subtle">
                    ℹ️ Show setup instructions
                </button>
            </div>

            <p style="text-align: center;">
                {render_button(f"Open {provider_name} & Get Download Links", "primary", {"onclick": f"window.open('{url_with_quick_transfer_params}', '_self')"})}
            </p>

            <!-- Manual submission - collapsible -->
            <div class="section-divider">
                <details id="manualSubmitDetails">
                    <summary id="manualSubmitSummary" style="cursor: pointer;">Show Manual Submission</summary>
                    <div style="margin-top: 1rem; text-align: left;">
                        <p style="font-size: 0.85rem; margin-bottom: 1rem;">
                            If the userscript doesn't work, you can manually paste the links below:
                        </p>
                        <form id="bypass-form" action="/captcha/bypass-submit" method="post" enctype="multipart/form-data">
                            <input type="hidden" name="package_id" value="{package_id}" />
                            <input type="hidden" name="title" value="{title}" />
                            <input type="hidden" name="password" value="{password}" />

                            <div style="margin-bottom: 1rem;">
                                <strong style="font-size: 0.9rem; display: block; margin-bottom: 0.5rem;">Paste download links (one per line):</strong>
                                <textarea id="links-input" name="links" rows="5" style="width: 100%; padding: 0.6rem; border-radius: var(--border-radius); border: 1px solid #ced4da; background: var(--card-bg); color: var(--fg-color); font-family: monospace; resize: vertical; font-size: 0.9rem;"></textarea>
                            </div>

                            <div style="margin-bottom: 1.5rem;">
                                <strong style="font-size: 0.9rem; display: block; margin-bottom: 0.5rem;">Or upload DLC file:</strong>
                                <input type="file" id="dlc-file" name="dlc_file" accept=".dlc" style="font-size: 0.9rem; padding: 0.2rem 0;" />
                            </div>

                            <div style="text-align: center;">
                                {submit_button}
                            </div>
                        </form>
                    </div>
                </details>
            </div>
        </details>
    </div>
    <script>
        // Handle CAPTCHA Bypass toggle
        const bypassDetails = document.getElementById('bypassDetails');
        const bypassSummary = document.getElementById('bypassSummary');

        if (bypassDetails && bypassSummary) {{
            bypassDetails.addEventListener('toggle', () => {{
                if (bypassDetails.open) {{
                    bypassSummary.textContent = 'Hide CAPTCHA Bypass';
                }} else {{
                    bypassSummary.textContent = 'Show CAPTCHA Bypass';
                }}
            }});
        }}

        // Handle manual submission toggle text
        const manualDetails = document.getElementById('manualSubmitDetails');
        const manualSummary = document.getElementById('manualSubmitSummary');

        if (manualDetails && manualSummary) {{
            manualDetails.addEventListener('toggle', () => {{
                if (manualDetails.open) {{
                    manualSummary.textContent = 'Hide Manual Submission';
                }} else {{
                    manualSummary.textContent = 'Show Manual Submission';
                }}
            }});
        }}

        // Handle setup instructions hide/show
        const hideSetup = localStorage.getItem('{storage_key}');
        const setupBox = document.getElementById('setup-instructions');
        const showLink = document.getElementById('show-instructions-link');

        if (hideSetup === 'true') {{
            setupBox.style.display = 'none';
            showLink.style.display = 'block';
        }}

        // Hide setup instructions
        document.getElementById('hide-setup-btn').addEventListener('click', function() {{
            localStorage.setItem('{storage_key}', 'true');
            setupBox.style.display = 'none';
            showLink.style.display = 'block';
        }});

        // Show setup instructions again
        document.getElementById('show-setup-btn').addEventListener('click', function() {{
            localStorage.removeItem('{storage_key}');
            setupBox.style.display = 'block';
            showLink.style.display = 'none';
        }});
    </script>
    '''
