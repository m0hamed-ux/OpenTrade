"""Gemini API client wrapper with retry logic."""

import asyncio
from typing import Any

from google import genai
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from config.logging_config import get_logger

logger = get_logger(__name__)


class GeminiError(Exception):
    """Base exception for Gemini API errors."""
    pass


class GeminiRateLimitError(GeminiError):
    """Rate limit exceeded."""
    pass


class GeminiClient:
    """Gemini API wrapper with retry logic and structured output support."""

    def __init__(self, api_key: str):
        """Initialize Gemini client.

        Args:
            api_key: Google Gemini API key
        """
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
        self._lock = asyncio.Lock()

    @retry(
        retry=retry_if_exception_type((GeminiRateLimitError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
    )
    async def generate(
        self,
        prompt: str,
        model_name: str = "gemini-2.0-flash-exp",
        system_instruction: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: str = "json",
    ) -> str:
        """Generate a response from Gemini.

        Args:
            prompt: User prompt
            model_name: Model to use
            system_instruction: System prompt
            temperature: Sampling temperature
            max_tokens: Maximum output tokens
            response_format: "json" or "text"

        Returns:
            Generated response text
        """
        config = genai.types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
        )

        if response_format == "json":
            config.response_mime_type = "application/json"

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
            )

            if response.prompt_feedback and response.prompt_feedback.block_reason:
                raise GeminiError(
                    f"Prompt blocked: {response.prompt_feedback.block_reason}"
                )

            return response.text

        except Exception as e:
            error_str = str(e).lower()
            if "rate limit" in error_str or "quota" in error_str:
                logger.warning("Gemini rate limit hit, retrying...", error=str(e))
                raise GeminiRateLimitError(str(e))
            logger.error("Gemini API error", error=str(e))
            raise GeminiError(str(e))

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        model_name: str = "gemini-2.0-flash-exp",
        system_instruction: str | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """Generate a response with function calling support.

        Args:
            prompt: User prompt
            tools: List of tool definitions
            model_name: Model to use
            system_instruction: System prompt
            temperature: Sampling temperature

        Returns:
            Dict with 'text' and/or 'function_calls'
        """
        # Convert tool definitions to Gemini format
        gemini_tools = []
        for tool in tools:
            gemini_tools.append({
                "function_declarations": [{
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool.get("parameters", {}),
                }]
            })

        config = genai.types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            tools=gemini_tools,
        )

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
            )

            result = {"text": None, "function_calls": []}

            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    result["text"] = part.text
                if hasattr(part, "function_call"):
                    result["function_calls"].append({
                        "name": part.function_call.name,
                        "args": dict(part.function_call.args),
                    })

            return result

        except Exception as e:
            error_str = str(e).lower()
            if "rate limit" in error_str or "quota" in error_str:
                raise GeminiRateLimitError(str(e))
            raise GeminiError(str(e))

    async def count_tokens(self, text: str, model_name: str = "gemini-2.0-flash-exp") -> int:
        """Count tokens in text.

        Args:
            text: Text to count tokens for
            model_name: Model to use for tokenization

        Returns:
            Token count
        """
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.client.models.count_tokens(
                model=model_name,
                contents=text,
            )
        )

        return result.total_tokens
