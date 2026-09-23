import logging
from typing import Any, Dict, List

import httpx

from app.llm.base import (
    BaseLLMClient,
    CapabilityLimitError,
    PlanOutput,
    PlannedTask,
    ProviderError,
    ProviderState,
    SynthesisReport,
    ToolDecision,
)
from app.llm.openai_provider import OpenAIProvider
from app.llm.gemini_provider import GeminiProvider
from app.llm.analytical_provider import AnalyticalProvider
from app.llm.ollama_provider import OllamaProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

class OmniOpsLLMClient(BaseLLMClient):
    """Factory and facade LLM client dynamically delegating to configured model providers."""

    def __init__(self):
        self._provider: BaseLLMClient = self._initialize_provider()
        self.provider_name = self._provider.__class__.__name__
        self.provider_state = ProviderState.AVAILABLE

    def _initialize_provider(self) -> BaseLLMClient:
        provider_mode = (settings.LLM_PROVIDER or "").strip().lower()

        if provider_mode == "ollama":
            logger.info("Initializing Ollama Provider (%s)", settings.OLLAMA_MODEL)
            return OllamaProvider(
                base_url=settings.OLLAMA_BASE_URL,
                model=settings.OLLAMA_MODEL,
                timeout_seconds=settings.OLLAMA_TIMEOUT_SECONDS,
                num_ctx=settings.OLLAMA_NUM_CTX,
            )

        if provider_mode == "openai":
            if not settings.OPENAI_API_KEY:
                raise CapabilityLimitError("LLM_PROVIDER=openai requires OPENAI_API_KEY.")
            logger.info("Initializing OpenAI Provider (%s)", settings.OPENAI_MODEL)
            return OpenAIProvider(api_key=settings.OPENAI_API_KEY, model=settings.OPENAI_MODEL)

        if provider_mode == "gemini":
            if not settings.GEMINI_API_KEY:
                raise CapabilityLimitError("LLM_PROVIDER=gemini requires GEMINI_API_KEY.")
            logger.info("Initializing Google Gemini Provider (%s)", settings.GEMINI_MODEL)
            return GeminiProvider(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)

        if provider_mode == "analytical" and settings.ENVIRONMENT.lower() in {"development", "test"}:
            logger.info("Initializing Dynamic Analytical Engine (explicit development/test provider)")
            return AnalyticalProvider()

        raise CapabilityLimitError(
            "Set LLM_PROVIDER explicitly to ollama, gemini, or openai and configure that provider."
        )

    async def readiness(self) -> Dict[str, str]:
        if isinstance(self._provider, OllamaProvider):
            return await self._provider.readiness()
        return {
            "status": "ready",
            "provider": self.provider_name.removesuffix("Provider").lower(),
            "model": getattr(self._provider, "model", "configured"),
        }

    async def generate_investigation_plan(
        self,
        objective: str,
        catalog_summary: Dict[str, Any]
    ) -> PlanOutput:
        return await self._invoke("planning", self._provider.generate_investigation_plan, objective, catalog_summary)

    async def decide_next_action(
        self,
        objective: str,
        current_task: PlannedTask,
        prior_observations: List[Dict[str, Any]],
        available_tools: List[Dict[str, Any]]
    ) -> ToolDecision:
        return await self._invoke("tool_decision", self._provider.decide_next_action, objective, current_task, prior_observations, available_tools)

    async def verify_and_synthesize(
        self,
        objective: str,
        observations: List[Dict[str, Any]],
        evidence_items: List[Dict[str, Any]],
        calculations: List[Dict[str, Any]]
    ) -> SynthesisReport:
        return await self._invoke("synthesis", self._provider.verify_and_synthesize, objective, observations, evidence_items, calculations)

    async def _invoke(self, operation: str, method, *args):
        try:
            result = await method(*args)
            self.provider_state = ProviderState.AVAILABLE
            return result
        except ProviderError as exc:
            self.provider_state = exc.state
            raise
        except (TimeoutError, httpx.TimeoutException) as exc:
            self.provider_state = ProviderState.TIMEOUT
            raise ProviderError(ProviderState.TIMEOUT, "PROVIDER_TIMEOUT", f"{self.provider_name} timed out during {operation}; the investigation was stopped.") from exc
        except Exception as exc:
            self.provider_state = ProviderState.MALFORMED_RESPONSE
            logger.error(
                "%s provider failed during %s (%s)",
                self.provider_name,
                operation,
                type(exc).__name__,
            )
            raise ProviderError(
                ProviderState.MALFORMED_RESPONSE,
                "PROVIDER_RESPONSE_INVALID",
                f"{self.provider_name} failed during {operation}; the investigation was stopped.",
            ) from exc

    def provenance(self) -> Dict[str, str]:
        return {"provider": self.provider_name, "state": self.provider_state.value}
