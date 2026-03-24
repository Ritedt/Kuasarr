# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import json
import re
import html
import time
from typing import Optional

from bottle import request, response

from kuasarr.providers import shared_state
from kuasarr.providers.auth import require_api_key
from kuasarr.providers.ui.html_templates import render_centered_html, render_button, render_nav
from kuasarr.storage.config import Config


def setup_categories_routes(app):
    """Setup routes for category management."""

    @app.get('/categories')
    def categories_page():
        """Render the category management UI."""
        return _render_categories_page()

    @app.get('/api/categories')
    @require_api_key
    def get_categories_api():
        """Get all categories as JSON."""
        response.content_type = 'application/json'
        categories = _get_all_categories()
        return json.dumps({"success": True, "categories": categories})

    @app.get('/api/categories/<category_id>')
    @require_api_key
    def get_category_api(category_id: str):
        """Get a single category by ID."""
        response.content_type = 'application/json'
        category = _get_category(category_id)
        if category:
            return json.dumps({"success": True, "category": category})
        response.status = 404
        return json.dumps({"success": False, "error": "Category not found"})

    @app.post('/api/categories')
    @require_api_key
    def create_category_api():
        """Create a new category."""
        response.content_type = 'application/json'
        try:
            data = request.json or {}
            name = data.get('name', '').strip()
            download_path = data.get('download_path', '').strip()
            file_patterns = data.get('file_patterns', [])

            # Validation
            errors = {}
            if not name:
                errors['name'] = 'Category name is required'
            elif len(name) > 50:
                errors['name'] = 'Category name must be 50 characters or less'
            elif not re.match(r'^[a-zA-Z0-9_\-\s]+$', name):
                errors['name'] = 'Category name can only contain letters, numbers, spaces, hyphens and underscores'

            if not download_path:
                errors['download_path'] = 'Download path is required'
            elif len(download_path) > 500:
                errors['download_path'] = 'Download path must be 500 characters or less'

            # Check for duplicate name
            existing = _get_all_categories()
            for cat in existing:
                if cat['name'].lower() == name.lower():
                    errors['name'] = 'A category with this name already exists'
                    break

            if errors:
                response.status = 400
                return json.dumps({"success": False, "errors": errors})

            # Generate ID from name
            category_id = _generate_category_id(name)

            # Validate file patterns
            validated_patterns = _validate_patterns(file_patterns)

            category = {
                'id': category_id,
                'name': name,
                'download_path': download_path,
                'file_patterns': validated_patterns,
                'created_at': int(time.time()) if 'time' in dir() else 0
            }

            _save_category(category_id, category)
            return json.dumps({"success": True, "category": category})

        except Exception as e:
            response.status = 500
            return json.dumps({"success": False, "error": str(e)})

    @app.post('/api/categories/<category_id>')
    @require_api_key
    def update_category_api(category_id: str):
        """Update an existing category."""
        response.content_type = 'application/json'
        try:
            existing = _get_category(category_id)
            if not existing:
                response.status = 404
                return json.dumps({"success": False, "error": "Category not found"})

            data = request.json or {}
            name = data.get('name', '').strip()
            download_path = data.get('download_path', '').strip()
            file_patterns = data.get('file_patterns', [])

            # Validation
            errors = {}
            if not name:
                errors['name'] = 'Category name is required'
            elif len(name) > 50:
                errors['name'] = 'Category name must be 50 characters or less'
            elif not re.match(r'^[a-zA-Z0-9_\-\s]+$', name):
                errors['name'] = 'Category name can only contain letters, numbers, spaces, hyphens and underscores'

            if not download_path:
                errors['download_path'] = 'Download path is required'
            elif len(download_path) > 500:
                errors['download_path'] = 'Download path must be 500 characters or less'

            # Check for duplicate name (excluding current category)
            all_categories = _get_all_categories()
            for cat in all_categories:
                if cat['id'] != category_id and cat['name'].lower() == name.lower():
                    errors['name'] = 'A category with this name already exists'
                    break

            if errors:
                response.status = 400
                return json.dumps({"success": False, "errors": errors})

            # Validate file patterns
            validated_patterns = _validate_patterns(file_patterns)

            category = {
                'id': category_id,
                'name': name,
                'download_path': download_path,
                'file_patterns': validated_patterns,
                'created_at': existing.get('created_at', 0)
            }

            _save_category(category_id, category)
            return json.dumps({"success": True, "category": category})

        except Exception as e:
            response.status = 500
            return json.dumps({"success": False, "error": str(e)})

    @app.delete('/api/categories/<category_id>')
    @require_api_key
    def delete_category_api(category_id: str):
        """Delete a category."""
        response.content_type = 'application/json'
        try:
            existing = _get_category(category_id)
            if not existing:
                response.status = 404
                return json.dumps({"success": False, "error": "Category not found"})

            _delete_category(category_id)
            return json.dumps({"success": True})

        except Exception as e:
            response.status = 500
            return json.dumps({"success": False, "error": str(e)})


