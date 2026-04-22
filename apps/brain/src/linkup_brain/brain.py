import asyncio
import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, assert_never, cast

import grpc.aio
from grpc_reflection.v1alpha import reflection
from loguru import logger
from pydantic import ValidationError

from linkup_brain import constants, enums, errors, logging, models, settings
from linkup_brain.resolvers import AgentResolver, PolicyResolver, ResponseFormatterResolver
from linkup_brain.search_result_selector import SearchResultSelector
from linkup_pb import brain_pb2, brain_pb2_grpc

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from linkup_brain.agent import BaseAgent
    from linkup_brain.policy import BasePolicy
    from linkup_brain.response_formatter import BaseResponseFormatter

SEARCH_DEPTH_PB_TO_SEARCH_DEPTH: dict[int, enums.SearchDepth | None] = {
    0: None,  # Unspecified
    1: enums.SearchDepth.STANDARD,
    2: enums.SearchDepth.DEEP,
    3: enums.SearchDepth.RESEARCH,
    4: enums.SearchDepth.FAST,
}
SEARCH_OUTPUT_TYPE_PB_TO_SEARCH_OUTPUT_TYPE: dict[int, enums.SearchOutputType | None] = {
    0: None,  # Unspecified
    1: enums.SearchOutputType.SEARCH_RESULTS,
    2: enums.SearchOutputType.SOURCED_ANSWER,
    3: enums.SearchOutputType.STRUCTURED,
}
RESEARCH_DEPTH_PB_TO_RESEARCH_DEPTH: dict[int, enums.ResearchDepth] = {
    0: enums.ResearchDepth.L,  # Unspecified defaults to L
    1: enums.ResearchDepth.S,
    2: enums.ResearchDepth.M,
    3: enums.ResearchDepth.L,
    4: enums.ResearchDepth.XL,
}


class Brain:
    def __init__(self) -> None:
        self.agent_resolver = AgentResolver()
        self.policy_resolver = PolicyResolver()
        self.search_result_selector = SearchResultSelector()
        self.response_formatter_resolver = ResponseFormatterResolver()

    async def search(self, request: models.SearchRequest) -> models.FormattedSearchResponse:
        logger.debug("Starting search")
        logger.debug(f"Query: {request.query}")
        logger.trace(f"Request: {request}")

        agent: BaseAgent = self.agent_resolver(name=request.settings.agent_name)
        policy: BasePolicy = self.policy_resolver(name=request.settings.policy_name)
        response_formatter: BaseResponseFormatter = self.response_formatter_resolver(
            name=request.settings.response_formatter_name
        )

        response: models.SearchResponse = await agent.search(request=request, policy=policy)
        logger.debug(f"Agent search completed with {len(response.search_results)} search results")
        if response.answer:
            logger.debug(f"Answer: {response.answer}")
        logger.trace(f"Response: {response}")

        if request.max_results and len(response.search_results) > request.max_results:
            logger.debug(
                f"Selecting {request.max_results} search results on {len(response.search_results)}"
            )
            try:
                selected_search_results: list[models.SearchResult] = self.search_result_selector(
                    response.search_results,
                    include_images=request.include_images,
                    max_results=request.max_results,
                    traces=response.traces,
                )
            except Exception as e:
                logger.error(
                    f"Error while selecting search results, falling back to naive first-only "
                    f"selection strategy: {e}"
                )
                selected_search_results = response.search_results[: request.max_results]
            response.search_results = selected_search_results

        if (
            request.output_type == enums.SearchOutputType.SOURCED_ANSWER
            or request.output_type == enums.SearchOutputType.STRUCTURED
        ):
            logger.debug(f"Formatting response for output type: {request.output_type.value}")
            try:
                search_response_formatting: models.SearchResponseFormatting = (
                    await response_formatter.format_search(request=request, response=response)
                )
            except Exception as e:
                raise errors.ResponseFormatterError(f"Response formatter crashed: {e}") from e
        elif request.output_type == enums.SearchOutputType.SEARCH_RESULTS:
            search_response_formatting = models.SearchResponseFormatting()
        else:
            assert_never(request.output_type)

        formatted_response = models.FormattedSearchResponse(
            request_id=response.request_id,
            query=response.query,
            answer=search_response_formatting.answer,
            structured_answer=search_response_formatting.structured_answer,
            search_results=response.search_results,
            traces=response.traces,
            brain_version=settings.GIT_SHORT_SHA,
            settings=request.settings,
        )

        logger.debug(
            f"Search completed with {len(formatted_response.search_results)} search results"
        )
        if formatted_response.answer:
            logger.debug(f"Answer: {formatted_response.answer}")
        if formatted_response.structured_answer:
            logger.debug(f"Structured Answer: {formatted_response.structured_answer}")
        logger.trace(f"Response: {formatted_response}")
        return formatted_response


