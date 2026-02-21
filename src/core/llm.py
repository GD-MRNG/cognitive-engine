import logging
import os
from abc import ABC, abstractmethod
from typing import Dict, Any

import openai
from langchain_community.llms import Ollama
import google.generativeai as genai

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    @abstractmethod
    def query(self, prompt: str, model: str = "default") -> str:
        pass


class MockLLMClient(BaseLLMClient):
    """Simulates response for testing."""

    def query(self, prompt: str, model: str = "default") -> str:
        logger.info(f"[MockLLM] Processing prompt with model '{model}'...")
        if "summar" in prompt.lower():
            return f"[[Mock Summary ({model})]]: The text discusses key concepts X, Y, Z..."
        return f"[[Mock Response ({model})]]: Action completed successfully."


class ProductionLLMClient(BaseLLMClient):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.provider = config.get("provider", "poe").lower()

        if self.provider == "poe":
            api_key = os.getenv("POE_API_KEY")
            if not api_key:
                logger.warning("POE_API_KEY not found in environment variables.")

            self.client = openai.OpenAI(
                api_key=api_key, base_url="https://api.poe.com/v1"
            )

        elif self.provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                logger.error("GEMINI_API_KEY not found in environment variables.")
                raise ValueError("Missing GEMINI_API_KEY")
            genai.configure(api_key=api_key)

        # Setup Ollama (No Auth needed for local)
        elif self.provider == "ollama":
            # We don't need persistent client for LangChain Ollama, we instantiate per call
            pass

    def query(self, prompt: str, model: str = "default") -> str:
        try:
            if self.provider == "poe":
                return self._query_poe(prompt, model)
            elif self.provider == "gemini":
                return self._query_gemini(prompt, model)
            elif self.provider == "ollama":
                return self._query_ollama(prompt, model)
            else:
                raise ValueError(f"Unknown provider: {self.provider}")
        except Exception as e:
            logger.error(f"LLM Query Failed ({self.provider}/{model}): {e}")
            return f"[Error: {e}]"

    def _query_poe(self, prompt: str, model: str) -> str:
        # Default to a safe model if 'default' is passed
        target_model = model if model != "default" else "Gemini-2.5-Flash"

        logger.info(f"Querying Poe API with model: {target_model}")
        response = self.client.chat.completions.create(
            model=target_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,  # Deterministic
        )
        return self._clean_llm_output(response.choices[0].message.content)

    def _query_gemini(self, prompt: str, model: str) -> str:
        # Default to Flash if not specified
        target_model = model if model != "default" else "gemini-2.5-flash"

        logger.info(f"Querying Google Gemini with model: {target_model}")
        model_instance = genai.GenerativeModel(target_model)
        response = model_instance.generate_content(prompt)
        return self._clean_llm_output(response.text)

    def _query_ollama(self, prompt: str, model: str) -> str:
        target_model = model if model != "default" else "qwen2.5:14b"

        logger.info(f"Querying Local Ollama with model: {target_model}")
        llm = Ollama(model=target_model, temperature=0.0)
        return llm.invoke(prompt)

    def _clean_llm_output(self, text: str) -> str:
        """
        Removes meta-commentary, 'thinking' lines, and blockquotes from the LLM output.
        Target patterns:
        - "*Thinking...*"
        - "> Blockquoted thought process"
        """
        if not text:
            return ""

        lines = text.splitlines()
        cleaned_lines = []

        for line in lines:
            stripped = line.strip()

            # Filter out blockquotes (standard CoT format for some models)
            if stripped.startswith(">"):
                continue

            # Filter out italicized thinking markers (e.g. *Thinking...*)
            if stripped.lower().startswith("*thinking"):
                continue

            cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()


def get_llm_client(config: Dict[str, Any]) -> BaseLLMClient:
    # Check if 'mock' is explicitly requested in the step config
    if config.get("provider") == "mock":
        return MockLLMClient()

    # Otherwise, check environment mode or default to Production
    return ProductionLLMClient(config)
