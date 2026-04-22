import { Inject, Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { ClientGrpc } from '@nestjs/microservices';
import { catchError, firstValueFrom, map, Observable, of } from 'rxjs';
import { FeatureFlagsService } from '@/modules/feature-flags/feature-flags.service';
import { Organization } from '@/modules/organizations/organization.model';
import { Brain } from '@/modules/searcher/brain.model';
import { Searcher } from '@/modules/searcher/searcher.model';

@Injectable()
export class BrainService implements OnModuleInit {
  private readonly LOG = new Logger(BrainService.name);
  private brainService: BrainGrpcService;

  constructor(
    @Inject('BRAIN_CLIENT')
    private readonly grpcClient: ClientGrpc,
    private readonly featureFlagsService: FeatureFlagsService,
  ) {}

  onModuleInit() {
    this.brainService = this.grpcClient.getService('Brain');
  }

  async search(
    requestId: string,
    organization: Organization.Authenticated,
    input: Searcher.SearchInput,
  ): Promise<BrainResponse | undefined> {
    const toBrainSearchQuery = this.toBrainSearchQuery(requestId, organization, input);
    const deadlineMs = this.getDeadlineMs(input.depth, input.researchDepth);

    return await firstValueFrom(
      this.brainService
        .search(toBrainSearchQuery, {
          deadline: Date.now() + deadlineMs,
        })
        .pipe(
          map(({ answer, searchResults, structuredAnswer, traces, brainVersion, settings }) => ({
            answer,
            searchResults: this.parseResults(searchResults),
            ...(structuredAnswer && {
              structuredAnswer: JSON.parse(structuredAnswer),
            }),
            brainVersion,
            settings,
            traces,
          })),
          catchError(e => {
            this.LOG.warn(e);
            return of(undefined);
          }),
        ),
    );
  }

  private toBrainSearchQuery(
    requestId: string,
    organization: Organization.Authenticated,
    {
      q,
      depth,
      outputType,
      structuredOutputSchema,
      includeImages,
      fromDate,
      includeDomains,
      excludeDomains,
      toDate,
      includeInlineCitations,
      maxResults,
      researchDepth,
      researchMode,
    }: Searcher.SearchInput,
  ): SearchRequest {
    return {
      depth: this.toBrainDepth(depth),
      outputType: this.toBrainOutputType(outputType),
      query: q,
      ...(structuredOutputSchema && {
        structuredOutputSchema: JSON.stringify(structuredOutputSchema),
      }),
      includeImages,
      includeInlineCitations,
      ...(fromDate && { fromDate }),
      settings: this.pickSettings(organization, depth),
      ...(includeDomains && { includeDomains: Array.from(new Set(includeDomains)) }),
      ...(excludeDomains && { excludeDomains: Array.from(new Set(excludeDomains)) }),
      requestInfo: {
        organizationId: organization.id,
        requestId,
      },
      toDate,
      ...(maxResults && { maxResults }),
      ...(researchDepth && { researchDepth: this.toBrainResearchDepth(researchDepth) }),
      ...(researchMode && { researchMode: this.toBrainResearchMode(researchMode) }),
    };
  }

  private getDeadlineMs(
    depth: Searcher.SearchDepth,
    researchDepth?: Searcher.ResearchDepth,
  ): number {
    if (depth === Searcher.SearchDepth.Research && researchDepth) {
      return Brain.RESEARCH_DEADLINE_MS_BY_DEPTH[researchDepth] ?? Brain.DEFAULT_RESEARCH_DEADLINE_MS;
    }
    return depth === Searcher.SearchDepth.Research
      ? Brain.DEFAULT_RESEARCH_DEADLINE_MS
      : Brain.DEFAULT_DEADLINE_MS;
  }

  private pickSettings(
    { id: organizationId, isPayingCustomer }: Organization.Authenticated,
    depth: Searcher.SearchDepth,
  ): SearchSettings {
    const searchRequestFeatureFlagConfig = Brain.SEARCH_REQUEST_FEATURE_FLAG_CONFIG_BY_DEPTH[depth];
    const featureFlagContext = { isPayingCustomer, organizationId };

    return {
      agent: this.featureFlagsService.getFeatureValue(
        searchRequestFeatureFlagConfig.agent.featureFlag,
        searchRequestFeatureFlagConfig.agent.defaultValue,
        featureFlagContext,
      ),
      policy: this.featureFlagsService.getFeatureValue(
        searchRequestFeatureFlagConfig.policy.featureFlag,
        searchRequestFeatureFlagConfig.policy.defaultValue,
        featureFlagContext,
      ),
      responseFormatter: this.featureFlagsService.getFeatureValue(
        searchRequestFeatureFlagConfig.responseFormatter.featureFlag,
        searchRequestFeatureFlagConfig.responseFormatter.defaultValue,
        featureFlagContext,
      ),
    };
  }

  private toBrainDepth(depth: Searcher.SearchDepth): Depth {
    switch (depth) {
      case Searcher.SearchDepth.Standard:
        return 'SEARCH_DEPTH_STANDARD';
      case Searcher.SearchDepth.Deep:
        return 'SEARCH_DEPTH_DEEP';
      case Searcher.SearchDepth.Fast:
        return 'SEARCH_DEPTH_FAST';
      case Searcher.SearchDepth.Research:
        return 'SEARCH_DEPTH_RESEARCH';
    }
  }

  private toBrainResearchDepth(researchDepth: Searcher.ResearchDepth): ResearchDepthProto {
    switch (researchDepth) {
      case Searcher.ResearchDepth.S:
        return 'RESEARCH_DEPTH_S';
      case Searcher.ResearchDepth.M:
        return 'RESEARCH_DEPTH_M';
      case Searcher.ResearchDepth.L:
        return 'RESEARCH_DEPTH_L';
      case Searcher.ResearchDepth.XL:
        return 'RESEARCH_DEPTH_XL';
    }
  }

  private toBrainResearchMode(researchMode: Searcher.ResearchMode): ResearchModeProto {
    switch (researchMode) {
      case Searcher.ResearchMode.Answer:
        return 'RESEARCH_MODE_ANSWER';
      case Searcher.ResearchMode.Investigate:
        return 'RESEARCH_MODE_INVESTIGATE';
      case Searcher.ResearchMode.Research:
        return 'RESEARCH_MODE_RESEARCH';
    }
  }

  private toBrainOutputType(outputType: Searcher.SearchOutputType): OutputType {
    switch (outputType) {
      case Searcher.SearchOutputType.SearchResults:
        return 'SEARCH_OUTPUT_SEARCH_RESULTS';
      case Searcher.SearchOutputType.SourcedAnswer:
        return 'SEARCH_OUTPUT_SOURCED_ANSWER';
      case Searcher.SearchOutputType.Structured:
        return 'SEARCH_OUTPUT_STRUCTURED';
    }
  }

  private parseResults(results: SearchResult[]): Searcher.SearchResult[] {
    return (results ?? []).flatMap(result => {
      const items: Searcher.SearchResult[] = [];

      if (result.textResult) {
        const { name, url, content, favicon } = result.textResult;
        items.push(
          Searcher.createTextSearchResult({
            content,
            favicon,
            name,
            url,
          }),
        );
      }

      if (result.imageResult) {
        const { name, url } = result.imageResult;
        items.push(
          Searcher.createImageSearchResult({
            name,
            url,
          }),
        );
      }

      return items;
    });
  }
}

type BrainGrpcService = {
  search(request: SearchRequest, options?: { deadline?: number }): Observable<SearchResponse>;
};

type Depth =
  | 'SEARCH_DEPTH_STANDARD'
  | 'SEARCH_DEPTH_DEEP'
  | 'SEARCH_DEPTH_FAST'
  | 'SEARCH_DEPTH_RESEARCH';

type ResearchDepthProto =
  | 'RESEARCH_DEPTH_S'
  | 'RESEARCH_DEPTH_M'
  | 'RESEARCH_DEPTH_L'
  | 'RESEARCH_DEPTH_XL';

type ResearchModeProto =
  | 'RESEARCH_MODE_ANSWER'
  | 'RESEARCH_MODE_INVESTIGATE'
  | 'RESEARCH_MODE_RESEARCH';

type OutputType =
  | 'SEARCH_OUTPUT_SEARCH_RESULTS'
  | 'SEARCH_OUTPUT_SOURCED_ANSWER'
  | 'SEARCH_OUTPUT_STRUCTURED';

type SearchRequest = {
  query: string;
  depth: Depth;
  outputType: OutputType;
  structuredOutputSchema?: string;
  includeImages: boolean;
  fromDate?: string;
  toDate: string;
  includeInlineCitations: boolean;
  settings?: SearchSettings;
  requestInfo: RequestInfo;
  maxResults?: number;
  researchDepth?: ResearchDepthProto;
  researchMode?: ResearchModeProto;
};

type RequestInfo = {
  requestId: string;
  organizationId: string;
};

type SearchSettings = {
  agent: string;
  policy: string;
  responseFormatter: string;
};

type SearchResponse = {
  answer: string;
  searchResults: SearchResult[];
  structuredAnswer: string;
  traces: string;
  brainVersion: string;
  settings: SearchSettings;
};

type SearchResult = {
  textResult: TextResult;
  imageResult: ImageResult;
};

type TextResult = {
  name: string;
  url: string;
  content: string;
  favicon: string;
};

type ImageResult = {
  name: string;
  url: string;
};

export interface BrainResponse {
  searchResults?: Searcher.SearchResult[];
  answer?: string;
  structuredAnswer?: Record<string, unknown>;
  traces?: string;
  brainVersion: string;
  settings: SearchSettings;
}