def _generate_category_id(name: str) -> str:
    """Generate a URL-safe category ID from the name."""
    # Replace spaces with underscores, remove special chars
    category_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', name.lower())
    category_id = re.sub(r'_+', '_', category_id)  # Collapse multiple underscores
    category_id = category_id.strip('_')

    # Ensure uniqueness by appending number if needed
    base_id = category_id
    counter = 1
    existing_ids = [c['id'] for c in _get_all_categories()]
    while category_id in existing_ids:
        category_id = f"{base_id}_{counter}"
        counter += 1

    return category_id


def _validate_patterns(patterns) -> list:
    """Validate and clean file patterns."""
    if not patterns:
        return []

    validated = []
    for pattern in patterns:
        if isinstance(pattern, str):
            pattern = pattern.strip()
            if pattern and len(pattern) <= 100:
                # Basic pattern validation - allow glob-style patterns
                if re.match(r'^[a-zA-Z0-9_\-\*\.\?\[\]]+$', pattern):
                    validated.append(pattern)
    return validated


def _get_all_categories() -> list:
    """Get all categories from storage."""
    try:
        db = shared_state.get_db("categories")
        raw_data = db.retrieve_all_titles()
        categories = []
        for key, value in raw_data:
            try:
                category = json.loads(value)
                categories.append(category)
            except json.JSONDecodeError:
                continue
        return sorted(categories, key=lambda x: x.get('name', ''))
    except Exception:
        return []


def _get_category(category_id: str) -> Optional[dict]:
    """Get a single category by ID."""
    try:
        db = shared_state.get_db("categories")
        value = db.retrieve(category_id)
        if value:
            return json.loads(value)
        return None
    except Exception:
        return None


def _save_category(category_id: str, category: dict):
    """Save a category to storage."""
    db = shared_state.get_db("categories")
    db.update_store(category_id, json.dumps(category))


def _delete_category(category_id: str):
    """Delete a category from storage."""
    db = shared_state.get_db("categories")
    db.delete(category_id)


