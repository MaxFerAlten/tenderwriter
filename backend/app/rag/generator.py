"""
TenderWriter — LLM Generator (Ollama)

Generates text using a local LLM served by Ollama.
Supports multiple prompt templates for different proposal writing tasks
and streaming responses.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urlsplit, urlunsplit

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

_DOCKER_MARKER = Path("/.dockerenv")
_DOCKER_LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}
_INTERNAL_LLAMACPP_HOSTS = {"tw-gateway", "llama-tender", "llama-opencode", "gateway"}
_KNOWN_OPENAI_COMPATIBLE_PORTS = {1234, 8080, 5000, 5001, 11434}
_OPENAI_API_PATH_MARKERS = {"/v1", "/api/v1", "/chat/completions", "/completions"}


# ──────────────────────────────────────────────
# Prompt Templates
# ──────────────────────────────────────────────

PROMPT_TEMPLATES = {
    "proposal_section": """You are an expert proposal writer for tenders and RFPs.
Write a professional, compelling proposal section based on the following context and instructions.

IMPORTANT: Respond in the SAME LANGUAGE as the user's instructions and requirements.

## Retrieved Context
{context}

## Section Title
{section_title}

## Instructions
{instructions}

## Requirements to Address
{requirements}

Write the section in a professional tone suitable for a formal tender submission.
Be specific, reference concrete evidence from the context (projects, team members,
certifications), and ensure all listed requirements are addressed.
Do not make up information. If the context doesn't contain relevant information,
note what additional information would be needed.

## Output
Write the proposal section below:
""",

    "executive_summary": """You are an expert proposal writer.
Create a compelling executive summary for a tender proposal based on the following sections and context.

IMPORTANT: Respond in the SAME LANGUAGE as the proposal sections and requirements.

## Proposal Sections
{sections}

## Company Context
{context}

## Tender Requirements
{requirements}

Write a concise, compelling executive summary (300-500 words) that:
1. Highlights the key strengths and differentiators
2. Demonstrates understanding of the client's needs
3. References specific experience and qualifications
4. Creates a strong first impression

## Executive Summary
""",

    "requirement_analyzer": """You are an expert at analyzing tender/RFP documents.
Extract and categorize all requirements from the following tender document text.

IMPORTANT: Respond in the SAME LANGUAGE as the tender document.

## Tender Document
{document_text}

For each requirement found, provide:
1. The requirement text (exact or closely paraphrased)
2. Category (technical, financial, legal, experience, staffing, timeline, etc.)
3. Priority (must-have, should-have, nice-to-have)

Format your response as a JSON array:
[
  {{
    "text": "requirement description",
    "category": "category",
    "priority": "must-have|should-have|nice-to-have"
  }}
]

## Extracted Requirements
""",

    "compliance_checker": """You are an expert compliance reviewer for tender proposals.
Analyze whether the proposal section adequately addresses the given requirement.

IMPORTANT: Respond in the SAME LANGUAGE as the requirement and proposal section.

## Requirement
{requirement}

## Proposal Section
{section_content}

## Available Evidence
{context}

Evaluate the compliance and respond with:
1. Status: FULLY_ADDRESSED, PARTIALLY_ADDRESSED, or NOT_ADDRESSED
2. Explanation of what is covered
3. Gaps: what is missing or needs improvement
4. Suggestions for strengthening the response

Format as JSON:
{{
  "status": "...",
  "explanation": "...",
  "gaps": ["..."],
  "suggestions": ["..."]
}}

## Compliance Assessment
""",

    "general_qa": """ISTRUZIONI IMPORTANTI: Devi rispondere SEMPRE nella STESSA LINGUA della domanda dell'utente.
- Se la domanda è in ITALIANO, rispondi in ITALIANO
- Se la domanda è in INGLESE, rispondi in INGLESE
- Se la domanda è in SPAGNOLO, rispondi in SPAGNOLO

You are TenderWriter, an AI assistant for tender proposal writing.
Answer the user's question based on the retrieved context from the knowledge base.

## Retrieved Context
{context}

## User Question
{query}

## Response Constraints
{response_constraints}

Provide a helpful, accurate answer based on the available context.
If the context doesn't contain enough information, say so clearly.

