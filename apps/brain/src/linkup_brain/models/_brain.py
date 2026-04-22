from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from linkup_brain import enums

from ._search_results import SearchResult
from ._toolbox import ToolboxCache
from ._trace import BaseTrace
from ._utils import deduplicate


class RequestInfo(BaseModel):
    request_id: str = Field(min_length=1)
    organization_id: str = Field(min_length=1)


class SearchSettings(BaseModel):
    agent_name: str = Field(min_length=1)
    policy_name: str = Field(min_length=1)
    response_formatter_name: str = Field(min_length=1)


class SearchRequest(BaseModel):
    id: str = Field(default="root", min_length=1)
    required_request_ids: list[str] = []
    query: str = Field(min_length=1)
    depth: enums.SearchDepth
    output_type: enums.SearchOutputType
    structured_output_schema: str = ""
    include_images: bool = False
    from_date: str = ""
    to_date: str = ""
    exclude_domains: list[str] = []
    include_domains: list[str] = []
    include_inline_citations: bool = False
    max_results: int | None = Field(default=None, gt=0)
    research_depth: enums.ResearchDepth = Field(default=enums.ResearchDepth.L)
    research_mode: enums.ResearchMode | None = Field(default=None)
    settings: SearchSettings
    request_info: RequestInfo | None = None
    toolbox_cache: ToolboxCache = ToolboxCache()

    @model_validator(mode="after")
    def _validate_structured_output_schema(self) -> Self:
        if (
            self.output_type == enums.SearchOutputType.STRUCTURED
            and not self.structured_output_schema
        ):
            raise ValueError("Missing value for `structured_output_schema`")
        return self


class SearchResponse(BaseModel):
    request_id: str = Field(default="root", min_length=1)
    query: str = Field(min_length=1)
    answer: str
    search_results: list[SearchResult]
    traces: list[BaseTrace] = []

    @field_validator("search_results", mode="after")
    @classmethod
    def _deduplicate_search_results(cls, search_results: list[SearchResult]) -> list[SearchResult]:
        return deduplicate(search_results)


class SearchResponseFormatting(BaseModel):
    answer: str = ""
    structured_answer: str = ""


class FormattedSearchResponse(SearchResponse):
    structured_answer: str
    brain_version: str
    settings: SearchSettings
