import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST = os.getenv("MOCK_EXTERNAL_LLM_HOST", "0.0.0.0")
PORT = int(os.getenv("MOCK_EXTERNAL_LLM_PORT", "18080"))
MODEL = os.getenv("MOCK_EXTERNAL_LLM_MODEL", "mock-external-llm")
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
        if self.path == "/v1/models":
            self._send_json(
                {
                    "object": "list",
                    "data": [
                        {
                            "id": MODEL,
                            "object": "model",
                            "owned_by": "tenderwriter",
                        }
                    ],
                }
            )
            return
        self._send_json({"detail": "not found"}, status=404)

    @staticmethod
    def _extract_prompt(payload: dict) -> str:
        prompt = payload.get("prompt")
        if isinstance(prompt, str) and prompt:
            return prompt

        messages = payload.get("messages")
        if isinstance(messages, list):
            parts: list[str] = []
            for message in messages:
                if not isinstance(message, dict):
                    continue
                role = message.get("role", "user")
                content = message.get("content", "")
                if isinstance(content, list):
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text")
                            if isinstance(text, str):
                                text_parts.append(text)
                    content = "\n".join(text_parts)
                if isinstance(content, str) and content:
                    parts.append(f"[{role}] {content}")
            return "\n".join(parts)

        return ""

    def do_POST(self) -> None:
        if self.path not in {"/completion", "/v1/completions", "/v1/chat/completions"}:
            self._send_json({"detail": "not found"}, status=404)
            return

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except json.JSONDecodeError:
            self._send_json({"detail": "invalid json"}, status=400)
            return

        prompt = self._extract_prompt(payload)
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

        if self.path == "/v1/chat/completions":
            self._send_json(
                {
                    "id": "chatcmpl-mock",
                    "object": "chat.completion",
                    "model": MODEL,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "mock ok"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }
            )
            return

        if self.path == "/v1/completions":
            self._send_json(
                {
                    "id": "cmpl-mock",
                    "object": "text_completion",
                    "model": MODEL,
                    "choices": [{"index": 0, "text": "mock ok", "finish_reason": "stop"}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }
            )
            return

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
