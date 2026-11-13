"""Offline security and portability checks; never load the installed skill's .env."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import instagram_client as client
import private_files as files


TOKEN = "dummy_local_test_token_1234567890"


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="instagram portable ")
        self.root = Path(self.directory.name)
        self.env = self.root / ".env"
        self.root_patch = patch.object(client, "ROOT", self.root)
        self.env_patch = patch.object(client, "ENV", self.env)
        self.root_patch.start()
        self.env_patch.start()
        client.SECRETS.clear()

    def tearDown(self):
        self.env_patch.stop()
        self.root_patch.stop()
        self.directory.cleanup()

    def save(self):
        client.save_env({"INSTAGRAM_ACCESS_TOKEN": TOKEN, "INSTAGRAM_API_VERSION": "v25.0"})

    def command(self, *args):
        output = io.StringIO()
        with patch.object(sys, "argv", ["instagram_client.py", *args]), contextlib.redirect_stdout(output):
            client.main()
        return json.loads(output.getvalue())

    def test_missing_credentials_status_works_on_fresh_install(self):
        report = self.command("status")
        self.assertFalse(report["configured"])
        self.assertFalse(self.env.exists())

    def test_set_token_creates_private_file_on_fresh_install(self):
        with patch.object(sys.stdin, "isatty", return_value=True), patch.object(sys.stderr, "isatty", return_value=True), patch.object(client.getpass, "getpass", return_value=TOKEN):
            report = self.command("set-token")
        self.assertTrue(report["saved"])
        self.assertNotIn(TOKEN, json.dumps(report))
        self.assertEqual(client.load_env()["INSTAGRAM_ACCESS_TOKEN"], TOKEN)

    def test_set_token_rejects_agent_transcript(self):
        with patch.object(sys.stdin, "isatty", return_value=False):
            with self.assertRaises(client.Failure):
                self.command("set-token")
        self.assertFalse(self.env.exists())

    def test_user_can_replace_credentials_with_unsafe_permissions(self):
        if os.name == "nt":
            native = files.WindowsFiles()
            native.sddl = "D:P(A;;FA;;;WD)"
            with self.assertRaises(files.PrivateFileError):
                native.open(self.env, True, True, True)
        else:
            self.env.touch()
            self.env.chmod(0o666)
        with self.assertRaises(client.Failure):
            client.load_env()
        with patch.object(sys.stdin, "isatty", return_value=True), patch.object(sys.stderr, "isatty", return_value=True), patch.object(client.getpass, "getpass", return_value=TOKEN):
            self.assertTrue(self.command("set-token")["saved"])
        self.assertEqual(client.load_env()["INSTAGRAM_ACCESS_TOKEN"], TOKEN)

    def test_round_trip_and_permissions(self):
        self.save()
        self.assertEqual(client.load_env()["INSTAGRAM_ACCESS_TOKEN"], TOKEN)
        fd = files.open_private(self.env)
        os.close(fd)
        if os.name != "nt":
            self.assertEqual(self.env.stat().st_mode & 0o777, 0o600)

    def test_unicode_storage_path(self):
        folder = self.root / "zażółć gęślą"
        folder.mkdir()
        with patch.object(client, "ENV", folder / ".env"):
            self.save()
            self.assertEqual(client.load_env()["INSTAGRAM_ACCESS_TOKEN"], TOKEN)

    def test_existing_private_credentials_survive_refresh_write(self):
        self.save()
        client.save_env({"INSTAGRAM_ACCESS_TOKEN": TOKEN + "new", "INSTAGRAM_API_VERSION": "v25.0"})
        self.assertEqual(client.load_env()["INSTAGRAM_ACCESS_TOKEN"], TOKEN + "new")
        self.assertEqual(list(self.root.glob(".env.*")), [])

    def test_failed_atomic_replace_preserves_previous_credentials(self):
        self.save()
        with patch.object(files.os, "replace", side_effect=OSError("simulated disk error")):
            with self.assertRaises(client.Failure):
                client.save_env({"INSTAGRAM_ACCESS_TOKEN": TOKEN + "new"})
        self.assertEqual(client.load_env()["INSTAGRAM_ACCESS_TOKEN"], TOKEN)
        self.assertEqual(list(self.root.glob(".env.*")), [])

    def test_reject_directory_in_place_of_credentials(self):
        self.env.mkdir()
        with self.assertRaises(client.Failure):
            client.load_env()

    def test_reject_credential_symlink_without_reading_target(self):
        target = self.root / "target"
        target.write_text("this is not a credential")
        try:
            self.env.symlink_to(target)
        except OSError:
            self.skipTest("Creating symlinks requires Windows Developer Mode or permission")
        with self.assertRaises(client.Failure):
            client.load_env()

    @unittest.skipIf(os.name == "nt", "POSIX file mode test")
    def test_reject_group_readable_credentials(self):
        self.save()
        self.env.chmod(0o640)
        with self.assertRaises(client.Failure):
            client.load_env()

    @unittest.skipUnless(os.name == "nt", "Windows DACL test")
    def test_reject_windows_world_access_acl(self):
        native = files.WindowsFiles()
        native.sddl = "D:P(A;;FA;;;WD)"
        with self.assertRaises(files.PrivateFileError):
            native.open(self.env, True, True, True)

    def test_status_never_exposes_token(self):
        self.save()
        report = self.command("status")
        self.assertTrue(report["configured"])
        self.assertNotIn(TOKEN, json.dumps(report))

    def test_redacts_tokens_in_nested_payload_and_paging(self):
        client.SECRETS.add(TOKEN)
        value = client.scrub({"access_token": TOKEN, "nested": [f"https://example.com/?access_token={TOKEN}", "value=" + TOKEN]})
        self.assertNotIn(TOKEN, json.dumps(value))

    def test_missing_token_cannot_make_api_request(self):
        with patch.object(client, "request") as request:
            with self.assertRaises(client.Failure):
                self.command("get", "me")
            request.assert_not_called()

    def test_no_write_command_is_accepted(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.command("post", "me")

    def test_pagination_rejects_another_host(self):
        with self.assertRaises(client.Failure):
            client.next_params("https://example.com/v25.0/me/media?after=x", "/v25.0/me/media")

    def test_pagination_strips_token_and_preserves_configured_version(self):
        params = client.next_params(f"https://graph.instagram.com/v26.0/123/media?after=abc&access_token={TOKEN}", "/v25.0/123/media")
        self.assertEqual(params, {"after": "abc"})

    def test_lock_is_released_when_command_fails(self):
        lock = self.root / ".env.lock"
        with self.assertRaises(ValueError):
            with files.locked(lock):
                raise ValueError("test")
        with files.locked(lock, timeout=0):
            pass

    def test_concurrent_process_cannot_enter_held_lock(self):
        lock = self.root / ".env.lock"
        code = """import sys
