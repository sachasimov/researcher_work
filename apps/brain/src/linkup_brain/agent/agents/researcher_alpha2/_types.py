from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from linkup_brain import enums, models

ResearchMode = enums.ResearchMode


class BaseModeConfig(BaseModel):
    pass


class ResearchModeConfig(BaseModeConfig):
    min_sources: int = Field(default=5, description="Minimum diverse sources to cite")
    synthesis_strategy: Literal["hierarchical", "thematic", "chronological"] = Field(
        default="hierarchical", description="How to organize the report"
    )
    max_leads: int = Field(default=15, description="Maximum number of investigation leads")
    max_review_cycles: int = Field(default=5, description="Maximum review/refine iterations")
    max_leads_per_review: int = Field(default=8, description="Maximum new leads per review cycle")
    scrape_per_lead: int = Field(default=5, description="Maximum URLs to scrape per lead")
    web_search_budget: int = Field(default=120, description="Maximum web search tool calls")
    web_scraper_budget: int = Field(default=90, description="Maximum web scraper tool calls")

    @classmethod
    def for_depth(cls, depth: enums.ResearchDepth) -> ResearchModeConfig:
        configs: dict[enums.ResearchDepth, dict[str, Any]] = {
            enums.ResearchDepth.S: dict(
                min_sources=2,
                max_leads=4,
                max_review_cycles=1,
                max_leads_per_review=3,
                scrape_per_lead=2,
                web_search_budget=20,
                web_scraper_budget=15,
            ),
            enums.ResearchDepth.M: dict(
                min_sources=3,
                max_leads=8,
                max_review_cycles=2,
                max_leads_per_review=5,
                scrape_per_lead=3,
                web_search_budget=50,
                web_scraper_budget=35,
            ),
            enums.ResearchDepth.L: dict(
                min_sources=4,
                max_leads=12,
                max_review_cycles=3,
                max_leads_per_review=6,
                scrape_per_lead=4,
                web_search_budget=80,
                web_scraper_budget=60,
            ),
            enums.ResearchDepth.XL: dict(
                min_sources=8,
                max_leads=20,
                max_review_cycles=6,
                max_leads_per_review=10,
                scrape_per_lead=6,
                web_search_budget=150,
                web_scraper_budget=100,
            ),
        }
        return cls(**configs[depth])


class InvestigateModeConfig(BaseModeConfig):
    max_leads: int = Field(default=10, description="Maximum number of investigation leads")
    max_review_cycles: int = Field(default=3, description="Maximum review/refine iterations")
    max_leads_per_review: int = Field(default=8, description="Maximum new leads per review cycle")
    scrape_per_lead: int = Field(default=3, description="Maximum URLs to scrape per lead")
    web_search_budget: int = Field(default=80, description="Maximum web search tool calls")
    web_scraper_budget: int = Field(default=60, description="Maximum web scraper tool calls")

    @classmethod
    def for_depth(cls, depth: enums.ResearchDepth) -> InvestigateModeConfig:
        configs: dict[enums.ResearchDepth, dict[str, Any]] = {
            enums.ResearchDepth.S: dict(
                max_leads=3,
                max_review_cycles=1,
                max_leads_per_review=3,
                scrape_per_lead=2,
                web_search_budget=15,
                web_scraper_budget=10,
            ),
            enums.ResearchDepth.M: dict(
                max_leads=6,
                max_review_cycles=2,
                max_leads_per_review=5,
                scrape_per_lead=2,
                web_search_budget=35,
                web_scraper_budget=25,
            ),
            enums.ResearchDepth.L: dict(
                max_leads=8,
                max_review_cycles=3,
                max_leads_per_review=6,
                scrape_per_lead=3,
                web_search_budget=55,
                web_scraper_budget=40,
            ),
            enums.ResearchDepth.XL: dict(
                max_leads=15,
                max_review_cycles=4,
                max_leads_per_review=8,
                scrape_per_lead=5,
                web_search_budget=100,
                web_scraper_budget=70,
            ),
        }
        return cls(**configs[depth])


class AnswerModeConfig(BaseModeConfig):
    max_retrieval_iterations: int = Field(default=30, description="Maximum agentic loop turns")
    max_self_reviews: int = Field(
        default=3, description="Maximum self-review cycles before finalizing"
    )

    @classmethod
    def for_depth(cls, depth: enums.ResearchDepth) -> AnswerModeConfig:
        configs: dict[enums.ResearchDepth, dict[str, Any]] = {
            enums.ResearchDepth.S: dict(
                max_retrieval_iterations=10,
                max_self_reviews=1,
            ),
            enums.ResearchDepth.M: dict(
                max_retrieval_iterations=15,
                max_self_reviews=2,
            ),
            enums.ResearchDepth.L: dict(
                max_retrieval_iterations=25,
                max_self_reviews=3,
            ),
            enums.ResearchDepth.XL: dict(
                max_retrieval_iterations=40,
                max_self_reviews=4,
            ),
        }
        return cls(**configs[depth])


