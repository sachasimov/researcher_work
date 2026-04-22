from enum import Enum, StrEnum


class AppEnv(StrEnum):
    PRODUCTION = "production"
    DEVELOPMENT = "development"


class LogLevel(StrEnum):
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SearchDepth(StrEnum):
    STANDARD = "standard"
    DEEP = "deep"
    RESEARCH = "research"
    FAST = "fast"


class ResearchDepth(StrEnum):
    S = "s"
    M = "m"
    L = "l"
    XL = "xl"


class SearchOutputType(StrEnum):
    SEARCH_RESULTS = "searchResults"
    SOURCED_ANSWER = "sourcedAnswer"
    STRUCTURED = "structured"


class ToolName(Enum):
    GOOGLE_MAP = "GoogleMapTool"
    IMAGE_SEARCH = "ImageSearchTool"
    LINKEDIN_COMMENTS_FETCHER = "LinkedinCommentsFetcherTool"
    LINKEDIN_POSTS_FETCHER = "LinkedinPostsFetcherTool"
    LINKEDIN_POSTS_SEARCHER = "LinkedinPostsSearcherTool"
    PAPPERS = "PappersTool"
    WEB_SEARCH = "WebSearchTool"
    WEB_SCRAPER = "WebScraperTool"
    YAHOO_FINANCE_HISTORICAL = "YahooFinanceHistoricalTool"
    YAHOO_FINANCE_QUOTE = "YahooFinanceQuoteTool"
