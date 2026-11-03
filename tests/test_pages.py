"""Smoke tests for the read-only placeholder pages."""

import os
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app import bind_settings, create_app

FAKE_PASSWORD = "test-password"
FAKE_HASH = generate_password_hash(FAKE_PASSWORD)


class BindSettingsTests(unittest.TestCase):
    def test_defaults_are_localhost_without_debug(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(bind_settings(), ("127.0.0.1", 5000, False))

    def test_host_port_and_debug_overrides(self):
        with patch.dict(
            os.environ,
            {"HOST": "127.0.0.1", "PORT": "5001", "FLASK_DEBUG": "1"},
            clear=True,
        ):
            self.assertEqual(bind_settings(), ("127.0.0.1", 5001, True))

    def test_debug_stays_off_for_other_values(self):
        with patch.dict(os.environ, {"FLASK_DEBUG": "true"}, clear=True):
            self.assertEqual(bind_settings()[2], False)


class PageTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test-secret",
                "ADMIN_PASSWORD_HASH": FAKE_HASH,
            },
        )
        self.env.start()
        self.client = create_app().test_client()
        self._login()

    def tearDown(self):
        self.env.stop()

    def _login(self):
        self.client.get("/login")
        with self.client.session_transaction() as sess:
            token = sess["csrf_token"]
        response = self.client.post(
            "/login",
            data={
                "username": "admin",
                "password": FAKE_PASSWORD,
                "csrf_token": token,
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_fleet_is_an_empty_readonly_table(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        for column in ("Name", "Host", "Status", "CPU", "Memory", "Last check"):
            self.assertIn(column, body)
        self.assertIn("No servers yet.", body)
        self.assertIn(">Logout<", body)
        self.assertEqual(body.lower().count("<form"), 1)
        self.assertEqual(body.lower().count("<script"), 1)
        self.assertIn("/static/refresh.js", body)
        self.assertNotIn("innerHTML", body)
        self.assertNotIn("Remove", body)

    def test_fleet_rejects_writes(self):
        self.assertEqual(self.client.post("/").status_code, 405)

    def test_unknown_detail_is_generic(self):
        response = self.client.get("/servers/sample")
        self.assertEqual(response.status_code, 404)
        body = response.get_data(as_text=True)
        self.assertIn("Not found", body)
        self.assertNotIn("sample", body)
        self.assertNotIn("<b>", body)

    def test_unknown_numeric_detail_hides_the_id(self):
        response = self.client.get("/servers/4242")
        self.assertEqual(response.status_code, 404)
        body = response.get_data(as_text=True)
        self.assertIn("Not found", body)
        self.assertNotIn("4242", body)

    def test_detail_rejects_writes(self):
        self.assertEqual(self.client.post("/servers/1").status_code, 405)


if __name__ == "__main__":
    unittest.main()