sys.path.insert(0, sys.argv[1])
from private_files import locked, PrivateFileError
try:
    with locked(sys.argv[2], timeout=0.15):
        raise SystemExit(2)
except PrivateFileError:
    print('locked')
"""
        with files.locked(lock):
            result = subprocess.run([sys.executable, "-c", code, str(SCRIPTS), str(lock)], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "locked")
        with files.locked(lock, timeout=0):
            pass

    def test_valid_refresh_is_atomic_and_token_is_not_printed(self):
        self.save()
        with patch.object(client, "request", return_value={"access_token": TOKEN + "refreshed", "expires_in": 5184000}):
            report = self.command("refresh")
        self.assertTrue(report["refreshed"])
        self.assertNotIn(TOKEN, json.dumps(report))
        self.assertEqual(client.load_env()["INSTAGRAM_ACCESS_TOKEN"], TOKEN + "refreshed")

    def test_expired_refresh_never_contacts_api(self):
        client.save_env({"INSTAGRAM_ACCESS_TOKEN": TOKEN, "INSTAGRAM_TOKEN_EXPIRES_AT": "1"})
        with patch.object(client, "request") as request:
            with self.assertRaises(client.Failure):
                self.command("refresh")
            request.assert_not_called()

    def test_token_too_young_is_not_refreshed(self):
        client.save_env({"INSTAGRAM_ACCESS_TOKEN": TOKEN, "INSTAGRAM_TOKEN_ISSUED_AT": str(int(client.time.time()))})
        with patch.object(client, "request") as request:
            with self.assertRaises(client.Failure):
                self.command("refresh")
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
