"""Vercel entrypoint. HTTP plumbing only - all logic lives in leader_rules."""
import json
from http.server import BaseHTTPRequestHandler

try:
    from leader_rules import analyze_graph
    IMPORT_ERROR = None
except Exception as exc:  # bundling problem shows as a readable message, not a bare 500
    analyze_graph, IMPORT_ERROR = None, repr(exc)


def handle_request(payload):
    """Pure: dict in, (status, dict) out. Tested directly, no server needed."""
    if IMPORT_ERROR:
        return 500, {"error": "leader_rules failed to import on the server: " + IMPORT_ERROR}
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
        return 400, {"error": "expected JSON body with a 'nodes' list"}
    try:
        return 200, analyze_graph(
            payload["nodes"],
            payload.get("edges") or [],
            payload.get("rules"),
        )
    except Exception as exc:
        return 500, {"error": type(exc).__name__ + ": " + str(exc)}


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

    def do_GET(self):
        # health check - lets you verify the function from a browser address bar
        self._send(200, {"ok": IMPORT_ERROR is None, "service": "leadership gap detector",
                         "import_error": IMPORT_ERROR,
                         "usage": "POST {nodes:[...], edges:[...], rules:{...}}"})

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
