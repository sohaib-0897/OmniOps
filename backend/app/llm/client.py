import logging
import httpx
from typing import Dict, Any, List, Optional
from app.llm.base import (
    BaseLLMClient,
    PlanOutput,
    PlannedTask,
    ToolDecision,
    SynthesisReport, ProviderError, ProviderState
)
from app.llm.openai_provider import OpenAIProvider
from app.llm.gemini_provider import GeminiProvider
from app.llm.analytical_provider import AnalyticalProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

class OmniOpsLLMClient(BaseLLMClient):
    """Factory and facade LLM client dynamically delegating to configured model providers."""

    def __init__(self):
        self._provider: BaseLLMClient = self._initialize_provider()
        self.provider_name = self._provider.__class__.__name__
        self.provider_state = ProviderState.AVAILABLE

    def _initialize_provider(self) -> BaseLLMClient:
        provider_mode = (settings.LLM_PROVIDER or "auto").lower()

        if provider_mode == "openai" or (provider_mode == "auto" and settings.OPENAI_API_KEY):
            logger.info("Initializing OpenAI Provider (%s)", settings.OPENAI_MODEL)
            return OpenAIProvider(api_key=settings.OPENAI_API_KEY, model=settings.OPENAI_MODEL)

        elif provider_mode == "gemini" or (provider_mode == "auto" and settings.GEMINI_API_KEY):
            logger.info("Initializing Google Gemini Provider (%s)", settings.GEMINI_MODEL)
            return GeminiProvider(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)

        else:
            logger.info("Initializing Dynamic Analytical Engine (Offline Provider)")
            return AnalyticalProvider()

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
                "SEMANTIC_PROVIDER_FAILED",
                f"{self.provider_name} failed during {operation}; the investigation was stopped.",
            ) from exc

    def provenance(self) -> Dict[str, str]:
        return {"provider": self.provider_name, "state": self.provider_state.value}
