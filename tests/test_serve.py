"""Exercise preview-server seeking through real HTTP requests using only stdlib."""

import functools
import http.client
import http.server
from pathlib import Path
import tempfile
import threading
import unittest

from serve import Handler


class KeepAliveHandler(Handler):
    # Reuse one handler across requests to catch stale range state.
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass


class RangeServingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        root = Path(temporary.name)
        cls.media = bytes(range(256)) * 4097
        (root / "movie.mp4").write_bytes(cls.media)
        (root / "empty.mp4").write_bytes(b"")
        (root / "index.html").write_bytes(b"<h1>Preview</h1>")
        (root / "folder").mkdir()
        (root / "folder" / "clip.mp4").write_bytes(b"clip")
        cls.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(KeepAliveHandler, directory=root)
        )
        cls.addClassCleanup(cls.server.server_close)
        thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        thread.start()
        cls.addClassCleanup(thread.join)
        cls.addClassCleanup(cls.server.shutdown)

    def setUp(self):
        self.connection = http.client.HTTPConnection(
            *self.server.server_address, timeout=5
        )
        self.addCleanup(self.connection.close)

    def request(self, method="GET", path="/movie.mp4", headers=None):
        self.connection.request(method, path, headers=headers or {})
        with self.connection.getresponse() as response:
            body = response.read()
        return response, body

    def test_finite_seek_returns_exact_bytes(self):
        response, body = self.request(headers={"Range": "bytes=1000000-1001023"})
        self.assertEqual(response.status, 206)
        self.assertEqual(body, self.media[1000000:1001024])
        self.assertEqual(response.getheader("Content-Length"), "1024")
        self.assertEqual(
            response.getheader("Content-Range"),
            f"bytes 1000000-1001023/{len(self.media)}",
        )
        self.assertEqual(response.getheader("Content-Type"), "video/mp4")
        self.assertEqual(response.getheader("Accept-Ranges"), "bytes")
        self.assertEqual(response.getheader("Cache-Control"), "no-store, max-age=0")

    def test_open_suffix_and_clamped_ranges(self):
        size = len(self.media)
        for requested, start, end in (
            (f"bytes={size - 19}-", size - 19, size - 1),
            ("bytes=-17", size - 17, size - 1),
            (f"bytes={size - 5}-{size + 100}", size - 5, size - 1),
            (f"bytes=-{size + 100}", 0, size - 1),
            ("bytes=0-0", 0, 0),
            ("bytes=-" + "9" * 5000, 0, size - 1),
        ):
            with self.subTest(requested=requested[:80]):
                response, body = self.request(headers={"Range": requested})
                self.assertEqual(response.status, 206)
                self.assertEqual(body, self.media[start:end + 1])
                self.assertEqual(response.getheader("Content-Length"), str(end - start + 1))
                self.assertEqual(
                    response.getheader("Content-Range"), f"bytes {start}-{end}/{size}"
                )

    def test_unsatisfiable_ranges_have_empty_416_response(self):
        size = len(self.media)
        for requested in (
            f"bytes={size}-", f"bytes={size + 2}-{size + 5}", "bytes=-0",
            "bytes=" + "9" * 5000 + "-",
            f"bytes={size + 2}-" + "9" * 5000,
        ):
            with self.subTest(requested=requested[:80]):
                response, body = self.request(headers={"Range": requested})
                self.assertEqual(response.status, 416)
                self.assertEqual(body, b"")
                self.assertEqual(response.getheader("Content-Length"), "0")
                self.assertEqual(response.getheader("Content-Range"), f"bytes */{size}")

    def test_malformed_and_multiple_ranges_fall_back_to_full_delivery(self):
        for requested in ("bytes=not-a-range", "bytes=-", "bytes=9-2",
                          "bytes=0-2,5-7", "items=0-2"):
            with self.subTest(requested=requested):
                response, body = self.request(headers={"Range": requested})
                self.assertEqual(response.status, 200)
                self.assertEqual(body, self.media)
                self.assertEqual(response.getheader("Content-Length"), str(len(self.media)))
                self.assertIsNone(response.getheader("Content-Range"))

    def test_range_state_does_not_leak_into_full_get_or_head(self):
        self.request(headers={"Range": "bytes=2-4"})
        response, body = self.request()
        self.assertEqual(response.status, 200)
        self.assertEqual(body, self.media)
        self.assertEqual(response.getheader("Accept-Ranges"), "bytes")
        self.assertIsNone(response.getheader("Content-Range"))
        for headers in ({}, {"Range": "bytes=2-4"}, {"Range": "bytes=99999999-"}):
            response, body = self.request(method="HEAD", headers=headers)
            self.assertEqual(response.status, 200)
            self.assertEqual(body, b"")
            self.assertEqual(response.getheader("Content-Length"), str(len(self.media)))
            self.assertIsNone(response.getheader("Content-Range"))
        response, body = self.request(headers={"Range": "bytes=5-7"})
        self.assertEqual(response.status, 206)
        self.assertEqual(body, self.media[5:8])

    def test_empty_file_is_deliverable_but_has_no_satisfiable_range(self):
        response, body = self.request(path="/empty.mp4")
        self.assertEqual((response.status, body), (200, b""))
        response, body = self.request(path="/empty.mp4", headers={"Range": "bytes=0-"})
        self.assertEqual((response.status, body), (416, b""))
        self.assertEqual(response.getheader("Content-Range"), "bytes */0")

    def test_conditionals_take_precedence_over_range(self):
        response, _ = self.request(method="HEAD")
        modified = response.getheader("Last-Modified")
        response, body = self.request(headers={"Range": "bytes=2-4", "If-Range": modified})
        self.assertEqual((response.status, body), (206, self.media[2:5]))
        response, body = self.request(headers={
            "Range": "bytes=2-4", "If-Range": "Thu, 01 Jan 1970 00:00:00 GMT"
        })
        self.assertEqual((response.status, body), (200, self.media))
        response, body = self.request(headers={
            "Range": "bytes=2-4", "If-Modified-Since": modified
        })
        self.assertEqual((response.status, body), (304, b""))
        self.assertIsNone(response.getheader("Content-Range"))

    def test_directory_and_missing_file_handling_remain_intact(self):
        response, body = self.request(path="/", headers={"Range": "bytes=0-2"})
        self.assertEqual((response.status, body), (200, b"<h1>Preview</h1>"))
        response, _ = self.request(path="/folder", headers={"Range": "bytes=0-2"})
        self.assertEqual(response.status, 301)
        self.assertEqual(response.getheader("Location"), "/folder/")
        response, body = self.request(path="/folder/", headers={"Range": "bytes=0-2"})
        self.assertEqual(response.status, 200)
        self.assertIn(b'clip.mp4', body)
        response, _ = self.request(path="/missing.mp4", headers={"Range": "bytes=0-2"})
        self.assertEqual(response.status, 404)


if __name__ == "__main__":
    unittest.main()
