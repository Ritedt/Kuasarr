# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import json
import re
import time
from typing import Optional

from bottle import request, response

from kuasarr.providers import shared_state
from kuasarr.providers.auth import require_api_key, require_csrf_token
from kuasarr.providers.log import error as log_error


def setup_categories_routes(app):
    """Setup routes for category management."""

    @app.get('/api/categories')
    @require_api_key
    def get_categories_api():
        """Get all categories as JSON."""
        response.content_type = 'application/json'
        categories = _get_all_categories()
        return json.dumps({"data": categories})

    @app.get('/api/categories/<category_id>')
    @require_api_key
    def get_category_api(category_id: str):
        """Get a single category by ID."""
        response.content_type = 'application/json'
        category = _get_category(category_id)
        if category:
            return json.dumps({"data": category})
        response.status = 404
        return json.dumps({"error": {"message": "Category not found"}})

    @app.post('/api/categories')
    @require_api_key
    @require_csrf_token
    def create_category_api():
        """Create a new category."""
        response.content_type = 'application/json'
        try:
            data = request.json or {}
            name = data.get('name', '').strip()
            pattern = data.get('pattern', '').strip()
            priority = int(data.get('priority', 0))
            enabled = bool(data.get('enabled', True))

            errors = {}
            if not name:
                errors['name'] = 'Category name is required'
            if not pattern:
                errors['pattern'] = 'Pattern is required'

            existing = _get_all_categories()
            for cat in existing:
                if cat['name'].lower() == name.lower():
                    errors['name'] = 'A category with this name already exists'
                    break

            if errors:
                response.status = 400
                return json.dumps({"error": {"message": "Validation failed", "details": errors}})

            category_id = _generate_category_id(name)
            category = {
                'id': category_id,
                'name': name,
                'pattern': pattern,
                'priority': priority,
                'enabled': enabled,
                'created_at': int(time.time()),
            }
            _save_category(category_id, category)
            return json.dumps({"data": category})

        except Exception as e:
            log_error(f"create_category failed: {e}")
            response.status = 500
            return json.dumps({"error": {"message": "Internal server error"}})

    @app.post('/api/categories/<category_id>')
    @require_api_key
    @require_csrf_token
    def update_category_api(category_id: str):
        """Update an existing category."""
        response.content_type = 'application/json'
        try:
            existing = _get_category(category_id)
            if not existing:
                response.status = 404
                return json.dumps({"error": {"message": "Category not found"}})

            data = request.json or {}
            name = data.get('name', existing.get('name', '')).strip()
            pattern = data.get('pattern', existing.get('pattern', '')).strip()
            priority = int(data.get('priority', existing.get('priority', 0)))
            enabled = bool(data.get('enabled', existing.get('enabled', True)))

            errors = {}
            if not name:
                errors['name'] = 'Category name is required'
            if not pattern:
                errors['pattern'] = 'Pattern is required'

            all_categories = _get_all_categories()
            for cat in all_categories:
                if cat['id'] != category_id and cat['name'].lower() == name.lower():
                    errors['name'] = 'A category with this name already exists'
                    break

            if errors:
                response.status = 400
                return json.dumps({"error": {"message": "Validation failed", "details": errors}})

            category = {
                'id': category_id,
                'name': name,
                'pattern': pattern,
                'priority': priority,
                'enabled': enabled,
                'created_at': existing.get('created_at', 0),
            }
            _save_category(category_id, category)
            return json.dumps({"data": category})

        except Exception as e:
            log_error(f"update_category failed: {e}")
            response.status = 500
            return json.dumps({"success": False, "error": "Internal server error"})

    @app.delete('/api/categories/<category_id>')
    @require_api_key
    @require_csrf_token
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
            log_error(f"delete_category failed: {e}")
            response.status = 500
            return json.dumps({"success": False, "error": "Internal server error"})


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



def _normalise_category(category: dict) -> dict:
    """Ensure category has the fields expected by the React UI."""
    if 'pattern' not in category:
        # Migrate old-format record: download_path + file_patterns → pattern
        category = dict(category)
        category['pattern'] = category.pop('download_path', '')
        category.pop('file_patterns', None)
    category.setdefault('priority', 0)
    category.setdefault('enabled', True)
    return category


def _get_all_categories() -> list:
    """Get all categories from storage."""
    try:
        db = shared_state.get_db("categories")
        raw_data = db.retrieve_all_titles()
        categories = []
        for key, value in raw_data:
            try:
                category = _normalise_category(json.loads(value))
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
            return _normalise_category(json.loads(value))
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

