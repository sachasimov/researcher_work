from __future__ import annotations

import asyncio
import time as _time
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from linkup_brain import enums, models

from ._constants import EXECUTOR_SOFT_TIMEOUT_BY_DEPTH
from ._prompts import (
    ANSWER_SELF_REVIEW_PROMPT,
    ANSWER_SYSTEM_PROMPT,
    EXTRACT_CONTEXT_SYSTEM_PROMPT,
    L_ANSWER_AUGMENTATION,
    M_ANSWER_AUGMENTATION,
    XL_ANSWER_AUGMENTATION,
)
from ._types import ExtractedContext
from ._utils import filter_search_results

if TYPE_CHECKING:
    from linkup_brain import llms, toolbox

    from ._types import AnswerModeConfig

ANSWER_AUGMENTATION_BY_DEPTH: dict[enums.ResearchDepth, str | None] = {
    enums.ResearchDepth.S: None,
    enums.ResearchDepth.M: M_ANSWER_AUGMENTATION,
    enums.ResearchDepth.L: L_ANSWER_AUGMENTATION,
    enums.ResearchDepth.XL: XL_ANSWER_AUGMENTATION,
}


class AnswerExecutor:
    def __init__(
        self,
        llm_client_strong: llms.BaseClient,
        llm_client_weak: llms.BaseClient,
        toolbox_client: toolbox.Client,
    ) -> None:
        self._llm_client_strong = llm_client_strong
        self._llm_client_weak = llm_client_weak
        self._toolbox_client = toolbox_client

    async def __call__(
        self,
        search_request: models.SearchRequest,
        *,
        config: AnswerModeConfig,
        tool_descriptions: list[models.ToolDescription],
        traces: list[models.BaseTrace],
    ) -> models.SearchResponse:
        research_depth = search_request.research_depth
        soft_timeout = EXECUTOR_SOFT_TIMEOUT_BY_DEPTH[research_depth]
        logger.debug(f"[Research] Starting agentic loop (research_depth={research_depth})")
        answer_start = _time.monotonic()

        max_turns = config.max_retrieval_iterations
        max_self_reviews = config.max_self_reviews

        today = datetime.now().strftime("%B %d, %Y")
        this_year = datetime.now().strftime("%Y")
        last_year = str(int(this_year) - 1)

        extracted_context = await self._extract_context(search_request.query, traces=traces)
        language = extracted_context.language
        country_code = extracted_context.country_code
        logger.debug(f"[Research] Context: locale={language}/{country_code}")

        system_prompt = ANSWER_SYSTEM_PROMPT.format(
            today=today,
            last_year=last_year,
            this_year=this_year,
            language=language,
            country_code=country_code,
        )
        answer_augmentation = ANSWER_AUGMENTATION_BY_DEPTH.get(research_depth)
        if answer_augmentation:
            system_prompt += "\n\n" + answer_augmentation

        messages: list[models.Message] = [
            models.SystemMessage(content=system_prompt),
            models.UserMessage(content=search_request.query),
        ]

        all_sources: list[models.SearchResult] = []
        self_review_count = 0
        timed_out = False

        turn = 0

        while turn < max_turns:
            elapsed = _time.monotonic() - answer_start
            if elapsed > soft_timeout:
                logger.warning(
                    f"[Research] Timeout reached ({elapsed:.0f}s > {soft_timeout}s)"
                )
                timed_out = True
                break

            turn += 1
            logger.debug(f"[Research] Turn {turn}/{max_turns}")

            result_message: models.AssistantMessage[
                str | None
            ] = await self._llm_client_strong.complete(
                messages, tool_descriptions=tool_descriptions
            )
            traces.append(result_message)
            messages.append(result_message)
            if result_message.content:
                logger.debug(f"[Research] Reasoning:\n{result_message.content}")

            if not result_message.tool_calls:
                if self_review_count < max_self_reviews:
                    self_review_count += 1
                    logger.debug(f"[Research] Self-review {self_review_count}/{max_self_reviews}")

                    messages.append(
                        models.UserMessage(
                            content=ANSWER_SELF_REVIEW_PROMPT.format(
                                today=today,
                                last_year=last_year,
                                this_year=this_year,
                            )
                        )
                    )
                    continue

                logger.debug(f"[Research] Agent finished after {turn} turns")
                answer = result_message.content or "Investigation produced no results."
                filtered_sources = filter_search_results(answer, all_sources)

                return models.SearchResponse(
                    request_id=search_request.id,
                    query=search_request.query,
                    answer=answer,
                    search_results=filtered_sources,
                    traces=traces,
                )

            for tool_call in result_message.tool_calls:
                logger.debug(f"[Research] Tool: {tool_call.name}({tool_call.params})")

            exec_results = await asyncio.gather(
                *(
                    self._execute_tool(
                        tool_name=tool_call.name,
                        tool_args=tool_call.params,
                        search_request=search_request,
                    )
                    for tool_call in result_message.tool_calls
                )
            )

            turn_tool_calls: list[models.ToolCall] = []
            turn_tool_results: list[models.ToolResult] = []
            conversation_tool_results: list[models.ToolResult] = []
            for tool_call, (result_text, sources, tool_result) in zip(
                result_message.tool_calls, exec_results, strict=True
            ):
                all_sources.extend(sources)
                turn_tool_calls.append(
                    models.ToolCall(
                        id=tool_result.tool_call_id,
                        name=tool_call.name,
                        params=tool_call.params,
                    )
                )
                turn_tool_results.append(tool_result)
                # For conversation continuity, create a ToolResult with the OpenAI tool_call_id
                # and the formatted text content
                conversation_tool_results.append(
                    models.ToolResult(
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.name,
                        search_results=tool_result.search_results,
                        cached=tool_result.cached,
                        content=result_text,
                    )
                )

            messages.append(models.ToolboxMessage(tool_results=conversation_tool_results))

            if turn_tool_calls:
                traces.append(
                    models.ToolCallBatch(content=result_message.content, tool_calls=turn_tool_calls)
                )
            if turn_tool_results:
                traces.append(models.ToolResultBatch.from_tool_results(turn_tool_results))

        if timed_out:
            logger.warning(f"[Research] Timeout after {turn} turns")
        else:
            logger.warning(f"[Research] Max turns ({max_turns}) reached")

        limit_reason = "the time limit" if timed_out else "the maximum number of search steps"
        messages.append(
            models.UserMessage(
                content=f"You've reached {limit_reason}. Please write your "
                "final report now based on everything you've found so far.",
            )
        )
        try:
            final_message: models.AssistantMessage[str] = await self._llm_client_strong.complete(
                messages
            )
        except ValueError:
            fallback = (
                "Investigation reached time limit."
                if timed_out
                else "Investigation reached step limit."
            )
            return models.SearchResponse(
                request_id=search_request.id,
                query=search_request.query,
                answer=fallback,
                search_results=filter_search_results(fallback, all_sources),
                traces=traces,
            )

        traces.append(final_message)
        answer = final_message.content
        filtered_sources = filter_search_results(answer, all_sources)

        return models.SearchResponse(
            request_id=search_request.id,
            query=search_request.query,
            answer=answer,
            search_results=filtered_sources,
            traces=traces,
        )

    async def _extract_context(
        self, query: str, *, traces: list[models.BaseTrace]
    ) -> ExtractedContext:
        try:
            messages: list[models.Message] = [
                models.SystemMessage(content=EXTRACT_CONTEXT_SYSTEM_PROMPT),
                models.UserMessage(content=query),
            ]
            result_message: models.AssistantMessage[
                ExtractedContext
            ] = await self._llm_client_weak.parse(messages, response_format=ExtractedContext)
            traces.append(result_message)
            return result_message.content
        except Exception as e:
            logger.warning(f"[Research] Context extraction failed: {e}")
            return ExtractedContext()

    async def _execute_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        *,
        search_request: models.SearchRequest,
    ) -> tuple[str, list[models.TextSearchResult], models.ToolResult]:
        tool_call = models.ToolCall(id=uuid.uuid4().hex, name=tool_name, params=tool_args)
        try:
            tool_result = await self._toolbox_client.execute(tool_call, search_request)
            results = [
                r
                for r in tool_result.search_results
                if isinstance(r, models.TextSearchResult) and r.content.strip()
            ]

            if not results:
                return "No results found.", [], tool_result

            parts: list[str] = []
            for i, r in enumerate(results, 1):
                content = r.content.strip()
                if len(content) > 2000:
                    content = content[:2000] + "..."
                parts.append(f"[{i}] {r.name}\nURL: {r.url}\n{content}")

            return "\n\n---\n\n".join(parts), results, tool_result

        except Exception as e:
            logger.error(f"[Research] Tool {tool_name} failed: {e}")
            empty_result = models.ToolResult(
                tool_call_id=tool_call.id, tool_name=tool_name, search_results=[]
            )
            return f"Tool {tool_name} failed: {type(e).__name__}", [], empty_result