RICORDA: Rispondi nella STESSA LINGUA della domanda sopra!
Inizia direttamente con la risposta finale, senza copiare intestazioni o sezioni del prompt.
""",
}


@dataclass
class GenerationResult:
    """Result from LLM generation."""
    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    template_used: str = ""


class Generator:
    """
    LLM text generation via Ollama HTTP API.

    Supports both synchronous and streaming generation with
    multiple prompt templates for different proposal writing tasks.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
    ):
        # Use llama_server settings by default, fallback to ollama for backward compatibility
        self.base_url = self._normalize_runtime_base_url(
            base_url or getattr(settings, 'llama_server_url', settings.ollama_base_url)
        )
        self.model = model or getattr(settings, 'llama_model', settings.ollama_model)
        self.provider = (provider or "llama").strip().lower()
        self.api_key = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None
        self.timeout = timeout or getattr(settings, 'llama_timeout', 120)
        if self.provider == "openrouter":
            self.base_url = self._normalize_openrouter_base_url(self.base_url)
        else:
            self.base_url = self._normalize_external_llm_base_url(self.base_url)

    @staticmethod
    def _running_in_docker() -> bool:
        return _DOCKER_MARKER.exists()

    @classmethod
    def _normalize_runtime_base_url(cls, base_url: str) -> str:
        normalized = (base_url or "").rstrip("/")
        if not normalized:
            return normalized

        parsed = urlsplit(normalized)
        hostname = (parsed.hostname or "").lower()
        if hostname not in _DOCKER_LOOPBACK_HOSTS or not cls._running_in_docker():
            return normalized

        netloc = "host.docker.internal"
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"

        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)).rstrip("/")

    @staticmethod
    def _normalize_external_llm_base_url(base_url: str) -> str:
        """Append /v1 to bare host:port URLs for external OpenAI-compatible servers.

        LM Studio, vLLM, and similar servers expose an OpenAI-compatible API
        at ``/v1``.  Users often configure just ``http://host:port`` without
        the path suffix, which causes the Generator to fall through to the
        Ollama code path.  This method detects that situation and appends
        ``/v1`` so that the OpenAI-compatible chat API is used instead.

        Ollama (default port 11434) is excluded because it uses its own
        ``/api/generate`` endpoint.
        """
        normalized = (base_url or "").rstrip("/")
        if not normalized:
            return normalized

        parsed = urlsplit(normalized)
        path = (parsed.path or "").rstrip("/").lower()

        # Already has a recognised API path — leave it alone.
        if path and any(path.endswith(m) for m in _OPENAI_API_PATH_MARKERS):
            return normalized

        hostname = (parsed.hostname or "").lower()

        # Internal llama.cpp hosts are handled by the legacy /completion path.
        if hostname in _INTERNAL_LLAMACPP_HOSTS:
            return normalized

        # Ollama uses port 11434 and its own /api/generate endpoint.
        if parsed.port == 11434:
            return normalized

        # Bare host:port (no meaningful path) that is NOT an internal host →
        # almost certainly an OpenAI-compatible server (LM Studio, vLLM, …).
        if not path or path == "/":
            logger.debug(
                "Auto-appending /v1 to bare external LLM URL",
                original_url=normalized,
            )
            return f"{normalized}/v1"

        return normalized

    @staticmethod
    def _normalize_openrouter_base_url(base_url: str) -> str:
        normalized = (base_url or "").rstrip("/")
        suffixes = (
            "/chat/completions",
            "/completions",
            "/models",
        )
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break
        return normalized.rstrip("/")

    @staticmethod
    def _strip_known_endpoint_suffix(base_url: str) -> str:
        normalized = (base_url or "").rstrip("/")
        suffixes = (
            "/chat/completions",
            "/completions",
            "/models",
        )
        for suffix in suffixes:
            if normalized.lower().endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break
        return normalized.rstrip("/")

    def _base_hostname(self) -> str:
        return (urlsplit(self.base_url).hostname or "").lower()

    def _base_path(self) -> str:
        return urlsplit(self.base_url).path.rstrip("/").lower()

    def _uses_openai_compatible_chat_api(self) -> bool:
        path = self._base_path()
        if path.endswith("/chat/completions"):
            return True
        if path in {"/v1", "/api/v1"}:
            return self._base_hostname() not in _INTERNAL_LLAMACPP_HOSTS
        return False

    def _uses_openai_compatible_completions_api(self) -> bool:
        path = self._base_path()
        return path.endswith("/completions") and not path.endswith("/chat/completions")

    def _openai_compatible_root_url(self) -> str:
        return self._strip_known_endpoint_suffix(self.base_url)

    def _openai_chat_url(self) -> str:
        if self._base_path().endswith("/chat/completions"):
            return self.base_url.rstrip("/")
        return f"{self._openai_compatible_root_url()}/chat/completions"

    def _openai_completion_url(self) -> str:
        if self._uses_openai_compatible_completions_api():
            return self.base_url.rstrip("/")
        return f"{self._openai_compatible_root_url()}/completions"

    def _legacy_llama_completion_url(self) -> str:
        if self._base_path().endswith("/v1"):
            return f"{self.base_url[:-3].rstrip('/')}/completion"
        return f"{self.base_url.rstrip('/')}/completion"

    def _request_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _raise_for_status_with_body(response: httpx.Response, *, context: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip()
            if detail:
                raise RuntimeError(
                    f"{context} failed with status {response.status_code}: {detail[:1000]}"
                ) from exc
            raise

    def _build_openrouter_payload(
        self,
        *,
        prompt: str,
        temperature: float,
        max_tokens: int,
        stop_tokens: list[str],
        stream: bool,
    ) -> dict:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stop_tokens:
            payload["stop"] = stop_tokens
        return payload

    def _build_openai_completion_payload(
        self,
        *,
        prompt: str,
        temperature: float,
        max_tokens: int,
        stop_tokens: list[str],
        stream: bool,
    ) -> dict:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stop_tokens:
            payload["stop"] = stop_tokens
        return payload

    @staticmethod
    def _extract_generated_text(data: dict) -> str:
        """Support both llama.cpp and OpenAI-style completion payloads."""
        content = data.get("content")
        if isinstance(content, str):
            return content

        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                text = first.get("text")
                if isinstance(text, str):
                    return text
                message = first.get("message")
                if isinstance(message, dict):
                    message_content = message.get("content")
                    if isinstance(message_content, str):
                        return message_content
        return ""

    @staticmethod
    def _extract_usage(data: dict) -> tuple[int | None, int | None]:
        """Extract token usage from llama.cpp, Ollama, or OpenAI-compatible responses."""
        prompt_tokens = data.get("tokens_evaluated") or data.get("prompt_eval_count")
        completion_tokens = data.get("tokens_predicted") or data.get("eval_count")

        usage = data.get("usage")
        if isinstance(usage, dict):
            if prompt_tokens is None:
                prompt_tokens = usage.get("prompt_tokens")
            if completion_tokens is None:
                completion_tokens = usage.get("completion_tokens")

        return prompt_tokens, completion_tokens

    @staticmethod
    def _parse_stream_line(line: str) -> dict | None:
        """Parse JSON or SSE `data:` stream lines into dict payloads."""
        line = line.strip()
        if not line:
            return None
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line:
            return None
        if line == "[DONE]":
            return {"done": True}
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _extract_stream_text_and_done(chunk: dict) -> tuple[str, bool]:
        """Extract streamed token text and completion flag for both payload formats."""
        content = chunk.get("content")
        if isinstance(content, str) and content:
            return content, bool(chunk.get("stop") or chunk.get("done"))

        choices = chunk.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                text = first.get("text")
                if isinstance(text, str) and text:
                    return text, first.get("finish_reason") is not None

                delta = first.get("delta")
                if isinstance(delta, dict):
                    delta_content = delta.get("content")
                    if isinstance(delta_content, str) and delta_content:
                        return delta_content, first.get("finish_reason") is not None

                message = first.get("message")
                if isinstance(message, dict):
                    message_content = message.get("content")
                    if isinstance(message_content, str) and message_content:
                        return message_content, first.get("finish_reason") is not None

                if first.get("finish_reason") is not None:
                    return "", True

        return "", bool(chunk.get("stop") or chunk.get("done"))

    @staticmethod
    def _should_retry_empty_openai_response(data: dict) -> bool:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return False
        first = choices[0]
        if not isinstance(first, dict):
            return False
        message = first.get("message")
        if not isinstance(message, dict):
            return False
        content = message.get("content")
        reasoning = message.get("reasoning_content")
        return (
            (not isinstance(content, str) or not content.strip())
            and isinstance(reasoning, str)
            and reasoning.strip() != ""
            and first.get("finish_reason") == "length"
        )

    @staticmethod
    def _expanded_retry_max_tokens(max_tokens: int) -> int:
        return min(max(max_tokens * 4, 1024), 4096)

    def _expanded_retry_timeout(self) -> int:
        return min(max(self.timeout * 4, 120), 300)

    def _timeout_for_requested_tokens(self, max_tokens: int) -> int:
        if max_tokens >= 1536:
            return min(max(self.timeout * 6, 180), 300)
        if max_tokens >= 1024:
            return min(max(self.timeout * 4, 120), 300)
        if max_tokens >= 768:
            return min(max(self.timeout * 3, 90), 300)
        return self.timeout

    async def _post_json_with_retries(
        self,
        *,
        url: str,
        request_data: dict,
        headers: dict[str, str] | None,
        context: str,
        timeout: int | None = None,
    ) -> dict:
        async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
            max_attempts = 2
            for attempt in range(1, max_attempts + 1):
                try:
                    response = await client.post(
                        url,
                        json=request_data,
                        headers=headers,
                    )
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    retriable = status in {502, 503, 504}
                    detail = exc.response.text[:500]
                    logger.warning(
                        f"{context} HTTP error",
                        status=status,
                        attempt=attempt,
                        retriable=retriable,
                        response=detail,
                    )
                    if retriable and attempt < max_attempts:
                        await asyncio.sleep(0.6 * attempt)
                        continue
                    raise RuntimeError(
                        f"{context} failed with status {status}: {detail}"
                    ) from exc
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    retriable = attempt < max_attempts
                    logger.warning(
                        f"{context} transport error",
                        attempt=attempt,
                        retriable=retriable,
                        error=str(exc),
                    )
                    if retriable:
                        await asyncio.sleep(0.6 * attempt)
                        continue
                    raise

    async def generate(
        self,
        template: str,
        variables: dict,
        temperature: float | None = None,
        max_tokens: int | None = None
    ) -> GenerationResult:
        """
        Generate text using a prompt template and Ollama.

        Args:
            template: Name of the prompt template (key in PROMPT_TEMPLATES)
                      or a raw prompt string.
            variables: Variables to fill into the template.
            temperature: Sampling temperature (lower = more focused).
            max_tokens: Maximum tokens to generate.

        Returns:
            GenerationResult with the generated text.
        """
        # Resolve template
        if template in PROMPT_TEMPLATES:
            prompt = PROMPT_TEMPLATES[template].format(**variables)
            template_name = template
        else:
            prompt = template.format(**variables)
            template_name = "custom"
        
        # For general_qa, detect language and add explicit instruction
        if template_name == "general_qa" and "query" in variables:
            user_query = variables["query"]
            # Simple language detection based on common words
            if any(word in user_query.lower() for word in ["chi", "cosa", "come", "quando", "dove", "perché", "descrivi", "spiega"]):
                # Italian detected - add strong Italian instruction
                prompt = f"<|im_start|>system\nSei un assistente AI. Devi rispondere SEMPRE in ITALIANO.<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
            else:
                # Default to English
                prompt = f"<|im_start|>system\nYou are an AI assistant. Always respond in the same language as the user's question.<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"

        logger.debug("Generating with LLM", model=self.model, template=template_name)

        # Resolve runtime params from settings overrides
        max_tokens = max_tokens or getattr(settings, "llama_max_tokens", 256)
        temperature = temperature if temperature is not None else getattr(settings, "llama_temperature", 0.3)
        stop_tokens = getattr(settings, "llama_stop_tokens", "</s>,<|im_end|>,<|endoftext|>")
        stop_tokens = [s.strip() for s in stop_tokens.split(",") if s.strip()] or ["</s>", "<|im_end|>", "<|endoftext|>"]
        request_timeout = self._timeout_for_requested_tokens(max_tokens)

        # OpenRouter / OpenAI-compatible chat API
        if self.provider == "openrouter":
            request_data = self._build_openrouter_payload(
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                stop_tokens=stop_tokens,
                stream=False,
            )

            data = await self._post_json_with_retries(
                url=f"{self.base_url}/chat/completions",
                request_data=request_data,
                headers=self._request_headers(),
                context="OpenRouter generation",
                timeout=request_timeout,
            )
            if self._should_retry_empty_openai_response(data):
                retry_max_tokens = self._expanded_retry_max_tokens(max_tokens)
                logger.info(
                    "Retrying OpenRouter generation with higher token budget",
                    previous_max_tokens=max_tokens,
                    retry_max_tokens=retry_max_tokens,
                )
                data = await self._post_json_with_retries(
                    url=f"{self.base_url}/chat/completions",
                    request_data=self._build_openrouter_payload(
                        prompt=prompt,
                        temperature=temperature,
                        max_tokens=retry_max_tokens,
                        stop_tokens=stop_tokens,
                        stream=False,
                    ),
                    headers=self._request_headers(),
                    context="OpenRouter generation retry",
                    timeout=max(
                        self._expanded_retry_timeout(),
                        self._timeout_for_requested_tokens(retry_max_tokens),
                    ),
                )

            prompt_tokens, completion_tokens = self._extract_usage(data)

            result = GenerationResult(
                text=self._extract_generated_text(data).strip(),
                model=self.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                template_used=template_name,
            )
        elif self._uses_openai_compatible_chat_api():
            request_data = self._build_openrouter_payload(
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                stop_tokens=stop_tokens,
                stream=False,
            )
            target_url = self._openai_chat_url()

            logger.debug(
                "Sending request to OpenAI-compatible chat server",
                url=target_url,
                prompt_len=len(prompt),
                max_tokens=max_tokens,
            )

            data = await self._post_json_with_retries(
                url=target_url,
                request_data=request_data,
                headers=self._request_headers(),
                context="OpenAI-compatible chat generation",
                timeout=request_timeout,
            )
            if self._should_retry_empty_openai_response(data):
                retry_max_tokens = self._expanded_retry_max_tokens(max_tokens)
                logger.info(
                    "Retrying OpenAI-compatible chat generation with higher token budget",
                    url=target_url,
                    previous_max_tokens=max_tokens,
                    retry_max_tokens=retry_max_tokens,
                )
                data = await self._post_json_with_retries(
                    url=target_url,
                    request_data=self._build_openrouter_payload(
                        prompt=prompt,
                        temperature=temperature,
                        max_tokens=retry_max_tokens,
                        stop_tokens=stop_tokens,
                        stream=False,
                    ),
                    headers=self._request_headers(),
                    context="OpenAI-compatible chat generation retry",
                    timeout=max(
                        self._expanded_retry_timeout(),
                        self._timeout_for_requested_tokens(retry_max_tokens),
                    ),
                )

            prompt_tokens, completion_tokens = self._extract_usage(data)

            result = GenerationResult(
                text=self._extract_generated_text(data).strip(),
                model=self.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                template_used=template_name,
            )
        elif self._uses_openai_compatible_completions_api():
            request_data = self._build_openai_completion_payload(
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                stop_tokens=stop_tokens,
                stream=False,
            )
            target_url = self._openai_completion_url()

            logger.debug(
                "Sending request to OpenAI-compatible completion server",
                url=target_url,
                prompt_len=len(prompt),
                max_tokens=max_tokens,
            )

            data = await self._post_json_with_retries(
                url=target_url,
                request_data=request_data,
                headers=self._request_headers(),
                context="OpenAI-compatible completion generation",
                timeout=request_timeout,
            )
            if self._should_retry_empty_openai_response(data):
                retry_max_tokens = self._expanded_retry_max_tokens(max_tokens)
                logger.info(
                    "Retrying OpenAI-compatible completion generation with higher token budget",
                    url=target_url,
                    previous_max_tokens=max_tokens,
                    retry_max_tokens=retry_max_tokens,
                )
                data = await self._post_json_with_retries(
                    url=target_url,
                    request_data=self._build_openai_completion_payload(
                        prompt=prompt,
                        temperature=temperature,
                        max_tokens=retry_max_tokens,
                        stop_tokens=stop_tokens,
                        stream=False,
                    ),
                    headers=self._request_headers(),
                    context="OpenAI-compatible completion generation retry",
                    timeout=max(
                        self._expanded_retry_timeout(),
                        self._timeout_for_requested_tokens(retry_max_tokens),
                    ),
                )

            prompt_tokens, completion_tokens = self._extract_usage(data)

            result = GenerationResult(
                text=self._extract_generated_text(data).strip(),
                model=self.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                template_used=template_name,
            )
        # Check if using llama.cpp (OpenAI-compatible) or Ollama
        elif "/v1" in self.base_url:
            # Internal llama.cpp server - use /completion endpoint.
            request_data = {
                "prompt": prompt,
                "n_predict": max_tokens,
                "temperature": temperature,
                "stop": stop_tokens,
            }
            target_url = self._legacy_llama_completion_url()

            logger.debug(
                "Sending request to llama server",
                url=target_url,
                prompt_len=len(prompt),
                n_predict=max_tokens,
            )

            data = await self._post_json_with_retries(
                url=target_url,
                request_data=request_data,
                headers=None,
                context="Llama server",
                timeout=request_timeout,
            )
            
            prompt_tokens, completion_tokens = self._extract_usage(data)

            result = GenerationResult(
                text=self._extract_generated_text(data).strip(),
                model=self.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                template_used=template_name,
            )
        else:
            # Ollama API
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,
                        },
                    },
                )
                response.raise_for_status()
                data = response.json()

            result = GenerationResult(
                text=data.get("response", "").strip(),
                model=self.model,
                prompt_tokens=data.get("prompt_eval_count"),
                completion_tokens=data.get("eval_count"),
                template_used=template_name,
            )

        logger.info(
            "Generation complete",
            template=template_name,
            output_len=len(result.text),
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        )

        return result

    async def generate_stream(
        self,
        template: str,
        variables: dict,
        temperature: float | None = None,
        max_tokens: int | None = None
    ) -> AsyncIterator[str]:
        """
        Generate text with streaming response.

        Yields tokens as they are generated by the LLM.
        """
        # Resolve template
        if template in PROMPT_TEMPLATES:
            prompt = PROMPT_TEMPLATES[template].format(**variables)
            template_name = template
        else:
            prompt = template.format(**variables)
            template_name = "custom"

        logger.debug("Streaming generation", model=self.model, template=template_name)

        # Resolve runtime params from settings overrides
        max_tokens = max_tokens or getattr(settings, "llama_max_tokens", 256)
        temperature = temperature if temperature is not None else getattr(settings, "llama_temperature", 0.3)
        stop_tokens = getattr(settings, "llama_stop_tokens", "</s>,<|im_end|>,<|endoftext|>")
        stop_tokens = [s.strip() for s in stop_tokens.split(",") if s.strip()] or ["</s>", "<|im_end|>", "<|endoftext|>"]
        stream_timeout = self._timeout_for_requested_tokens(max_tokens)

        # OpenRouter / OpenAI-compatible chat API
        if self.provider == "openrouter":
            async with httpx.AsyncClient(timeout=stream_timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=self._build_openrouter_payload(
                        prompt=prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stop_tokens=stop_tokens,
                        stream=True,
                    ),
                    headers=self._request_headers(),
                ) as response:
                    self._raise_for_status_with_body(
                        response,
                        context="OpenRouter streaming generation",
                    )
                    async for line in response.aiter_lines():
                        chunk = self._parse_stream_line(line)
                        if not chunk:
                            continue
                        if chunk.get("done"):
                            break

                        token, done = self._extract_stream_text_and_done(chunk)
                        if token:
                            yield token
                        if done:
                            break
        elif self._uses_openai_compatible_chat_api():
            async with httpx.AsyncClient(timeout=stream_timeout) as client:
                async with client.stream(
                    "POST",
                    self._openai_chat_url(),
                    json=self._build_openrouter_payload(
                        prompt=prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stop_tokens=stop_tokens,
                        stream=True,
                    ),
                    headers=self._request_headers(),
                ) as response:
                    self._raise_for_status_with_body(
                        response,
                        context="OpenAI-compatible chat streaming generation",
                    )
                    async for line in response.aiter_lines():
                        chunk = self._parse_stream_line(line)
                        if not chunk:
                            continue
                        if chunk.get("done"):
                            break

                        token, done = self._extract_stream_text_and_done(chunk)
                        if token:
                            yield token
                        if done:
                            break
        elif self._uses_openai_compatible_completions_api():
            async with httpx.AsyncClient(timeout=stream_timeout) as client:
                async with client.stream(
                    "POST",
                    self._openai_completion_url(),
                    json=self._build_openai_completion_payload(
                        prompt=prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stop_tokens=stop_tokens,
                        stream=True,
                    ),
                    headers=self._request_headers(),
                ) as response:
                    self._raise_for_status_with_body(
                        response,
                        context="OpenAI-compatible completion streaming generation",
                    )
                    async for line in response.aiter_lines():
                        chunk = self._parse_stream_line(line)
                        if not chunk:
                            continue
                        if chunk.get("done"):
                            break

                        token, done = self._extract_stream_text_and_done(chunk)
                        if token:
                            yield token
                        if done:
                            break
        # Check if using llama.cpp or Ollama
        elif "/v1" in self.base_url:
            async with httpx.AsyncClient(timeout=stream_timeout) as client:
                async with client.stream(
                    "POST",
                    self._legacy_llama_completion_url(),
                    json={
                        "prompt": prompt,
                        "n_predict": max_tokens,
                        "temperature": temperature,
                        "stream": True,
                        "stop": stop_tokens,
                    },
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        chunk = self._parse_stream_line(line)
                        if not chunk:
                            continue
                        if chunk.get("done"):
                            break

                        token, done = self._extract_stream_text_and_done(chunk)
                        if token:
                            yield token
                        if done:
                            break
        else:
            # Ollama API
            async with httpx.AsyncClient(timeout=stream_timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": True,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,
                        },
                    },
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        chunk = self._parse_stream_line(line)
                        if not chunk:
                            continue
                        if chunk.get("done"):
                            break

                        token = chunk.get("response", "")
                        if token:
                            yield token
                        if chunk.get("done", False):
                            break

    async def check_health(self) -> bool:
        """Check if the LLM server is running and the model is available."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Check if using OpenRouter
                if self.provider == "openrouter":
                    response = await client.get(
                        f"{self.base_url}/models",
                        headers=self._request_headers(),
                    )
                    response.raise_for_status()
                    return True
                if self._uses_openai_compatible_chat_api() or self._uses_openai_compatible_completions_api():
                    response = await client.get(
                        f"{self._openai_compatible_root_url()}/models",
                        headers=self._request_headers(),
                    )
                    response.raise_for_status()
                    return True
                # Check if using llama.cpp (OpenAI-compatible) or Ollama
                if "/v1" in self.base_url:
                    # llama.cpp with OpenAI-compatible API
                    response = await client.get(f"{self.base_url}/models")
                    response.raise_for_status()
                    return True
                else:
                    # Ollama API
                    response = await client.get(f"{self.base_url}/api/tags")
                    response.raise_for_status()
                    models = response.json().get("models", [])
                    available = [m["name"] for m in models]
                    if self.model in available:
                        return True
                    logger.warning(
                        "Model not found in Ollama",
                        model=self.model,
                        available=available,
                    )
                    return False
        except Exception as e:
            logger.error("LLM health check failed", error=str(e))
            return False

    async def ensure_model(self):
        """Pull the model if it's not already available."""
        if self.provider == "openrouter" or "/v1" in self.base_url:
            return
        if await self.check_health():
            return

        logger.info("Pulling model from Ollama", model=self.model)
        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/pull",
                json={"name": self.model},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.strip():
                        data = json.loads(line)
                        status = data.get("status", "")
                        if "pulling" in status:
                            logger.debug("Pulling model", status=status)

        logger.info("Model pulled successfully", model=self.model)
