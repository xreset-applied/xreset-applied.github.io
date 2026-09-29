#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Local preview server for the research website template.

Serves the repository root over HTTP with no build step and no caching, so a
browser refresh always shows your latest edit. Binds 0.0.0.0, so the preview is
reachable on every interface (localhost, LAN, Tailscale, ...).

    uv run serve.py            # serve on 0.0.0.0:8888
    uv run serve.py --port N   # override the port
    python3 serve.py           # (works too — no third-party deps)

The site is fully static; just refresh the browser after editing files.
"""

import argparse
import datetime
import email.utils
import functools
import http.server
import os
import re
import socket

DEFAULT_PORT = 8888
HOST = "0.0.0.0"
ROOT = os.path.dirname(os.path.abspath(__file__))


def _http_date(value):
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, IndexError, OverflowError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


class Handler(http.server.SimpleHTTPRequestHandler):
    """Static, seekable files rooted at the repo, with no-cache for live edits."""

    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".svg": "image/svg+xml",
        ".json": "application/json",
        ".ttf": "font/ttf",
        ".otf": "font/otf",
        ".woff2": "font/woff2",
    }

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def send_head(self):
        # A handler can serve several requests on one keep-alive connection.
        self.range_remaining = None
        requested = ",".join(self.headers.get_all("Range", []))
        match = re.fullmatch(r"bytes=([0-9]*)-([0-9]*)", requested.strip(), re.IGNORECASE)
        # Range is only defined for GET. Ignore unsupported/malformed range sets
        # rather than pretending to provide a multipart response.
        if self.command != "GET" or not match or not any(match.groups()):
            return super().send_head()

        path = self.translate_path(self.path)
        # Leave redirects, index pages, listings, and trailing-slash errors to
        # the standard handler; those responses may ignore Range.
        if os.path.isdir(path) or path.endswith("/"):
            return super().send_head()
        try:
            source = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        try:
            stat = os.fstat(source.fileno())
            modified = datetime.datetime.fromtimestamp(
                stat.st_mtime, datetime.timezone.utc
            ).replace(microsecond=0)
            since = self.headers.get("If-Modified-Since")
            if since is not None and "If-None-Match" not in self.headers:
                since = _http_date(since)
                if since is not None and modified <= since:
                    source.close()
                    return super().send_head()
            if_range = self.headers.get("If-Range")
            # We publish Last-Modified, not ETags. An unknown validator requires
            # the complete representation, never a potentially stale fragment.
            if if_range is not None and _http_date(if_range) != modified:
                source.close()
                return super().send_head()

            size = stat.st_size
            bounds = []
            digits = len(str(size))
            for value in match.groups():
                if not value:
                    bounds.append(None)
                else:
                    value = value.lstrip("0") or "0"
                    # Huge decimal offsets are legal; cap before int conversion
                    # so Python's integer-string limit cannot break a request.
                    bounds.append(min(int(value), size) if len(value) <= digits else size)
            first, last = bounds
            if first is not None and last is not None and first > last:
                source.close()
                return super().send_head()
            if first is None:
                start, end = max(0, size - last), size - 1
            else:
                start = first
                end = min(last, size - 1) if last is not None else size - 1
            if start >= size or start > end:
                source.close()
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None

            source.seek(start)
            self.range_remaining = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(self.range_remaining))
            self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
            self.end_headers()
            return source
        except BaseException:
            source.close()
            raise

    def copyfile(self, source, outputfile):
        try:
            if self.range_remaining is None:
                return super().copyfile(source, outputfile)
            while self.range_remaining:
                chunk = source.read(min(65536, self.range_remaining))
                if not chunk:
                    break
                outputfile.write(chunk)
                self.range_remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Seeking cancels in-flight media transfers in browsers.

    def log_message(self, fmt, *args):
        print("  %s - %s" % (self.address_string(), fmt % args))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"port to bind (default {DEFAULT_PORT})")
    args = parser.parse_args()

    handler = functools.partial(Handler, directory=ROOT)
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer((HOST, args.port), handler) as httpd:
        print(f"Research website template serving on {HOST}:{args.port} (root: {ROOT})")
        print(f"  local:      http://127.0.0.1:{args.port}/")
        print(f"  components:  http://127.0.0.1:{args.port}/components.html")
        print(f"  network:     http://{socket.gethostname()}:{args.port}/")
        print("  press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()