class BrainServicer(brain_pb2_grpc.BrainServicer):
    def __init__(self) -> None:
        self._brain = Brain()

    async def Search(  # noqa: N802  # pragma: no cover
        self,
        request: brain_pb2.SearchRequest,
        context: grpc.aio.ServicerContext[brain_pb2.SearchRequest, brain_pb2.SearchResponse],
    ) -> brain_pb2.SearchResponse:
        try:
            search_request: models.SearchRequest = self._get_search_request(request=request)
            search_response: models.FormattedSearchResponse = await self._brain.search(
                request=search_request
            )
            return self._get_response(search_response=search_response)

        except errors.InvalidArgumentError as e:
            logger.exception(f"Invalid argument error: {e}")
            await context.abort(code=grpc.StatusCode.INVALID_ARGUMENT, details=str(e))
        except errors.ResponseFormatterError as e:
            logger.exception(f"Response formatter error: {e}")
            await context.abort(code=grpc.StatusCode.RESOURCE_EXHAUSTED, details=str(e))
        except Exception as e:
            logger.exception(f"Unhandled error: {e}")
            await context.abort(code=grpc.StatusCode.INTERNAL, details=str(e))

    @staticmethod
    def _get_search_request(request: brain_pb2.SearchRequest) -> models.SearchRequest:
        try:
            request_info_pb: brain_pb2.RequestInfo = request.request_info
            if request_info_pb.request_id and request_info_pb.organization_id:
                request_info: models.RequestInfo | None = models.RequestInfo(
                    request_id=request_info_pb.request_id,
                    organization_id=request_info_pb.organization_id,
                )
            elif not request_info_pb.request_id and not request_info_pb.organization_id:
                request_info = None
            else:
                raise errors.InvalidArgumentError(
                    "Both or neither of `request_id` and `organization_id` must be provided in "
                    "`request_info`"
                )

            return models.SearchRequest(
                query=request.query,
                depth=cast(
                    "enums.SearchDepth",
                    SEARCH_DEPTH_PB_TO_SEARCH_DEPTH[request.depth],
                ),
                output_type=cast(
                    "enums.SearchOutputType",
                    SEARCH_OUTPUT_TYPE_PB_TO_SEARCH_OUTPUT_TYPE[request.output_type],
                ),
                structured_output_schema=request.structured_output_schema,
                include_images=request.include_images,
                from_date=request.from_date,
                to_date=request.to_date,
                exclude_domains=list(request.exclude_domains),
                include_domains=list(request.include_domains),
                include_inline_citations=request.include_inline_citations,
                max_results=request.max_results or None,
                research_depth=RESEARCH_DEPTH_PB_TO_RESEARCH_DEPTH.get(
                    request.research_depth, enums.ResearchDepth.L
                ),
                settings=models.SearchSettings(
                    agent_name=request.settings.agent,
                    policy_name=request.settings.policy,
                    response_formatter_name=request.settings.response_formatter,
                ),
                request_info=request_info,
                toolbox_cache=models.ToolboxCache(),
            )
        except ValidationError as e:
            raise errors.InvalidArgumentError("Invalid request") from e

    @staticmethod
    def _get_response(
        search_response: models.FormattedSearchResponse,
    ) -> brain_pb2.SearchResponse:
        traces_serialized: str = json.dumps(
            [trace.model_dump() for trace in search_response.traces],
            ensure_ascii=False,
        )
        search_results_pb: list[brain_pb2.SearchResult] = [
            brain_pb2.SearchResult(
                text_result=brain_pb2.TextResult(
                    name=search_result.name,
                    url=search_result.url,
                    content=search_result.content,
                    favicon=search_result.favicon,
                    relevancy_score=search_result.relevancy_score,
                )
                if isinstance(search_result, models.TextSearchResult)
                else None,
                image_result=brain_pb2.ImageResult(
                    name=search_result.name,
                    url=search_result.url,
                )
                if isinstance(search_result, models.ImageSearchResult)
                else None,
            )
            for search_result in search_response.search_results
        ]
        return brain_pb2.SearchResponse(
            answer=search_response.answer,
            search_results=search_results_pb,
            traces=traces_serialized,
            structured_answer=search_response.structured_answer,
            brain_version=search_response.brain_version,
            settings=brain_pb2.SearchSettings(
                agent=search_response.settings.agent_name or "",
                policy=search_response.settings.policy_name or "",
                response_formatter=search_response.settings.response_formatter_name or "",
            ),
        )


SERVER_OPTIONS: Sequence[tuple[str, Any]] = [
    ("grpc.max_send_message_length", 100 * constants.DEFAULT_GRPC_MESSAGE_SIZE),
]


async def serve(servicer: BrainServicer) -> None:  # pragma: no cover
    server: grpc.aio.Server = grpc.aio.server(options=SERVER_OPTIONS)
    brain_pb2_grpc.add_BrainServicer_to_server(servicer=servicer, server=server)  # pyright: ignore[reportUnknownMemberType]

    # Enable gRPC reflection to make this testable with tools like grpcurl
    reflection.enable_server_reflection(
        [brain_pb2.DESCRIPTOR.services_by_name["Brain"].full_name],
        server,
    )

    server.add_insecure_port(f"[::]:{settings.PORT}")
    await server.start()
    logger.info(f"Brain service started on port {settings.PORT}")
    await server.wait_for_termination()


def main() -> None:  # pragma: no cover
    logging.setup()

    servicer = BrainServicer()
    service_coroutine: Awaitable[None] = serve(servicer=servicer)

    loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop=loop)
    loop.run_until_complete(future=service_coroutine)


if __name__ == "__main__":  # pragma: no cover
    main()
