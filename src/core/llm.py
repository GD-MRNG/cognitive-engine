import logging
import os
import time
import re
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
    DEFAULT_POE_MODEL = "gemini-3-flash"
    DEFAULT_GEMINI_MODEL = "gemini-3-flash"
    DEFAULT_OLLAMA_MODEL = "qwen2.5:14b"
    DEFAULT_FALLBACK_MODEL = "deepseek-r1:8b"

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.provider = config.get("provider", "poe").lower()

        self.max_retries = config.get("max_retries", 2)
        self.base_delay = config.get("retry_delay", 2)
        self.fallback_enabled = config.get("fallback_enabled", True)

        # Use class constant for fallback default
        self.fallback_model = config.get("fallback_model", self.DEFAULT_FALLBACK_MODEL)

        # Block Patterns: Regexes to remove entire chunks (multiline)
        self.cleaning_block_patterns = [
            r"<think>.*?</think>",
            r"<thought>.*?</thought>",
            r"\[Thinking:.*?\]",
            r"Thinking.*?...done thinking.",
        ]

        # Line Prefixes: Remove lines starting with these (case-insensitive)
        self.cleaning_line_prefixes = [
            ">",
            "*thinking",
            "thinking:",
        ]

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

        elif self.provider == "ollama":
            pass

    def query(self, prompt: str, model: str = "default") -> str:
        """
        Orchestrates the query with:
        1. Mandatory cooldown (Rate Limit protection).
        2. Primary Provider attempt with Exponential Backoff.
        3. Hot Fallback to Local LLM if Primary fails.
        """

        time.sleep(1.0)  # Mandatory Cooldown

        try:
            return self._execute_with_retry(
                provider_func=self._query_primary_provider,
                prompt=prompt,
                model=model,
                retries=self.max_retries,
                provider_name=self.provider,
            )
        except Exception as e:
            logger.error(
                f"Primary Provider ({self.provider}) failed after retries: {e}"
            )

            if self.fallback_enabled and self.provider != "ollama":
                logger.warning(
                    f"⚠️ Initiating Hot Fallback to Local Ollama ({self.fallback_model})..."
                )
                try:
                    return self._execute_with_retry(
                        provider_func=self._query_ollama,
                        prompt=prompt,
                        model=self.fallback_model,
                        retries=2,
                        provider_name="ollama-fallback",
                    )
                except Exception as fallback_error:
                    logger.critical(f"Fallback failed: {fallback_error}")

            return f"[Error: All LLM providers failed. Primary: {e}]"

    def _execute_with_retry(self, provider_func, prompt, model, retries, provider_name):
        last_exception = None
        for attempt in range(1, retries + 1):
            try:
                if attempt > 1:
                    logger.info(
                        f"Retry attempt {attempt}/{retries} for {provider_name}..."
                    )
                return provider_func(prompt, model)
            except Exception as e:
                last_exception = e
                logger.warning(f"Attempt {attempt} failed for {provider_name}: {e}")
                if attempt < retries:
                    sleep_time = self.base_delay * (2 ** (attempt - 1))
                    time.sleep(sleep_time)
        raise last_exception

    def _query_primary_provider(self, prompt: str, model: str) -> str:
        if self.provider == "poe":
            return self._query_poe(prompt, model)
        elif self.provider == "gemini":
            return self._query_gemini(prompt, model)
        elif self.provider == "ollama":
            return self._query_ollama(prompt, model)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def _query_poe(self, prompt: str, model: str) -> str:
        target_model = model if model != "default" else self.DEFAULT_POE_MODEL
        logger.info(f"Querying Poe API with model: {target_model}")
        response = self.client.chat.completions.create(
            model=target_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        return self._clean_llm_output(response.choices[0].message.content)

    def _query_gemini(self, prompt: str, model: str) -> str:
        target_model = model if model != "default" else self.DEFAULT_GEMINI_MODEL
        logger.info(f"Querying Google Gemini with model: {target_model}")
        model_instance = genai.GenerativeModel(target_model)
        response = model_instance.generate_content(prompt)
        return self._clean_llm_output(response.text)

    def _query_ollama(self, prompt: str, model: str) -> str:
        target_model = model if model != "default" else self.DEFAULT_OLLAMA_MODEL
        logger.info(f"Querying Local Ollama with model: {target_model}")
        llm = Ollama(model=target_model, temperature=0.0)
        return self._clean_llm_output(llm.invoke(prompt))

    def _clean_llm_output(self, text: str) -> str:
        """
        Modular cleaning of LLM output based on configured patterns.
        1. Removes multi-line blocks (regex).
        2. Filters out specific lines (prefixes).
        """
        if not text:
            return ""

        # 1. Block Removal
        # Uses DOTALL so . matches newlines, IGNORECASE for <Think> vs <think>
        for pattern in self.cleaning_block_patterns:
            text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

        # 2. Line Filtering
        lines = text.splitlines()
        cleaned_lines = []

        for line in lines:
            stripped = line.strip().lower()

            # Check if line starts with any forbidden prefix
            if any(
                stripped.startswith(prefix) for prefix in self.cleaning_line_prefixes
            ):
                continue

            cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()


def get_llm_client(config: Dict[str, Any]) -> BaseLLMClient:
    if config.get("provider") == "mock":
        return MockLLMClient()
    return ProductionLLMClient(config)
