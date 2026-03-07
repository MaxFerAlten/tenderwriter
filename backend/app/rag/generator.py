"""
TenderWriter — LLM Generator (Ollama)

Generates text using a local LLM served by Ollama.
Supports multiple prompt templates for different proposal writing tasks
and streaming responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()


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

Provide a helpful, accurate answer based on the available context.
If the context doesn't contain enough information, say so clearly.

RICORDA: Rispondi nella STESSA LINGUA della domanda sopra!

## Answer (in the same language as the question)
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
        timeout: int | None = None,
    ):
        # Use llama_server settings by default, fallback to ollama for backward compatibility
        self.base_url = base_url or getattr(settings, 'llama_server_url', settings.ollama_base_url)
        self.model = model or getattr(settings, 'llama_model', settings.ollama_model)
        self.timeout = timeout or getattr(settings, 'llama_timeout', 120)

    async def generate(
        self,
        template: str,
        variables: dict,
        temperature: float = 0.3,
        max_tokens: int = 512,  # Reduced for faster CPU inference
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

        # Check if using llama.cpp (OpenAI-compatible) or Ollama
        if "/v1" in self.base_url:
            # llama.cpp server - use /completion endpoint (not /v1/chat/completions due to parsing bug)
            base_url_without_v1 = self.base_url.replace("/v1", "")
            
            request_data = {
                "prompt": prompt,
                "n_predict": max_tokens,
                "temperature": temperature,
                "stop": ["</s>", "<|im_end|>", "<|endoftext|>"],
            }
            
            logger.debug("Sending request to llama server", 
                        url=f"{base_url_without_v1}/completion",
                        prompt_len=len(prompt),
                        n_predict=max_tokens)
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                try:
                    response = await client.post(
                        f"{base_url_without_v1}/completion",
                        json=request_data,
                    )
                    response.raise_for_status()
                    data = response.json()
                except httpx.HTTPStatusError as e:
                    logger.error("Llama server error", 
                                status=e.response.status_code,
                                response=e.response.text[:500])
                    raise
            
            result = GenerationResult(
                text=data.get("content", "").strip(),
                model=self.model,
                prompt_tokens=data.get("tokens_evaluated"),
                completion_tokens=data.get("tokens_predicted"),
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
        temperature: float = 0.3,
        max_tokens: int = 512,  # Reduced for faster CPU inference
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

        # Check if using llama.cpp or Ollama
        if "/v1" in self.base_url:
            # llama.cpp server - use /completion endpoint with streaming
            base_url_without_v1 = self.base_url.replace("/v1", "")
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{base_url_without_v1}/completion",
                    json={
                        "prompt": prompt,
                        "n_predict": max_tokens,
                        "temperature": temperature,
                        "stream": True,
                        "stop": ["</s>", "<|im_end|>", "<|endoftext|>"],
                    },
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                import json
                                chunk = json.loads(line)
                                content = chunk.get("content", "")
                                if content:
                                    yield content
                                if chunk.get("stop", False):
                                    break
                            except (json.JSONDecodeError, KeyError):
                                continue
        else:
            # Ollama API
            async with httpx.AsyncClient(timeout=self.timeout) as client:
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
                        if line.strip():
                            import json
                            chunk = json.loads(line)
                            token = chunk.get("response", "")
                            if token:
                                yield token
                            if chunk.get("done", False):
                                break

    async def check_health(self) -> bool:
        """Check if the LLM server is running and the model is available."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
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
                        import json
                        data = json.loads(line)
                        status = data.get("status", "")
                        if "pulling" in status:
                            logger.debug("Pulling model", status=status)

        logger.info("Model pulled successfully", model=self.model)