def _render_categories_page():
    """Render the categories management page."""
    nav = render_nav('/categories')

    html_content = f'''
    <h1><img src="/static/logo.png" alt="kuasarr logo" class="logo"/>kuasarr</h1>
    {nav}
    <h2>Category Management</h2>
    <p>Organize downloads into categories with custom download paths and file patterns.</p>

    <div class="categories-actions">
        <button class="btn-primary" onclick="showAddCategoryModal()">
            <span class="btn-icon">+</span> Add Category
        </button>
    </div>

    <div id="categories-list" class="categories-list">
        <div class="loading-message">Loading categories...</div>
    </div>

    <div id="category-form-modal" class="modal-overlay">
        <div class="modal">
            <h3 id="modal-title">Add Category</h3>
            <form id="category-form">
                <input type="hidden" id="category-id" value="">

                <div class="form-group">
                    <label for="category-name">Category Name <span class="required">*</span></label>
                    <input type="text" id="category-name" name="name" maxlength="50" required
                           placeholder="e.g., Movies, TV Shows, Music">
                    <div class="field-error" id="name-error"></div>
                </div>

                <div class="form-group">
                    <label for="category-path">Download Path <span class="required">*</span></label>
                    <input type="text" id="category-path" name="download_path" maxlength="500" required
                           placeholder="/downloads/movies">
                    <div class="form-help">Absolute path where downloads in this category will be saved</div>
                    <div class="field-error" id="path-error"></div>
                </div>

                <div class="form-group">
                    <label for="category-patterns">File Patterns</label>
                    <div class="patterns-container" id="patterns-container">
                        <div class="pattern-row">
                            <input type="text" class="pattern-input" placeholder="*.mkv" maxlength="100">
                            <button type="button" class="btn-icon-remove" onclick="removePatternRow(this)">-</button>
                        </div>
                    </div>
                    <button type="button" class="btn-secondary btn-sm" onclick="addPatternRow()">+ Add Pattern</button>
                    <div class="form-help">File patterns to auto-assign to this category (e.g., *.mkv, *movie*)</div>
                </div>

                <div class="form-feedback" id="form-feedback"></div>

                <div class="modal-actions">
                    <button type="button" class="btn-secondary" onclick="closeCategoryModal()">Cancel</button>
                    <button type="submit" class="btn-primary">
                        <span class="btn-text">Save</span>
                        <span class="btn-spinner" hidden>Saving...</span>
                    </button>
                </div>
            </form>
        </div>
    </div>

    <div id="delete-modal" class="modal-overlay">
        <div class="modal modal-small">
            <h3>Delete Category?</h3>
            <p>Are you sure you want to delete the category <strong id="delete-category-name"></strong>?</p>
            <p class="warning-text">This action cannot be undone.</p>
            <div class="modal-actions">
                <button type="button" class="btn-secondary" onclick="closeDeleteModal()">Cancel</button>
                <button type="button" class="btn-danger" id="confirm-delete-btn">Delete</button>
            </div>
        </div>
    </div>

    <style>
        .categories-actions {{
            margin: 20px 0;
            text-align: left;
        }}

        .categories-list {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            max-width: 700px;
            margin: 0 auto;
        }}

        .category-card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: var(--border-radius);
            padding: 16px;
            text-align: left;
            transition: box-shadow 0.2s ease;
        }}

        .category-card:hover {{
            box-shadow: 0 2px 8px var(--card-shadow);
        }}

        .category-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}

        .category-name {{
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--fg-color);
        }}

        .category-path {{
            font-family: monospace;
            font-size: 0.9rem;
            color: var(--text-muted);
            margin-bottom: 8px;
            word-break: break-all;
        }}

        .category-patterns {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 8px;
        }}

        .pattern-tag {{
            background: var(--code-bg);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.85rem;
            font-family: monospace;
            color: var(--fg-color);
        }}

        .category-actions {{
            display: flex;
            gap: 8px;
        }}

        .btn-small {{
            padding: 4px 12px;
            font-size: 0.85rem;
        }}

        .empty-message {{
            text-align: center;
            padding: 40px 20px;
            color: var(--text-muted);
        }}

        .loading-message {{
            text-align: center;
            padding: 40px 20px;
            color: var(--text-muted);
        }}

        /* Modal styles */
        .modal-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            display: none;
            justify-content: center;
            align-items: flex-start;
            z-index: 1000;
            padding: 20px;
            overflow-y: auto;
        }}

        .modal-overlay.active {{
            display: flex;
        }}

        .modal {{
            background: var(--card-bg);
            border-radius: var(--border-radius);
            padding: 24px;
            max-width: 500px;
            width: 100%;
            margin: auto;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }}

        .modal-small {{
            max-width: 400px;
        }}

        .modal h3 {{
            margin-top: 0;
            margin-bottom: 20px;
        }}

        .modal-actions {{
            display: flex;
            justify-content: flex-end;
            gap: 12px;
            margin-top: 24px;
        }}

        .form-group {{
            margin-bottom: 16px;
            text-align: left;
        }}

        .form-group label {{
            display: block;
            font-weight: 500;
            margin-bottom: 6px;
        }}

        .required {{
            color: var(--error-color);
        }}

        .form-help {{
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-top: 4px;
        }}

        .field-error {{
            display: none;
            color: var(--error-color);
            font-size: 0.85rem;
            margin-top: 4px;
        }}

        .field-error.visible {{
            display: block;
        }}

        .patterns-container {{
            margin-bottom: 8px;
        }}

        .pattern-row {{
            display: flex;
            gap: 8px;
            margin-bottom: 8px;
        }}

        .pattern-row input {{
            flex: 1;
            margin-bottom: 0;
        }}

        .btn-icon-remove {{
            background: var(--error-color);
            color: white;
            border: none;
            width: 32px;
            height: 32px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 1.2rem;
            line-height: 1;
        }}

        .btn-icon-remove:hover {{
            opacity: 0.9;
        }}

        .warning-text {{
            color: var(--error-color);
            font-size: 0.9rem;
        }}

        .btn-icon {{
            margin-right: 4px;
        }}

        @media (max-width: 600px) {{
            .modal {{
                margin: 0;
                max-height: 90vh;
                overflow-y: auto;
            }}

            .category-header {{
                flex-direction: column;
                align-items: flex-start;
                gap: 8px;
            }}

            .modal-actions {{
                flex-direction: column-reverse;
            }}

            .modal-actions button {{
                width: 100%;
            }}
        }}
    </style>

    <script>
        let categories = [];
        let deleteCategoryId = null;

        // Load categories on page load
        document.addEventListener('DOMContentLoaded', loadCategories);

        async function loadCategories() {{
            try {{
                const response = await kuasarrApiFetch('/api/categories');
                const data = await response.json();

                if (data.success) {{
                    categories = data.categories || [];
                    renderCategories();
                }} else {{
                    showError('Failed to load categories: ' + (data.error || 'Unknown error'));
                }}
            }} catch (e) {{
                showError('Failed to load categories: ' + e.message);
            }}
        }}

        function renderCategories() {{
            const container = document.getElementById('categories-list');

            if (categories.length === 0) {{
                container.innerHTML = `
                    <div class="empty-message">
                        <p>No categories yet.</p>
                        <p>Click "Add Category" to create your first category.</p>
                    </div>
                `;
                return;
            }}

            container.innerHTML = categories.map(cat => `
                <div class="category-card" data-id="${{cat.id}}">
                    <div class="category-header">
                        <span class="category-name">${{escapeHtml(cat.name)}}</span>
                        <div class="category-actions">
                            <button class="btn-secondary btn-sm" onclick="editCategory('${{cat.id}}')">Edit</button>
                            <button class="btn-danger btn-sm" onclick="confirmDeleteCategory('${{cat.id}}')">Delete</button>
                        </div>
                    </div>
                    <div class="category-path">${{escapeHtml(cat.download_path)}}</div>
                    ${{cat.file_patterns && cat.file_patterns.length > 0 ? `
                        <div class="category-patterns">
                            ${{cat.file_patterns.map(p => `<span class="pattern-tag">${{escapeHtml(p)}}</span>`).join('')}}
                        </div>
                    ` : ''}}
                </div>
            `).join('');
        }}

        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}

        function showAddCategoryModal() {{
            document.getElementById('modal-title').textContent = 'Add Category';
            document.getElementById('category-id').value = '';
            document.getElementById('category-form').reset();
            document.getElementById('patterns-container').innerHTML = `
                <div class="pattern-row">
                    <input type="text" class="pattern-input" placeholder="*.mkv" maxlength="100">
                    <button type="button" class="btn-icon-remove" onclick="removePatternRow(this)">-</button>
                </div>
            `;
            clearErrors();
            document.getElementById('category-form-modal').classList.add('active');
        }}

        function editCategory(categoryId) {{
            const category = categories.find(c => c.id === categoryId);
            if (!category) return;

            document.getElementById('modal-title').textContent = 'Edit Category';
            document.getElementById('category-id').value = category.id;
            document.getElementById('category-name').value = category.name;
            document.getElementById('category-path').value = category.download_path;

            // Render patterns
            const patterns = category.file_patterns || [];
            const container = document.getElementById('patterns-container');
            if (patterns.length > 0) {{
                container.innerHTML = patterns.map(p => `
                    <div class="pattern-row">
                        <input type="text" class="pattern-input" value="${{escapeHtml(p)}}" maxlength="100">
                        <button type="button" class="btn-icon-remove" onclick="removePatternRow(this)">-</button>
                    </div>
                `).join('');
            }} else {{
                container.innerHTML = `
                    <div class="pattern-row">
                        <input type="text" class="pattern-input" placeholder="*.mkv" maxlength="100">
                        <button type="button" class="btn-icon-remove" onclick="removePatternRow(this)">-</button>
                    </div>
                `;
            }}

            clearErrors();
            document.getElementById('category-form-modal').classList.add('active');
        }}

        function closeCategoryModal() {{
            document.getElementById('category-form-modal').classList.remove('active');
        }}

        function addPatternRow() {{
            const container = document.getElementById('patterns-container');
            const row = document.createElement('div');
            row.className = 'pattern-row';
            row.innerHTML = `
                <input type="text" class="pattern-input" placeholder="*.mp4" maxlength="100">
                <button type="button" class="btn-icon-remove" onclick="removePatternRow(this)">-</button>
            `;
            container.appendChild(row);
        }}

        function removePatternRow(btn) {{
            const rows = document.querySelectorAll('.pattern-row');
            if (rows.length > 1) {{
                btn.closest('.pattern-row').remove();
            }} else {{
                // Clear the input instead of removing the last row
                const input = btn.closest('.pattern-row').querySelector('input');
                input.value = '';
            }}
        }}

        function clearErrors() {{
            document.querySelectorAll('.field-error').forEach(el => el.classList.remove('visible'));
            document.querySelectorAll('.form-group input').forEach(el => el.classList.remove('has-error'));
            document.getElementById('form-feedback').textContent = '';
            document.getElementById('form-feedback').className = 'form-feedback';
        }}

        function showFieldError(fieldId, message) {{
            const errorEl = document.getElementById(fieldId + '-error');
            const inputEl = document.getElementById('category-' + fieldId.replace('_', '-'));
            if (errorEl) {{
                errorEl.textContent = message;
                errorEl.classList.add('visible');
            }}
            if (inputEl) {{
                inputEl.classList.add('has-error');
            }}
        }}

        function showFormFeedback(message, isError) {{
            const feedback = document.getElementById('form-feedback');
            feedback.textContent = message;
            feedback.className = 'form-feedback ' + (isError ? 'error' : 'success');
        }}

        function showError(message) {{
            const container = document.getElementById('categories-list');
            container.innerHTML = `<div class="empty-message" style="color: var(--error-color);">${{escapeHtml(message)}}</div>`;
        }}

        // Form submission
        document.getElementById('category-form').addEventListener('submit', async function(e) {{
            e.preventDefault();
            clearErrors();

            const categoryId = document.getElementById('category-id').value;
            const name = document.getElementById('category-name').value.trim();
            const downloadPath = document.getElementById('category-path').value.trim();

            // Collect patterns
            const patterns = [];
            document.querySelectorAll('.pattern-input').forEach(input => {{
                const value = input.value.trim();
                if (value) patterns.push(value);
            }});

            const data = {{
                name: name,
                download_path: downloadPath,
                file_patterns: patterns
            }};

            const submitBtn = this.querySelector('button[type="submit"]');
            const btnText = submitBtn.querySelector('.btn-text');
            const btnSpinner = submitBtn.querySelector('.btn-spinner');

            submitBtn.disabled = true;
            btnText.hidden = true;
            btnSpinner.hidden = false;

            try {{
                const url = categoryId ? `/api/categories/${{categoryId}}` : '/api/categories';
                const method = categoryId ? 'POST' : 'POST';

                const response = await kuasarrApiFetch(url, {{
                    method: method,
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify(data)
                }});

                const result = await response.json();

                if (result.success) {{
                    closeCategoryModal();
                    await loadCategories();
                }} else if (result.errors) {{
                    Object.keys(result.errors).forEach(field => {{
                        showFieldError(field, result.errors[field]);
                    }});
                    showFormFeedback('Please correct the errors above.', true);
                }} else {{
                    showFormFeedback(result.error || 'An error occurred.', true);
                }}
            }} catch (e) {{
                showFormFeedback('Network error: ' + e.message, true);
            }} finally {{
                submitBtn.disabled = false;
                btnText.hidden = false;
                btnSpinner.hidden = true;
            }}
        }});

        // Delete functionality
        function confirmDeleteCategory(categoryId) {{
            const category = categories.find(c => c.id === categoryId);
            if (!category) return;

            deleteCategoryId = categoryId;
            document.getElementById('delete-category-name').textContent = category.name;
            document.getElementById('delete-modal').classList.add('active');
        }}

        function closeDeleteModal() {{
            document.getElementById('delete-modal').classList.remove('active');
            deleteCategoryId = null;
        }}

        document.getElementById('confirm-delete-btn').addEventListener('click', async function() {{
            if (!deleteCategoryId) return;

            try {{
                const response = await kuasarrApiFetch(`/api/categories/${{deleteCategoryId}}`, {{
                    method: 'DELETE'
                }});

                const result = await response.json();

                if (result.success) {{
                    closeDeleteModal();
                    await loadCategories();
                }} else {{
                    alert('Failed to delete: ' + (result.error || 'Unknown error'));
                }}
            }} catch (e) {{
                alert('Network error: ' + e.message);
            }}
        }});

        // Close modals on overlay click
        document.getElementById('category-form-modal').addEventListener('click', function(e) {{
            if (e.target === this) closeCategoryModal();
        }});

        document.getElementById('delete-modal').addEventListener('click', function(e) {{
            if (e.target === this) closeDeleteModal();
        }});

        // Close modals on Escape key
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') {{
                closeCategoryModal();
                closeDeleteModal();
            }}
        }});
    </script>
    '''

    return render_centered_html(html_content)
