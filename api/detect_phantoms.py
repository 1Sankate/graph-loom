"""Vercel entrypoint. HTTP plumbing only - all logic lives in leader_rules."""
import json
from http.server import BaseHTTPRequestHandler

from leader_rules import analyze_graph


def handle_request(payload):
    """Pure: dict in, (status, dict) out. Tested directly, no server needed."""
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
        return 400, {"error": "expected JSON body with a 'nodes' list"}
    return 200, analyze_graph(
        payload["nodes"],
        payload.get("edges") or [],
        payload.get("rules"),
    )


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as err:
            status, body = 400, {"error": "invalid JSON: " + str(err)}
        else:
            status, body = handle_request(payload)
        self._send(status, body)

    def do_OPTIONS(self):
        self._send(204, None)

    def _send(self, status, body):
        raw = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if raw:
            self.wfile.write(raw)
