"""Minimal HTTP server — exposes /run to trigger news fetch."""

import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from dotenv import load_dotenv

load_dotenv()

CRON_SECRET = os.getenv("CRON_SECRET", "")
PORT = int(os.getenv("PORT", "10000"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._respond(200, "ok")
            return

        if self.path.startswith("/run"):
            if CRON_SECRET and self.headers.get("X-Cron-Secret") != CRON_SECRET:
                self._respond(401, "unauthorized")
                return
            threading.Thread(target=self._trigger_run, daemon=True).start()
            self._respond(200, "started")
            return

        self._respond(404, "not found")

    def _trigger_run(self):
        import main
        try:
            main.run()
        except Exception as e:
            print(f"Run failed: {e}", file=sys.stderr)

    def _respond(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, format, *args):
        print(f"[server] {args[0]}")


if __name__ == "__main__":
    print(f"Listening on :{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
