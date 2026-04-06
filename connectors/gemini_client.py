"""Gemini API client wrapper with retry logic."""

import asyncio
from typing import Any

import google.generativeai as genai
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
        genai.configure(api_key=api_key)
        self._models: dict[str, genai.GenerativeModel] = {}
        self._lock = asyncio.Lock()

    def _get_model(
        self,
        model_name: str,
        system_instruction: str | None = None,
        tools: list[dict] | None = None,
    ) -> genai.GenerativeModel:
        """Get or create a Gemini model instance.

        Args:
            model_name: Model identifier (e.g., "gemini-2.5-pro")
            system_instruction: System prompt for the model
            tools: Function calling tools

        Returns:
            GenerativeModel instance
        """
        cache_key = f"{model_name}:{hash(system_instruction or '')}:{hash(str(tools or []))}"

        if cache_key not in self._models:
            config = {}
            if system_instruction:
                config["system_instruction"] = system_instruction

            model = genai.GenerativeModel(
                model_name=model_name,
                **config,
            )
            self._models[cache_key] = model

        return self._models[cache_key]

    @retry(
        retry=retry_if_exception_type((GeminiRateLimitError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
    )
    async def generate(
        self,
        prompt: str,
        model_name: str = "gemini-2.5-pro",
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
        model = self._get_model(model_name, system_instruction)

        generation_config = genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        if response_format == "json":
            generation_config.response_mime_type = "application/json"

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: model.generate_content(
                    prompt,
                    generation_config=generation_config,
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
        model_name: str = "gemini-2.5-pro",
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
        model = self._get_model(model_name, system_instruction)

        generation_config = genai.GenerationConfig(
            temperature=temperature,
        )

        # Convert tool definitions to Gemini format
        gemini_tools = []
        for tool in tools:
            gemini_tools.append(genai.protos.Tool(
                function_declarations=[
                    genai.protos.FunctionDeclaration(
                        name=tool["name"],
                        description=tool["description"],
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                k: genai.protos.Schema(
                                    type=self._map_type(v.get("type", "string")),
                                    description=v.get("description", ""),
                                )
                                for k, v in tool.get("parameters", {}).get("properties", {}).items()
                            },
                            required=tool.get("parameters", {}).get("required", []),
                        ),
                    )
                ]
            ))

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: model.generate_content(
                    prompt,
                    generation_config=generation_config,
                    tools=gemini_tools,
                )
            )

            result = {"text": None, "function_calls": []}

            for part in response.parts:
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

    def _map_type(self, type_str: str) -> int:
        """Map JSON schema type to Gemini proto type."""
        type_map = {
            "string": genai.protos.Type.STRING,
            "number": genai.protos.Type.NUMBER,
            "integer": genai.protos.Type.INTEGER,
            "boolean": genai.protos.Type.BOOLEAN,
            "array": genai.protos.Type.ARRAY,
            "object": genai.protos.Type.OBJECT,
        }
        return type_map.get(type_str, genai.protos.Type.STRING)

    async def count_tokens(self, text: str, model_name: str = "gemini-2.5-pro") -> int:
        """Count tokens in text.

        Args:
            text: Text to count tokens for
            model_name: Model to use for tokenization

        Returns:
            Token count
        """
        model = self._get_model(model_name)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: model.count_tokens(text)
        )

        return result.total_tokens
