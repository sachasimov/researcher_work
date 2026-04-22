from __future__ import annotations

import asyncio
import time as _time
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger

from linkup_brain import enums, models

from ._constants import EXECUTOR_SOFT_TIMEOUT
from ._lead_executor import LeadExecutor
from ._prompts import (
    EXTRACT_CONTEXT_SYSTEM_PROMPT,
    PLAN_SYSTEM_PROMPT_INVESTIGATE,
    PLAN_SYSTEM_PROMPT_RESEARCH,
    PLAN_USER_PROMPT,
    REVIEW_SYSTEM_PROMPT,
    REVIEW_USER_PROMPT,
    SYNTHESIZE_SYSTEM_PROMPT,
    SYNTHESIZE_USER_PROMPT,
)
from ._types import (
    ExtractedContext,
    InvestigationPlan,
    InvestigationState,
    Lead,
    LeadResult,
    PipelineModeConfig,
    ResearchModeConfig,
    ReviewOutcome,
)
from ._utils import filter_search_results

if TYPE_CHECKING:
    from linkup_brain import llms, toolbox


class PipelineExecutor:
    def __init__(
        self,
        *,
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
        config: PipelineModeConfig,
        traces: list[models.BaseTrace],
    ) -> models.SearchResponse:
        pipeline_start = _time.monotonic()

        extracted_context = await self._extract_context(search_request.query, traces=traces)
        subject = extracted_context.subject
        language = extracted_context.language
        country_code = extracted_context.country_code
        logger.debug(f"[Pipeline] Context: subject='{subject}', locale={language}/{country_code}")

        today = datetime.now().strftime("%B %d, %Y")

        tool_budgets = {
            enums.ToolName.WEB_SEARCH.value: config.web_search_budget,
            enums.ToolName.WEB_SCRAPER.value: config.web_scraper_budget,
        }

        state = InvestigationState(
            query=search_request.query,
            subject=subject,
            language=language,
            country_code=country_code,
            tool_budgets=tool_budgets,
        )

        plan = await self._plan(
            search_request.query,
            config=config,
            language=language,
            country_code=country_code,
            today=today,
            traces=traces,
        )
        # Enforce the configured lead cap
        plan.leads = plan.leads[: config.max_leads]
        state.plan = plan
        logger.debug(f"[Pipeline] Plan generated: {len(plan.leads)} leads, {len(plan.dimensions)} dimensions")
        for dim in plan.dimensions:
            logger.debug(f"[Pipeline] Dimension: {dim}")

        wave_leads = plan.leads

        for wave in range(config.max_review_cycles):
            elapsed = _time.monotonic() - pipeline_start
            if elapsed > EXECUTOR_SOFT_TIMEOUT:
                logger.warning(
                    f"[Pipeline] Timeout reached ({elapsed:.0f}s > {EXECUTOR_SOFT_TIMEOUT}s)"
                )
                break

            logger.debug(f"[Pipeline] Wave {wave + 1} ({len(wave_leads)} leads)")

            results = await self._execute_leads(
                wave_leads,
                search_request=search_request,
                state=state,
                scrape_per_lead=config.scrape_per_lead,
                traces=traces,
            )
            state.lead_results.extend(results)

            for lr in results:
                for f in lr.findings:
                    if f.source_url:
                        state.all_sources.append(
                            models.TextSearchResult(
                                tool_call_id=uuid.uuid4().hex,
                                name=f.source_name,
                                url=f.source_url,
                                content=f.content,
                                favicon="",
                                relevancy_score=None,
                            )
                        )

            total_findings = sum(len(lr.findings) for lr in results)
            logger.debug(
                f"[Pipeline] Wave {wave + 1} done: {total_findings} findings, "
                f"budget: {state.budget_summary}"
            )

            if state.budget_exhausted:
                logger.debug("[Pipeline] Budget exhausted, skipping review")
                break

            elapsed = _time.monotonic() - pipeline_start
            if elapsed > EXECUTOR_SOFT_TIMEOUT:
                logger.warning(f"[Pipeline] Timeout after wave execution ({elapsed:.0f}s)")
                break

            review = await self._review(search_request.query, state, today, traces=traces)
            logger.debug(
                f"[Pipeline] Review: sufficient={review.is_sufficient}, "
                f"gaps={len(review.gaps)}, new_leads={len(review.new_leads)}"
            )

            if review.is_sufficient or not review.new_leads:
                break

            wave_leads = review.new_leads[: config.max_leads_per_review]

        # Synthesis uses mode-specific params when available
        synthesis_strategy = "thematic"
        min_sources = 1
        if isinstance(config, ResearchModeConfig):
            synthesis_strategy = config.synthesis_strategy
            min_sources = config.min_sources

        report = await self._synthesize(
            search_request.query,
            state.lead_results,
            today,
            synthesis_strategy=synthesis_strategy,
            min_sources=min_sources,
            traces=traces,
        )

        filtered_sources = filter_search_results(report, state.all_sources)

        elapsed = _time.monotonic() - pipeline_start
        logger.debug(f"[Pipeline] Complete in {elapsed:.1f}s")

        return models.SearchResponse(
            request_id=search_request.id,
            query=search_request.query,
            answer=report,
            search_results=filtered_sources,
            traces=traces,
        )

    async def _plan(
        self,
        query: str,
        *,
        config: PipelineModeConfig,
        language: str,
        country_code: str,
        today: str,
        traces: list[models.BaseTrace],
    ) -> InvestigationPlan:
        plan_prompt = (
            PLAN_SYSTEM_PROMPT_RESEARCH
            if isinstance(config, ResearchModeConfig)
            else PLAN_SYSTEM_PROMPT_INVESTIGATE
        )
        messages: list[models.Message] = [
            models.SystemMessage(
                content=plan_prompt.format(
                    today=today, language=language, country_code=country_code
                )
            ),
            models.UserMessage(content=PLAN_USER_PROMPT.format(query=query)),
        ]

        try:
            result_message: models.AssistantMessage[
                InvestigationPlan
            ] = await self._llm_client_strong.parse(messages, response_format=InvestigationPlan)
        except ValueError:
            logger.error("[Pipeline] Plan structured parse returned None")
            return InvestigationPlan(
                reasoning="Failed to parse plan — using fallback single lead",
                leads=[
                    Lead(
                        id="lead_1",
                        goal=query,
                        search_queries=[query],
                    )
                ],
            )

        traces.append(result_message)
        return result_message.content

    async def _execute_leads(
        self,
        leads: list[Lead],
        *,
        search_request: models.SearchRequest,
        state: InvestigationState,
        scrape_per_lead: int = 3,
        traces: list[models.BaseTrace],
    ) -> list[LeadResult]:
        executor = LeadExecutor(
            llm_client=self._llm_client_weak,
            toolbox_client=self._toolbox_client,
            search_request=search_request,
            state=state,
            traces=traces,
            wave_lead_count=max(1, len(leads)),
            scrape_per_lead=max(1, scrape_per_lead),
        )

        independent: list[Lead] = []
        dependent: list[Lead] = []

        completed_lead_ids = {lr.lead_id for lr in state.lead_results}
        for lead in leads:
            unmet = [dep for dep in lead.depends_on if dep not in completed_lead_ids]
            if not unmet:
                independent.append(lead)
            else:
                dependent.append(lead)

        # Sort by priority (1 = highest) so the most important leads execute first
        independent.sort(key=lambda lead: lead.priority)
        dependent.sort(key=lambda lead: lead.priority)

        results: list[LeadResult] = []
        if independent:
            coros = [executor.execute(lead) for lead in independent]
            results = list(await asyncio.gather(*coros))

        newly_completed = {lr.lead_id for lr in results}
        completed_lead_ids.update(newly_completed)

        remaining = list(dependent)
        while remaining:
            ready: list[Lead] = []
            still_blocked: list[Lead] = []
            for lead in remaining:
                unmet = [dep for dep in lead.depends_on if dep not in completed_lead_ids]
                if not unmet:
                    ready.append(lead)
                else:
                    still_blocked.append(lead)

            if not ready:
                for lead in remaining:
                    logger.warning(
                        f"[Pipeline] Lead '{lead.id}' has unresolvable dependencies: "
                        f"{lead.depends_on}"
                    )
                break

            batch_results = list(await asyncio.gather(*(executor.execute(lead) for lead in ready)))
            results.extend(batch_results)
            completed_lead_ids.update(lr.lead_id for lr in batch_results)
            remaining = still_blocked

        return results

    async def _review(
        self,
        query: str,
        state: InvestigationState,
        today: str,
        *,
        traces: list[models.BaseTrace],
    ) -> ReviewOutcome:
        findings_parts: list[str] = []
        for lr in state.lead_results:
            parts = [f"### Lead '{lr.lead_id}': {lr.goal} (status: {lr.status})"]
            if lr.findings:
                for i, f in enumerate(lr.findings, 1):
                    source_info = f" [{f.source_name}]({f.source_url})" if f.source_url else ""
                    parts.append(f"  {i}. {f.content}{source_info} (confidence: {f.confidence})")
            else:
                parts.append("  No findings.")
            findings_parts.append("\n".join(parts))

        findings_summary = "\n\n".join(findings_parts)

        dimensions_list = "\n".join(
            f"{i}. {dim}" for i, dim in enumerate(state.plan.dimensions, 1)
        ) if state.plan and state.plan.dimensions else "No dimensions defined."

        system_prompt = REVIEW_SYSTEM_PROMPT.format(
            today=today,
            remaining_budget=state.budget_summary,
        )
        user_prompt = REVIEW_USER_PROMPT.format(
            query=query,
            dimensions=dimensions_list,
            findings_summary=findings_summary,
            remaining_budget=state.budget_summary,
        )

        messages: list[models.Message] = [
            models.SystemMessage(content=system_prompt),
            models.UserMessage(content=user_prompt),
        ]

        try:
            result_message: models.AssistantMessage[
                ReviewOutcome
            ] = await self._llm_client_strong.parse(messages, response_format=ReviewOutcome)
        except ValueError:
            logger.error("[Pipeline] Review structured parse returned None")
            return ReviewOutcome(
                is_sufficient=True,
                reasoning="Failed to parse review — defaulting to sufficient",
            )

        traces.append(result_message)
        review = result_message.content
        for ds in review.dimension_scores:
            logger.debug(f"[Pipeline] Dimension '{ds.dimension}': {ds.score}")
        for gap in review.gaps:
            logger.debug(f"[Pipeline] Gap: {gap}")
        for lead in review.new_leads:
            logger.debug(f"[Pipeline] New lead '{lead.id}': {lead.goal}")
        return review

    async def _synthesize(
        self,
        query: str,
        lead_results: list[LeadResult],
        today: str,
        *,
        synthesis_strategy: str = "thematic",
        min_sources: int = 1,
        traces: list[models.BaseTrace],
    ) -> str:
        findings_parts: list[str] = []
        for lr in lead_results:
            if not lr.findings:
                continue
            parts = [f"### Lead: {lr.goal}"]
            for f in lr.findings:
                source_info = f" [Source: {f.source_name}]({f.source_url})" if f.source_url else ""
                parts.append(f"- {f.content}{source_info}")
            findings_parts.append("\n".join(parts))

        if not findings_parts:
            return "Investigation produced no findings. No sources could be retrieved."

        all_findings = "\n\n".join(findings_parts)

        system_prompt = SYNTHESIZE_SYSTEM_PROMPT.format(
            today=today,
            synthesis_strategy=synthesis_strategy,
            min_sources=min_sources,
        )
        user_prompt = SYNTHESIZE_USER_PROMPT.format(
            query=query,
            all_findings=all_findings,
        )

        messages: list[models.Message] = [
            models.SystemMessage(content=system_prompt),
            models.UserMessage(content=user_prompt),
        ]
        try:
            result_message: models.AssistantMessage[str] = await self._llm_client_strong.complete(
                messages
            )
        except ValueError:
            return "Synthesis failed."

        traces.append(result_message)
        return result_message.content

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
