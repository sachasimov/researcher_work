from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from loguru import logger
from openai import AsyncOpenAI

from linkup_brain import enums, llms, models, settings, toolbox
from linkup_brain.agent.abc import BaseAgent

from ._answer_executor import AnswerExecutor
from ._pipeline_executor import PipelineExecutor
from ._prompts import CLASSIFY_MODE_SYSTEM_PROMPT, CLASSIFY_MODE_USER_PROMPT
from ._types import (
    AnswerModeConfig,
    InvestigateModeConfig,
    ModeClassification,
    ModeConfig,
    ResearchMode,
    ResearchModeConfig,
)

if TYPE_CHECKING:
    from linkup_brain.policy.abc import BasePolicy


class _BaseResearchAlpha2Agent(BaseAgent):
    def __init__(
        self,
        *,
        llm_client_strong: llms.BaseClient,
        llm_client_weak: llms.BaseClient,
    ) -> None:
        super().__init__(
            toolbox_client=toolbox.Client(postprocessor=toolbox.postprocessors.CohereV2())
        )

        self._llm_client_strong = llm_client_strong
        self._llm_client_weak = llm_client_weak

        self._answer_executor = AnswerExecutor(
            toolbox_client=self._toolbox_client,
            llm_client_strong=self._llm_client_strong,
            llm_client_weak=self._llm_client_weak,
        )
        self._investigate_executor = PipelineExecutor(
            llm_client_strong=self._llm_client_strong,
            llm_client_weak=self._llm_client_weak,
            toolbox_client=self._toolbox_client,
        )

    async def search(
        self, request: models.SearchRequest, policy: BasePolicy
    ) -> models.SearchResponse:
        traces: list[models.BaseTrace] = []
        research_depth = request.research_depth

        if request.research_mode is not None:
            mode = ResearchMode(request.research_mode)
        else:
            mode = await self._classify_mode(
                request.query,
                output_type=request.output_type,
                structured_output_schema=request.structured_output_schema,
                traces=traces,
            )
        logger.debug(f"[Research] Starting (mode={mode}, research_depth={research_depth})")

        if mode == ResearchMode.ANSWER:
            config: ModeConfig = AnswerModeConfig.for_depth(research_depth)
            tool_descriptions = await self._build_tool_descriptions(request)
            return await self._answer_executor(
                request,
                config=config,
                tool_descriptions=tool_descriptions,
                traces=traces,
            )

        if mode == ResearchMode.RESEARCH or mode == ResearchMode.INVESTIGATE:
            if mode == ResearchMode.RESEARCH:
                config = ResearchModeConfig.for_depth(research_depth)
            elif mode == ResearchMode.INVESTIGATE:
                config = InvestigateModeConfig.for_depth(research_depth)
            else:
                assert_never(mode)
            return await self._investigate_executor(
                request, config=config, research_depth=research_depth, traces=traces
            )

        assert_never(mode)

    async def _build_tool_descriptions(
        self, search_request: models.SearchRequest
    ) -> list[models.ToolDescription]:
        description = await self._toolbox_client.describe(search_request=search_request)
        logger.debug(f"[Research] Built {len(description.tool_descriptions)} tools from toolbox")
        return description.tool_descriptions

    async def _classify_mode(
        self,
        query: str,
        *,
        output_type: enums.SearchOutputType,
        structured_output_schema: str | None,
        traces: list[models.BaseTrace],
    ) -> ResearchMode:
        try:
            system_prompt = CLASSIFY_MODE_SYSTEM_PROMPT.format(
                output_type=output_type.value,
                structured_output_schema=structured_output_schema,
            )
            user_prompt = CLASSIFY_MODE_USER_PROMPT.format(query=query)

            messages: list[models.Message] = [
                models.SystemMessage(content=system_prompt),
                models.UserMessage(content=user_prompt),
            ]
            result_message: models.AssistantMessage[
                ModeClassification
            ] = await self._llm_client_weak.parse(messages, response_format=ModeClassification)
            traces.append(result_message)
            classification = result_message.content
            logger.debug(
                f"[Research] Auto-classified mode={classification.mode} "
                f"({classification.reasoning})"
            )
            return classification.mode

        except Exception as e:
            logger.warning(f"[Research] Mode classification failed, defaulting to INVESTIGATE: {e}")
            return ResearchMode.INVESTIGATE


