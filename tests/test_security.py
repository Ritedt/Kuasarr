# -*- coding: utf-8 -*-
"""Tests for security utilities (credential masking)."""

import pytest
from kuasarr.shared.security import (
    mask_sensitive_data,
    mask_url_credentials,
    mask_config_value,
    mask_dict_values,
    sanitize_log_message,
)


class TestMaskSensitiveData:
    """Tests for mask_sensitive_data function."""

    def test_basic_masking(self):
        """Test basic password masking."""
        result = mask_sensitive_data("password123")
        assert result == "p*********3"

    def test_short_value(self):
        """Test masking of short values."""
        result = mask_sensitive_data("ab")
        assert result == "**"

    def test_empty_value(self):
        """Test masking of empty string."""
        result = mask_sensitive_data("")
        assert result == "***EMPTY***"

    def test_none_value(self):
        """Test masking of None."""
        result = mask_sensitive_data(None)
        assert result == "***EMPTY***"

    def test_custom_visibility(self):
        """Test custom visible start/end."""
        result = mask_sensitive_data("secret_token_12345", visible_start=2, visible_end=3)
        assert result == "se*************345"


class TestMaskUrlCredentials:
    """Tests for mask_url_credentials function."""

    def test_http_basic_auth(self):
        """Test masking HTTP Basic Auth."""
        url = "http://user:pass@host.com/path"
        result = mask_url_credentials(url)
        assert result == "http://*CREDENTIALS*@host.com/path"

    def test_https_api_key(self):
        """Test masking API key in URL."""
        url = "https://api.key123@service.com/api"
        result = mask_url_credentials(url)
        assert result == "https://*CREDENTIALS*@service.com/api"

    def test_no_credentials(self):
        """Test URL without credentials."""
        url = "https://example.com/path"
        result = mask_url_credentials(url)
        assert result == "https://example.com/path"

    def test_empty_url(self):
        """Test empty URL."""
        result = mask_url_credentials("")
        assert result == ""


class TestMaskConfigValue:
    """Tests for mask_config_value function."""

    def test_password_key(self):
        """Test masking password key."""
        result = mask_config_value("password", "secret123")
        assert "*" in result
        assert result.startswith("s")
        assert result.endswith("3")

    def test_token_key(self):
        """Test masking token key."""
        result = mask_config_value("api_token", "abc123xyz")
        assert "*" in result

    def test_non_sensitive_key(self):
        """Test non-sensitive key is not masked."""
        result = mask_config_value("username", "john_doe")
        assert result == "john_doe"

    def test_empty_value(self):
        """Test empty value."""
        result = mask_config_value("password", "")
        assert result == ""


class TestMaskDictValues:
    """Tests for mask_dict_values function."""

    def test_mask_sensitive_keys(self):
        """Test masking sensitive keys in dict."""
        data = {
            "username": "john",
            "password": "secret123",
            "api_key": "key123",
        }
        result = mask_dict_values(data)
        assert result["username"] == "john"
        assert "*" in result["password"]
        assert "*" in result["api_key"]

    def test_nested_dict(self):
        """Test masking in nested dict."""
        data = {
            "user": {
                "name": "john",
                "password": "secret"
            }
        }
        result = mask_dict_values(data)
        assert result["user"]["name"] == "john"
        assert "*" in result["user"]["password"]


class TestSanitizeLogMessage:
    """Tests for sanitize_log_message function."""

    def test_mask_password_in_json(self):
        """Test masking password in JSON log."""
        message = 'Request: {"username": "john", "password": "secret123"}'
        result = sanitize_log_message(message)
        assert "secret123" not in result
        assert "***MASKED***" in result

    def test_mask_token_in_url(self):
        """Test masking token in URL."""
        message = "Calling API: https://api.example.com?token=abc123&user=john"
        result = sanitize_log_message(message)
        assert "abc123" not in result
        assert "***MASKED***" in result

    def test_no_sensitive_data(self):
        """Test message without sensitive data."""
        message = "Processing request for user john"
        result = sanitize_log_message(message)
        assert result == "Processing request for user john"
