#!/usr/bin/env python3
"""Embedding provider helper for USS TJR semantic retrieval."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


DEFAULT_PROVIDER = "mistral"
DEFAULT_OLLAMA_MODEL = "nomic-embed-text"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MISTRAL_EMBEDDING_MODEL = "mistral-embed"
DEFAULT_MISTRAL_BASE_URL = "https://api.mistral.ai/v1"


class EmbeddingError(RuntimeError):
    """Raised when embedding generation fails."""


class EmbeddingClient:
    def __init__(self) -> None:
        self.provider = os.environ.get("EMBEDDING_PROVIDER", DEFAULT_PROVIDER).strip().lower()
        if self.provider == "ollama":
            self.model = os.environ.get("OLLAMA_EMBEDDING_MODEL", DEFAULT_OLLAMA_MODEL)
            self.base_url = os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/")
            self.api_key = ""
            return
        if self.provider == "mistral":
            self.api_key = os.environ.get("MISTRAL_API_KEY", "")
            self.model = os.environ.get("MISTRAL_EMBEDDING_MODEL", DEFAULT_MISTRAL_EMBEDDING_MODEL)
            self.base_url = os.environ.get("MISTRAL_BASE_URL", DEFAULT_MISTRAL_BASE_URL).rstrip("/")
            if not self.api_key:
                raise EmbeddingError("Set MISTRAL_API_KEY before generating Mistral embeddings.")
            return
        raise EmbeddingError("Set EMBEDDING_PROVIDER to 'mistral' or 'ollama'.")

    def create(self, inputs: list[str]) -> list[list[float]]:
        if self.provider == "ollama":
            return [self._create_ollama(text) for text in inputs]
        return self._create_openai(inputs)

    def _create_ollama(self, text: str) -> list[float]:
        payload = json.dumps({"model": self.model, "prompt": text}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/embeddings",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8")
            raise EmbeddingError(f"Ollama embedding request failed: {error.code} {detail}") from error
        except urllib.error.URLError as error:
            raise EmbeddingError(f"Ollama embedding request failed: {error.reason}") from error
        embedding = body.get("embedding")
        if not embedding:
            raise EmbeddingError(f"Ollama response did not include an embedding for model {self.model}.")
        return embedding

    def _create_openai(self, inputs: list[str]) -> list[list[float]]:
        payload = json.dumps({"model": self.model, "input": inputs}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/embeddings",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8")
            raise EmbeddingError(f"Embedding request failed: {error.code} {detail}") from error
        data: list[dict[str, Any]] = body.get("data", [])
        data.sort(key=lambda item: item["index"])
        return [item["embedding"] for item in data]

    def create_one(self, text: str) -> list[float]:
        return self.create([text])[0]

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"
