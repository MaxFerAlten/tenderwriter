import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST = "0.0.0.0"
PORT = 18080
LAST_REQUEST: dict = {}


class MockLLMHandler(BaseHTTPRequestHandler):
    server_version = "MockExternalLLM/0.1"

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json({"status": "ok"})
            return
        if self.path == "/last":
            self._send_json(LAST_REQUEST or {"status": "empty"})
            return
        self._send_json({"detail": "not found"}, status=404)

    def do_POST(self) -> None:
        if self.path != "/completion":
            self._send_json({"detail": "not found"}, status=404)
            return

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except json.JSONDecodeError:
            self._send_json({"detail": "invalid json"}, status=400)
            return

        prompt = payload.get("prompt", "")
        LAST_REQUEST.clear()
        LAST_REQUEST.update(
            {
                "path": self.path,
                "headers": dict(self.headers.items()),
                "payload": payload,
                "prompt": prompt,
            }
        )

        print("\n=== MOCK EXTERNAL LLM PROMPT START ===", flush=True)
        print(prompt, flush=True)
        print("=== MOCK EXTERNAL LLM PROMPT END ===\n", flush=True)

        self._send_json(
            {
                "content": "mock ok",
                "tokens_evaluated": 10,
                "tokens_predicted": 5,
            }
        )


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), MockLLMHandler)
    print(f"Mock external LLM listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()
