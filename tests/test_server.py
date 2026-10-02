"""Tests for the HTTP API in diskwhy.server, run against a real local server."""

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from diskwhy import safety, scanner, server

TOKEN = "test-token"


class ServerTest(unittest.TestCase):
    """Authentication, listing and removal through the running server."""

    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
        cls.port = cls.httpd.server_address[1]
        cls.httpd.RequestHandlerClass = server.make_handler(TOKEN, cls.port, [])
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=safety.HOME, prefix=".diskwhy-test-")
        self.addCleanup(lambda: os.system(f"rm -rf '{self.tmp}'"))
        scanner.clear_cache()

    def call(self, path, body=None, token=TOKEN, host=None):
        """Send one request to the test server and return `(status, parsed_json)`."""
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=None if body is None else json.dumps(body).encode(),
            headers={
                "X-DiskWhy-Token": token,
                "Host": host or f"127.0.0.1:{self.port}",
            },
        )
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_api_needs_the_token(self):
        self.assertEqual(self.call("/api/volume", token="wrong")[0], 403)

    def test_rejects_foreign_host_header(self):
        self.assertEqual(self.call("/api/volume", host="evil.example")[0], 403)

    def test_index_needs_the_token_in_the_url(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/")
        self.assertEqual(ctx.exception.code, 403)
        ctx.exception.close()

    def test_ls_reports_sizes_largest_first(self):
        os.mkdir(os.path.join(self.tmp, "big"))
        with open(os.path.join(self.tmp, "big", "f"), "wb") as f:
            f.write(b"x" * 2_000_000)
        with open(os.path.join(self.tmp, "small"), "wb") as f:
            f.write(b"x")
        status, data = self.call("/api/ls?path=" + self.tmp)
        self.assertEqual(status, 200)
        self.assertEqual([e["name"] for e in data["entries"]], ["big", "small"])
        self.assertTrue(data["entries"][0]["is_dir"])
        self.assertGreaterEqual(data["entries"][0]["size"], 2_000_000)

    def test_trash_moves_and_keeps_the_data(self):
        target = os.path.join(self.tmp, "to-trash")
        os.mkdir(target)
        status, _ = self.call("/api/remove", {"path": target, "mode": "trash"})
        self.assertEqual(status, 200)
        self.assertFalse(os.path.exists(target))
        self.assertTrue(os.path.exists(os.path.join(safety.HOME, ".Trash", "to-trash")))
        os.system(f"rm -rf '{safety.HOME}/.Trash/to-trash'")

    def test_permanent_delete_requires_the_typed_name(self):
        target = os.path.join(self.tmp, "victim")
        os.mkdir(target)
        status, _ = self.call(
            "/api/remove", {"path": target, "mode": "delete", "confirm": "wrong"}
        )
        self.assertEqual(status, 409)
        self.assertTrue(os.path.exists(target))

        status, _ = self.call(
            "/api/remove", {"path": target, "mode": "delete", "confirm": "victim"}
        )
        self.assertEqual(status, 200)
        self.assertFalse(os.path.exists(target))

    def test_remove_refuses_protected_path_even_with_confirmation(self):
        status, _ = self.call(
            "/api/remove",
            {
                "path": safety.HOME,
                "mode": "delete",
                "confirm": os.path.basename(safety.HOME),
            },
        )
        self.assertEqual(status, 409)
        self.assertTrue(os.path.isdir(safety.HOME))

    def test_removing_a_symlink_leaves_its_target(self):
        real = os.path.join(self.tmp, "real")
        os.mkdir(real)
        link = os.path.join(self.tmp, "link")
        os.symlink(real, link)
        status, _ = self.call(
            "/api/remove", {"path": link, "mode": "delete", "confirm": "link"}
        )
        self.assertEqual(status, 200)
        self.assertFalse(os.path.lexists(link))
        self.assertTrue(os.path.isdir(real))


if __name__ == "__main__":
    unittest.main()
