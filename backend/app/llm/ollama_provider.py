import asyncio
import json
import logging
from typing import Any, Dict, List, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.llm.base import (
    BaseLLMClient,
    PlanOutput,
    PlannedTask,
    ProviderError,
    ProviderState,
    SynthesisReport,
    ToolDecision,
)


StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)
logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMClient):
    """Local Ollama HTTP provider with schema-constrained output validation."""

    MAX_ATTEMPTS = 2
    RETRY_DELAY_SECONDS = 1.0
    WORKER_LEASE_SECONDS = 120.0

    def __init__(self, base_url: str, model: str, timeout_seconds: float = 90.0):
        self.base_url = base_url.rstrip("/")
        self.model = model.strip()
        self.timeout_seconds = float(timeout_seconds)
        if not self.base_url or not self.model:
            raise ProviderError(
                ProviderState.UNAVAILABLE,
                "LLM_PROVIDER_REQUIRED",
                "Ollama requires OLLAMA_BASE_URL and OLLAMA_MODEL.",
            )
        if self.timeout_seconds <= 0 or self.timeout_seconds >= self.WORKER_LEASE_SECONDS:
            raise ProviderError(
                ProviderState.UNAVAILABLE,
                "LLM_PROVIDER_REQUIRED",
                "OLLAMA_TIMEOUT_SECONDS must be greater than zero and below the worker lease duration.",
            )

    async def readiness(self) -> Dict[str, str]:
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout_seconds, 5.0), trust_env=False) as client:
                response = await client.get(f"{self.base_url}/api/tags")
        except httpx.TimeoutException:
            return {"status": "unavailable", "provider": "ollama", "model": self.model, "code": "PROVIDER_TIMEOUT"}
        except httpx.TransportError:
            return {"status": "unavailable", "provider": "ollama", "model": self.model, "code": "PROVIDER_UNAVAILABLE"}

        if response.status_code != 200:
            return {"status": "unavailable", "provider": "ollama", "model": self.model, "code": "PROVIDER_UNAVAILABLE"}
        try:
            body = response.json()
            names = {
                value
                for item in body.get("models", [])
                if isinstance(item, dict)
                for value in (item.get("name"), item.get("model"))
                if isinstance(value, str)
            }
        except (AttributeError, TypeError, ValueError):
            return {"status": "unavailable", "provider": "ollama", "model": self.model, "code": "PROVIDER_RESPONSE_INVALID"}
        if self.model not in names:
            return {"status": "unavailable", "provider": "ollama", "model": self.model, "code": "PROVIDER_MODEL_UNAVAILABLE"}
        return {"status": "ready", "provider": "ollama", "model": self.model}

    async def _structured_chat(
        self,
        *,
        system_instruction: str,
        prompt: str,
        output_model: type[StructuredOutput],
    ) -> StructuredOutput:
        schema = output_model.model_json_schema()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"{prompt}\n\nReturn only JSON matching this schema:\n{json.dumps(schema)}"},
            ],
            "stream": False,
            "format": schema,
            "think": False,
            "options": {"temperature": 0.1},
        }

        logger.info("Ollama request started model=%s operation=%s", self.model, output_model.__name__)
        async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
            for attempt in range(self.MAX_ATTEMPTS):
                try:
                    response = await client.post(f"{self.base_url}/api/chat", json=payload)
                except httpx.TimeoutException as exc:
                    logger.error("Ollama request failed code=PROVIDER_TIMEOUT operation=%s", output_model.__name__)
                    raise ProviderError(ProviderState.TIMEOUT, "PROVIDER_TIMEOUT", "Ollama generation timed out.") from exc
                except httpx.TransportError as exc:
                    if attempt + 1 < self.MAX_ATTEMPTS:
                        logger.warning(
                            "Ollama retry scheduled reason=transport attempt=%s",
                            attempt + 2,
                        )
                        await asyncio.sleep(self.RETRY_DELAY_SECONDS)
                        continue
                    logger.error("Ollama request failed code=PROVIDER_UNAVAILABLE operation=%s", output_model.__name__)
                    raise ProviderError(ProviderState.UNAVAILABLE, "PROVIDER_UNAVAILABLE", "Ollama is unavailable.") from exc

                if response.status_code == 404:
                    logger.error("Ollama request failed code=PROVIDER_MODEL_UNAVAILABLE operation=%s", output_model.__name__)
                    raise ProviderError(
                        ProviderState.UNAVAILABLE,
                        "PROVIDER_MODEL_UNAVAILABLE",
                        "The configured Ollama model is not installed.",
                    )
                if response.status_code >= 500 and attempt + 1 < self.MAX_ATTEMPTS:
                    logger.warning(
                        "Ollama retry scheduled reason=http_%s attempt=%s",
                        response.status_code,
                        attempt + 2,
                    )
                    await asyncio.sleep(self.RETRY_DELAY_SECONDS)
                    continue
                if response.status_code != 200:
                    logger.error("Ollama request failed code=PROVIDER_UNAVAILABLE operation=%s", output_model.__name__)
                    raise ProviderError(
                        ProviderState.UNAVAILABLE,
                        "PROVIDER_UNAVAILABLE",
                        f"Ollama returned HTTP {response.status_code}.",
                    )
                try:
                    body = response.json()
                    content = body["message"]["content"]
                    if not isinstance(content, str) or not content.strip():
                        raise ValueError("empty content")
                    return output_model.model_validate_json(content)
                except (KeyError, TypeError, ValueError, ValidationError) as exc:
                    logger.error("Ollama request failed code=PROVIDER_RESPONSE_INVALID operation=%s", output_model.__name__)
                    raise ProviderError(
                        ProviderState.MALFORMED_RESPONSE,
                        "PROVIDER_RESPONSE_INVALID",
                        "Ollama returned output that failed schema validation.",
                    ) from exc

        raise ProviderError(ProviderState.UNAVAILABLE, "PROVIDER_UNAVAILABLE", "Ollama retry loop ended without a response.")

    async def generate_investigation_plan(
        self,
        objective: str,
        catalog_summary: Dict[str, Any],
    ) -> PlanOutput:
        return await self._structured_chat(
            system_instruction="Plan only actions supported by the supplied data catalog.",
            prompt=(
                f"Objective: {objective}\n\nAvailable catalog:\n"
                f"{json.dumps(catalog_summary, indent=2, default=str)}\n\n"
                "Create one to four discrete, verifiable investigation tasks. Use document modality "
                "for uploaded text sources and make task descriptions useful as retrieval queries. "
                "For a simple objective over one ready document, create exactly one retrieval task; "
                "do not split retrieval, analysis, summary, and verification into redundant tasks."
            ),
            output_model=PlanOutput,
        )

    async def decide_next_action(
        self,
        objective: str,
        current_task: PlannedTask,
        prior_observations: List[Dict[str, Any]],
        available_tools: List[Dict[str, Any]],
    ) -> ToolDecision:
        return await self._structured_chat(
            system_instruction="Select exactly one supplied tool and provide arguments matching its input schema.",
            prompt=(
                f"Objective: {objective}\nCurrent task: {current_task.model_dump_json()}\n"
                f"Prior observations: {json.dumps(prior_observations[-3:], default=str)}\n"
                f"Available tools: {json.dumps(available_tools, default=str)}"
            ),
            output_model=ToolDecision,
        )

    async def verify_and_synthesize(
        self,
        objective: str,
        observations: List[Dict[str, Any]],
        evidence_items: List[Dict[str, Any]],
        calculations: List[Dict[str, Any]],
    ) -> SynthesisReport:
        return await self._structured_chat(
            system_instruction=(
                "Produce an evidence-grounded report. Every factual claim must cite one or more exact evidence "
                "IDs supplied by the application; never invent IDs or facts."
            ),
            prompt=(
                f"Objective: {objective}\n\nEvidence: {json.dumps(evidence_items, indent=2, default=str)}\n\n"
                f"Calculations: {json.dumps(calculations, indent=2, default=str)}\n\n"
                f"Observations: {json.dumps(observations, indent=2, default=str)}"
            ),
            output_model=SynthesisReport,
        )
