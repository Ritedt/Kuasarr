# -*- coding: utf-8 -*-
"""Tests for debug utilities (Termbin integration)."""

import pytest
from unittest.mock import patch, MagicMock
from kuasarr.shared.debug import upload_to_termbin, upload_exception


class TestUploadToTermbin:
    """Tests for upload_to_termbin function."""

    @patch('socket.socket')
    def test_successful_upload(self, mock_socket_class):
        """Test successful termbin upload."""
        mock_socket = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        mock_socket.recv.return_value = b"https://termbin.com/abc123\x00"

        result = upload_to_termbin("Test debug content")

        assert result == "https://termbin.com/abc123"
        mock_socket.connect.assert_called_once_with(("termbin.com", 9999))
        mock_socket.sendall.assert_called_once()

    @patch('socket.socket')
    def test_upload_with_empty_content(self, mock_socket_class):
        """Test upload with empty content."""
        mock_socket = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        mock_socket.recv.return_value = b"https://termbin.com/xyz789\x00"

        result = upload_to_termbin("")

        assert result is None

    @patch('socket.socket')
    def test_socket_error(self, mock_socket_class):
        """Test handling of socket error."""
        mock_socket_class.side_effect = OSError("Connection refused")

        result = upload_to_termbin("Test content")

        assert result is None

    @patch('socket.socket')
    def test_empty_response(self, mock_socket_class):
        """Test handling of empty response."""
        mock_socket = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        mock_socket.recv.return_value = b""

        result = upload_to_termbin("Test content")

        assert result is None


class TestUploadException:
    """Tests for upload_exception function."""

    @patch('kuasarr.shared.debug.upload_to_termbin')
    def test_successful_exception_upload(self, mock_upload):
        """Test uploading exception info."""
        mock_upload.return_value = "https://termbin.com/err456"

        try:
            raise ValueError("Test error message")
        except Exception as e:
            result = upload_exception(e)

        assert result == "https://termbin.com/err456"
        mock_upload.assert_called_once()
        call_args = mock_upload.call_args[0][0]
        assert "ValueError" in call_args
        assert "Test error message" in call_args

    @patch('kuasarr.shared.debug.upload_to_termbin')
    def test_upload_failure(self, mock_upload):
        """Test handling when upload fails."""
        mock_upload.return_value = None

        try:
            raise RuntimeError("Another error")
        except Exception as e:
            result = upload_exception(e)

        assert result is None