class OpenaiGpt54ResearcherAlpha2Agent(_BaseResearchAlpha2Agent):
    def __init__(self) -> None:
        super().__init__(
            llm_client_strong=llms.OpenaiClient(
                AsyncOpenAI(
                    base_url=settings.OPENAI_BASE_URL,
                    api_key=settings.OPENAI_API_KEY.get_secret_value(),
                    timeout=120.0,
                    max_retries=2,
                ),
                model="gpt-5.4",
                temperature=0.3,
            ),
            llm_client_weak=llms.OpenaiClient(
                AsyncOpenAI(
                    base_url=settings.OPENAI_BASE_URL,
                    api_key=settings.OPENAI_API_KEY.get_secret_value(),
                    timeout=60.0,
                    max_retries=2,
                ),
                # NOTE: gpt-5.4-mini has a 272k context window (even if the documentation says
                # otherwise), let's use one with a bigger one
                model="gpt-4.1-mini",
                temperature=0.0,
            ),
        )


class OpenaiGpt41ResearcherAlpha2Agent(_BaseResearchAlpha2Agent):
    def __init__(self) -> None:
        super().__init__(
            llm_client_strong=llms.OpenaiClient(
                AsyncOpenAI(
                    base_url=settings.OPENAI_BASE_URL,
                    api_key=settings.OPENAI_API_KEY.get_secret_value(),
                    timeout=120.0,
                    max_retries=2,
                ),
                model="gpt-4.1",
                temperature=0.3,
            ),
            llm_client_weak=llms.OpenaiClient(
                AsyncOpenAI(
                    base_url=settings.OPENAI_BASE_URL,
                    api_key=settings.OPENAI_API_KEY.get_secret_value(),
                    timeout=60.0,
                    max_retries=2,
                ),
                model="gpt-4.1-mini",
                temperature=0.0,
            ),
        )


OpenaiResearcherAlpha2Agent = OpenaiGpt54ResearcherAlpha2Agent


class Gemini25ResearcherAlpha2Agent(_BaseResearchAlpha2Agent):
    def __init__(self) -> None:
        super().__init__(
            llm_client_strong=llms.GeminiClient(
                AsyncOpenAI(
                    base_url=settings.GEMINI_BASE_URL,
                    api_key=settings.GEMINI_API_KEY.get_secret_value(),
                    timeout=120.0,
                    max_retries=2,
                ),
                model="gemini-2.5-pro",
                temperature=0.3,
            ),
            llm_client_weak=llms.GeminiClient(
                AsyncOpenAI(
                    base_url=settings.GEMINI_BASE_URL,
                    api_key=settings.GEMINI_API_KEY.get_secret_value(),
                    timeout=60.0,
                    max_retries=2,
                ),
                model="gemini-2.5-flash",
                temperature=0.0,
            ),
        )


class Gemini31ResearcherAlpha2Agent(_BaseResearchAlpha2Agent):
    def __init__(self) -> None:
        super().__init__(
            llm_client_strong=llms.GeminiClient(
                AsyncOpenAI(
                    base_url=settings.GEMINI_BASE_URL,
                    api_key=settings.GEMINI_API_KEY.get_secret_value(),
                    timeout=120.0,
                    max_retries=2,
                ),
                model="gemini-3.1-pro-preview",
                temperature=0.3,
            ),
            llm_client_weak=llms.GeminiClient(
                AsyncOpenAI(
                    base_url=settings.GEMINI_BASE_URL,
                    api_key=settings.GEMINI_API_KEY.get_secret_value(),
                    timeout=60.0,
                    max_retries=2,
                ),
                model="gemini-3-flash-preview",
                temperature=0.0,
            ),
        )


GeminiResearcherAlpha2Agent = Gemini25ResearcherAlpha2Agent
