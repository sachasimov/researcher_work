import { Searcher } from '@/modules/searcher/searcher.model';

export namespace Brain {
  export const DEFAULT_FAST_AGENT = 'Fast' as const;
  export const DEFAULT_STANDARD_AGENT = 'LanggraphStandard' as const;
  export const DEFAULT_DEEP_AGENT = 'LanggraphDeep' as const;
  export const DEFAULT_RESEARCH_AGENT = 'OpenaiResearcherAlpha2' as const;

  export const DEFAULT_FAST_POLICY = 'Gpt41MiniStandard' as const; // TODO: value doesn't matter, this should be removed in the future
  export const DEFAULT_STANDARD_POLICY = 'Gpt41MiniStandard' as const;
  export const DEFAULT_DEEP_POLICY = 'Gpt41Mini' as const;
  export const DEFAULT_RESEARCH_POLICY = 'Gpt41MiniResearch' as const;

  export const DEFAULT_FAST_RESPONSE_FORMATTER = 'Gpt41Mini' as const;
  export const DEFAULT_STANDARD_RESPONSE_FORMATTER = 'Gpt41Mini' as const;
  export const DEFAULT_DEEP_RESPONSE_FORMATTER = 'Gpt41Mini' as const;
  export const DEFAULT_RESEARCH_RESPONSE_FORMATTER = 'Gpt41Research' as const;

  export const DEFAULT_DEADLINE_MS = 180000; // 3 minutes
  export const DEFAULT_RESEARCH_DEADLINE_MS = 720000; // 12 minutes

  export const RESEARCH_DEADLINE_MS_BY_DEPTH: Record<string, number> = {
    [Searcher.ResearchDepth.S]: 600000, // 10 minutes
    [Searcher.ResearchDepth.M]: 720000, // 12 minutes
    [Searcher.ResearchDepth.L]: 900000, // 15 minutes
    [Searcher.ResearchDepth.XL]: 1200000, // 20 minutes
  };

  export type FeatureFlagConfig = {
    defaultValue: string;
    featureFlag: string;
  };

  export type SearchRequestFeatureFlagConfig = {
    agent: FeatureFlagConfig;
    policy: FeatureFlagConfig;
    responseFormatter: FeatureFlagConfig;
  };

  export const SEARCH_REQUEST_FEATURE_FLAG_CONFIG_BY_DEPTH: Record<
    Searcher.SearchDepth,
    SearchRequestFeatureFlagConfig
  > = {
    [Searcher.SearchDepth.Fast]: {
      agent: { defaultValue: DEFAULT_FAST_AGENT, featureFlag: 'brain-fast-agent' },
      policy: { defaultValue: DEFAULT_FAST_POLICY, featureFlag: 'brain-fast-policy' },
      responseFormatter: {
        defaultValue: DEFAULT_FAST_RESPONSE_FORMATTER,
        featureFlag: 'brain-fast-response-formatter',
      },
    },
    [Searcher.SearchDepth.Standard]: {
      agent: { defaultValue: DEFAULT_STANDARD_AGENT, featureFlag: 'brain-standard-agent' },
      policy: { defaultValue: DEFAULT_STANDARD_POLICY, featureFlag: 'brain-standard-policy' },
      responseFormatter: {
        defaultValue: DEFAULT_STANDARD_RESPONSE_FORMATTER,
        featureFlag: 'brain-standard-response-formatter',
      },
    },
    [Searcher.SearchDepth.Deep]: {
      agent: { defaultValue: DEFAULT_DEEP_AGENT, featureFlag: 'brain-deep-agent' },
      policy: { defaultValue: DEFAULT_DEEP_POLICY, featureFlag: 'brain-deep-policy' },
      responseFormatter: {
        defaultValue: DEFAULT_DEEP_RESPONSE_FORMATTER,
        featureFlag: 'brain-deep-response-formatter',
      },
    },
    [Searcher.SearchDepth.Research]: {
      agent: { defaultValue: DEFAULT_RESEARCH_AGENT, featureFlag: 'brain-research-agent' },
      policy: { defaultValue: DEFAULT_RESEARCH_POLICY, featureFlag: 'brain-research-policy' },
      responseFormatter: {
        defaultValue: DEFAULT_RESEARCH_RESPONSE_FORMATTER,
        featureFlag: 'brain-research-response-formatter',
      },
    },
  };
}