type ModeConfig = ResearchModeConfig | InvestigateModeConfig | AnswerModeConfig
type PipelineModeConfig = ResearchModeConfig | InvestigateModeConfig


class ModeClassification(BaseModel):
    mode: ResearchMode = Field(description="The classified research mode")
    reasoning: str = Field(description="Brief explanation of the classification decision")


class Lead(BaseModel):
    id: str = Field(description="Unique lead identifier (e.g., 'lead_1')")
    goal: str = Field(description="What this lead aims to discover")
    search_queries: list[str] = Field(
        default_factory=list,
        description="Web search queries to execute",
    )
    scrape_urls: list[str] = Field(
        default_factory=list,
        description="Specific URLs to scrape for detailed content",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="IDs of leads that must complete before this one",
    )
    priority: int = Field(
        default=1,
        description="Execution priority (1=highest)",
        ge=1,
        le=10,
    )


class InvestigationPlan(BaseModel):
    reasoning: str = Field(description="LLM's reasoning about query decomposition")
    dimensions: list[str] = Field(
        default_factory=list,
        description="Key aspects/dimensions the report must cover (4-8 items)",
    )
    leads: list[Lead] = Field(description="Ordered list of leads to pursue")


class Finding(BaseModel):
    content: str = Field(description="The extracted information")
    source_url: str = Field(default="", description="URL where this was found")
    source_name: str = Field(default="", description="Name/title of the source")
    confidence: float = Field(
        default=0.5,
        description="Confidence in this finding (0-1)",
        ge=0.0,
        le=1.0,
    )


class LeadResult(BaseModel):
    lead_id: str
    goal: str
    findings: list[Finding] = Field(default_factory=list[Finding])
    queries_executed: list[str] = Field(default_factory=list)
    urls_scraped: list[str] = Field(default_factory=list)
    sources_found: int = 0
    status: str = Field(
        default="success",
        description="Execution status: success, partial, empty, skipped, error",
    )


class DimensionScore(BaseModel):
    dimension: str = Field(description="The dimension being scored")
    score: str = Field(description="Coverage score: covered, partial, or missing")


class ReviewOutcome(BaseModel):
    dimension_scores: list[DimensionScore] = Field(
        default_factory=list,
        description="Coverage score per dimension",
    )
    is_sufficient: bool = Field(description="Whether gathered info answers the query")
    reasoning: str = Field(description="Explanation of the assessment")
    gaps: list[str] = Field(
        default_factory=list,
        description="Information gaps still remaining (only for missing dimensions)",
    )
    new_leads: list[Lead] = Field(
        default_factory=list[Lead],
        description="New leads to pursue for missing dimensions only",
    )


class ExtractedContext(BaseModel):
    subject: str = Field(default="", description="Extracted subject name")
    language: str = Field(default="en", description="Detected language code")
    country_code: str = Field(default="us", description="Detected country code")


class FindingsExtraction(BaseModel):
    findings: list[Finding] = Field(
        default_factory=list[Finding],
        description="Extracted findings from sources",
    )


FALLBACK_TOOL_BUDGET = 20


class InvestigationState(BaseModel):
    query: str
    subject: str = ""
    language: str = "en"
    country_code: str = "us"
    plan: InvestigationPlan | None = None
    lead_results: list[LeadResult] = Field(default_factory=list[LeadResult])
    review_cycles: int = 0
    all_sources: list[models.SearchResult] = Field(default_factory=list[models.SearchResult])

    tool_budgets: dict[str, int] = Field(default_factory=dict)
    tool_usage: dict[str, int] = Field(default_factory=dict)

    def _budget_for(self, tool_name: str) -> int:
        return self.tool_budgets.get(tool_name, FALLBACK_TOOL_BUDGET)

    def tool_budget_exhausted(self, tool_name: str) -> bool:
        return self.tool_usage.get(tool_name, 0) >= self._budget_for(tool_name)

    @property
    def budget_exhausted(self) -> bool:
        known_tools = set(self.tool_budgets) | set(self.tool_usage)
        return all(self.tool_budget_exhausted(t) for t in known_tools)

    def remaining(self, tool_name: str) -> int:
        return max(0, self._budget_for(tool_name) - self.tool_usage.get(tool_name, 0))

    def use_tool(self, tool_name: str) -> None:
        self.tool_usage[tool_name] = self.tool_usage.get(tool_name, 0) + 1

    @property
    def budget_summary(self) -> str:
        known_tools = dict.fromkeys([*self.tool_budgets, *self.tool_usage])
        parts: list[str] = []
        for tool_name in known_tools:
            used = self.tool_usage.get(tool_name, 0)
            limit = self._budget_for(tool_name)
            parts.append(f"{tool_name}: {used}/{limit}")
        return ", ".join(parts)
