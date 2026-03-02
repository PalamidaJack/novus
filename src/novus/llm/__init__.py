"""
LLM Client for NOVUS.

Unified interface for multiple LLM providers with API key management.
"""

from __future__ import annotations

import os
import asyncio
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
from pathlib import Path
import yaml

import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class LLMRequest:
    """LLM request parameters."""
    messages: List[Dict[str, str]]
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 1024
    stream: bool = False
    
    @classmethod
    def from_prompt(cls, prompt: str, **kwargs) -> "LLMRequest":
        """Create request from single prompt."""
        return cls(
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )


@dataclass
class LLMResponse:
    """LLM response."""
    content: str
    model: str
    usage: Dict[str, int]
    finish_reason: Optional[str] = None


class LLMProvider(ABC):
    """Abstract LLM provider."""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient()
        return self
    
    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
    
    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send completion request."""
        pass
    
    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Stream completion."""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        super().__init__(
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1"
        )
    
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send OpenAI completion request."""
        if not self._client:
            self._client = httpx.AsyncClient()
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens
        }
        
        try:
            response = await self._client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()
            
            return LLMResponse(
                content=data["choices"][0]["message"]["content"],
                model=data["model"],
                usage=data.get("usage", {}),
                finish_reason=data["choices"][0].get("finish_reason")
            )
        except httpx.HTTPError as e:
            logger.error("openai_request_failed", error=str(e))
            raise
    
    async def stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Stream OpenAI completion."""
        if not self._client:
            self._client = httpx.AsyncClient()
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True
        }
        
        try:
            async with self._client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60.0
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        # Parse SSE data
                        import json
                        try:
                            chunk = json.loads(data)
                            if chunk["choices"]:
                                delta = chunk["choices"][0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                        except json.JSONDecodeError:
                            continue
        except httpx.HTTPError as e:
            logger.error("openai_stream_failed", error=str(e))
            raise


class AnthropicProvider(LLMProvider):
    """Anthropic API provider."""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        super().__init__(
            api_key=api_key,
            base_url=base_url or "https://api.anthropic.com/v1"
        )
    
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send Anthropic completion request."""
        if not self._client:
            self._client = httpx.AsyncClient()
        
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        # Convert messages to Anthropic format
        system_msg = ""
        user_messages = []
        for msg in request.messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                user_messages.append(msg)
        
        payload = {
            "model": request.model,
            "messages": user_messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature
        }
        if system_msg:
            payload["system"] = system_msg
        
        try:
            response = await self._client.post(
                f"{self.base_url}/messages",
                headers=headers,
                json=payload,
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()
            
            return LLMResponse(
                content=data["content"][0]["text"],
                model=data["model"],
                usage={
                    "prompt_tokens": data["usage"]["input_tokens"],
                    "completion_tokens": data["usage"]["output_tokens"],
                    "total_tokens": data["usage"]["input_tokens"] + data["usage"]["output_tokens"]
                },
                finish_reason=data.get("stop_reason")
            )
        except httpx.HTTPError as e:
            logger.error("anthropic_request_failed", error=str(e))
            raise
    
    async def stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Stream Anthropic completion."""
        # Similar to OpenAI but Anthropic-specific format
        yield "[Streaming not yet implemented for Anthropic]"


class LLMClient:
    """Unified LLM client with provider selection."""

    PROVIDERS = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "openrouter": OpenAIProvider,
        "kilo": OpenAIProvider,
    }

    PROVIDER_BASE_URLS = {
        "openrouter": "https://openrouter.ai/api/v1",
        "kilo": "https://api.kilo.ai/api/gateway",
    }

    DEFAULT_MODELS = {
        "openai": "gpt-4",
        "anthropic": "claude-3-opus-20240229",
        "openrouter": "openai/gpt-4",
        "kilo": "kilo/auto",
    }
    
    def __init__(
        self,
        provider: str = "openai",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        enable_prompt_cache: bool = True,
    ):
        self.provider_name = provider.lower()
        self.model = model or self.DEFAULT_MODELS.get(self.provider_name, "gpt-4")
        self.enable_prompt_cache = enable_prompt_cache
        self._prompt_cache: Dict[str, str] = {}
        
        # Get API key
        self.api_key = api_key or self._load_api_key(provider)
        
        if not self.api_key:
            raise ValueError(
                f"No API key found for {provider}. "
                f"Set {provider.upper()}_API_KEY environment variable "
                f"or run 'novus onboard' to configure."
            )
        
        # Initialize provider
        provider_class = self.PROVIDERS.get(self.provider_name)
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider}")

        effective_url = base_url or self.PROVIDER_BASE_URLS.get(self.provider_name)
        self.provider = provider_class(self.api_key, effective_url)
        
        logger.info(
            "llm_client_initialized",
            provider=provider,
            model=self.model
        )
    
    def _load_api_key(self, provider: str) -> Optional[str]:
        """Load API key from environment or config."""
        # Try environment variable first
        env_var = f"{provider.upper()}_API_KEY"
        key = os.environ.get(env_var)
        if key:
            return key
        
        # Try config file
        config_path = Path.home() / ".novus" / "api-keys.yaml"
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = yaml.safe_load(f)
                if config and provider in config:
                    return config[provider]
            except Exception:
                pass
        
        return None
    
    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> str:
        """Simple completion interface."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        cache_key = self._cache_key(messages, temperature, max_tokens)
        if self.enable_prompt_cache and cache_key in self._prompt_cache:
            return self._prompt_cache[cache_key]
        
        request = LLMRequest(
            messages=messages,
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        async with self.provider:
            response = await self.provider.complete(request)
            if self.enable_prompt_cache:
                self._prompt_cache[cache_key] = response.content
            return response.content
    
    async def stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> AsyncGenerator[str, None]:
        """Stream completion."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        request = LLMRequest(
            messages=messages,
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True
        )
        
        async with self.provider:
            async for chunk in self.provider.stream(request):
                yield chunk
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> str:
        """Chat completion with message history."""
        cache_key = self._cache_key(messages, temperature, max_tokens)
        if self.enable_prompt_cache and cache_key in self._prompt_cache:
            return self._prompt_cache[cache_key]
        request = LLMRequest(
            messages=messages,
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        async with self.provider:
            response = await self.provider.complete(request)
            if self.enable_prompt_cache:
                self._prompt_cache[cache_key] = response.content
            return response.content

    def _cache_key(self, messages: List[Dict[str, str]], temperature: float, max_tokens: int) -> str:
        payload = {
            "provider": self.provider_name,
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        blob = str(payload).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()


# Global client cache
_client_cache: Dict[str, LLMClient] = {}


def get_llm_client(
    provider: str = "openai",
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> LLMClient:
    """Get or create LLM client."""
    cache_key = f"{provider}:{model or 'default'}"
    
    if cache_key not in _client_cache:
        _client_cache[cache_key] = LLMClient(
            provider=provider,
            api_key=api_key,
            model=model
        )
    
    return _client_cache[cache_key]


def clear_llm_cache():
    """Clear LLM client cache."""
    _client_cache.clear()
