"""Offline tests for reusing and replacing a saved YouTube authorization."""

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import youtube_analytics_pull as youtube


class CredentialTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name).resolve()
        self.client_path = root / "client.json"
        self.token_path = root / "secrets" / "token.json"
        self.token_path.parent.mkdir()
        self.token_path.write_text('{"fixture": "saved"}', encoding="utf-8")
        self.creds = Mock(valid=True, expired=False, refresh_token="fixture")
        self.creds.has_scopes.return_value = True
        self.creds.to_json.return_value = '{"fixture": "updated"}'
        self.credentials = Mock()
        self.credentials.from_authorized_user_file.return_value = self.creds
        self.flow = Mock()
        self.flow.from_client_secrets_file.return_value.run_local_server.return_value = self.creds
        self.request = Mock()
        modules = patch.dict(sys.modules, {
            "google.auth.transport.requests": SimpleNamespace(Request=self.request),
            "google.oauth2.credentials": SimpleNamespace(Credentials=self.credentials),
            "google_auth_oauthlib.flow": SimpleNamespace(InstalledAppFlow=self.flow),
        })
        modules.start()
        self.addCleanup(modules.stop)

    def test_valid_authorization_does_not_write(self):
        with patch.object(youtube, "save_credentials") as save:
            self.assertIs(youtube.load_credentials(self.client_path, self.token_path), self.creds)
        save.assert_not_called()
        self.creds.refresh.assert_not_called()
        self.flow.from_client_secrets_file.assert_not_called()

    def test_refresh_replaces_the_saved_authorization(self):
        self.creds.expired = True
        self.creds.refresh.side_effect = lambda _: setattr(self.creds, "expired", False)
        self.assertIs(youtube.load_credentials(self.client_path, self.token_path), self.creds)
        self.creds.refresh.assert_called_once_with(self.request.return_value)
        self.assert_updated()

    def test_login_saves_a_new_authorization(self):
        self.token_path.unlink()
        self.client_path.touch()
        self.assertIs(youtube.load_credentials(self.client_path, self.token_path), self.creds)
        self.flow.from_client_secrets_file.return_value.run_local_server.assert_called_once_with(port=0)
        self.assert_updated()

    def test_failed_replace_keeps_the_old_authorization(self):
        with patch.object(youtube.os, "replace", side_effect=OSError("simulated failure")):
            with self.assertRaises(OSError):
                youtube.save_credentials(self.token_path, self.creds.to_json())
        self.assertEqual(self.token_path.read_text(encoding="utf-8"), '{"fixture": "saved"}')
        self.assertEqual(list(self.token_path.parent.iterdir()), [self.token_path])

    def assert_updated(self):
        self.assertEqual(self.token_path.read_text(encoding="utf-8"), '{"fixture": "updated"}')
        self.assertEqual(list(self.token_path.parent.iterdir()), [self.token_path])
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(self.token_path.stat().st_mode), 0o600)
