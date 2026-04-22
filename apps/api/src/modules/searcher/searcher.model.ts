import Decimal from 'decimal.js';
import { z } from 'zod';
import { LinkupError } from '@/commons/exceptions/linkup.error';
import { WalletTransaction } from '@/modules/wallets-transactions/wallet-transaction.model';

export namespace Searcher {
  export const SearchDepth = {
    Deep: 'deep',
    Fast: 'fast',
    Research: 'research',
    Standard: 'standard',
  } as const;

  export const SearchDepthSchema = z.enum(SearchDepth);
  export type SearchDepth = z.infer<typeof SearchDepthSchema>;

  export const ResearchDepth = {
    L: 'l',
    M: 'm',
    S: 's',
    XL: 'xl',
  } as const;

  export const ResearchDepthSchema = z.enum(ResearchDepth);
  export type ResearchDepth = z.infer<typeof ResearchDepthSchema>;

  export const ResearchMode = {
    Answer: 'answer',
    Investigate: 'investigate',
    Research: 'research',
  } as const;

  export const ResearchModeSchema = z.enum(ResearchMode);
  export type ResearchMode = z.infer<typeof ResearchModeSchema>;

  export const SearchOutputType = {
    SearchResults: 'searchResults',
    SourcedAnswer: 'sourcedAnswer',
    Structured: 'structured',
  } as const;

  export const SearchOutputTypeSchema = z.enum(SearchOutputType);
  export type SearchOutputType = z.infer<typeof SearchOutputTypeSchema>;

  export const SearchInputSchema = z.object({
    depth: SearchDepthSchema,
    excludeDomains: z.array(z.string()).optional(),
    fromDate: z.iso.date().optional(),
    includeDomains: z.array(z.string()).optional(),
    includeImages: z.boolean(),
    includeInlineCitations: z.boolean(),
    includeSources: z.boolean(),
    maxResults: z.number().optional(),
    outputType: SearchOutputTypeSchema,
    q: z.string(),
    researchDepth: ResearchDepthSchema.optional(),
    researchMode: ResearchModeSchema.optional(),
    structuredOutputSchema: z.record(z.string(), z.unknown()).optional(),
    toDate: z.iso.date(),
  });
  export type SearchInput = z.infer<typeof SearchInputSchema>;

  export const cost: Record<SearchDepth, Decimal> = {
    [SearchDepth.Fast]: new Decimal('0.005'),
    [SearchDepth.Standard]: new Decimal('0.005'),
    [SearchDepth.Deep]: new Decimal('0.05'),
    [SearchDepth.Research]: new Decimal('0.05'),
  };

  export const researchCost: Record<ResearchDepth, Decimal> = {
    [ResearchDepth.S]: new Decimal('0.01'),
    [ResearchDepth.M]: new Decimal('0.03'),
    [ResearchDepth.L]: new Decimal('0.05'),
    [ResearchDepth.XL]: new Decimal('0.10'),
  };

  export const walletTransactionType: Record<SearchDepth, WalletTransaction.Type> = {
    [SearchDepth.Fast]: WalletTransaction.Type.ApiUsageSearch,
    [SearchDepth.Standard]: WalletTransaction.Type.ApiUsageSearch,
    [SearchDepth.Deep]: WalletTransaction.Type.ApiUsageSearch,
    [SearchDepth.Research]: WalletTransaction.Type.ApiUsageResearch,
  };

  export type SearchResult = z.infer<typeof SearchResultSchema>;
  export type SearchResults = z.infer<typeof SearchResultsSchema>;
  export type SourcedAnswer = z.infer<typeof SourcedAnswerSchema>;
  export type Structured = z.infer<typeof StructuredSchema>;
  export type SearchResponse = z.infer<typeof SearchResponseSchema>;

  export const createSearchResults = (params: Omit<SearchResults, 'type'>): SearchResults =>
    SearchResultsSchema.parse({ type: 'searchResults', ...params });

  export const createSourcedAnswer = (params: Omit<SourcedAnswer, 'type'>): SourcedAnswer =>
    SourcedAnswerSchema.parse({ type: 'sourcedAnswer', ...params });

  export const createStructured = (params: Omit<Structured, 'type'>): Structured =>
    StructuredSchema.parse({ type: 'structured', ...params });

  export const isTextSearchResult = (result: SearchResult): result is TextSearchResult => {
    return result.type === 'text';
  };

  export const createTextSearchResult = (
    params: Omit<TextSearchResult, 'type'>,
  ): TextSearchResult => TextSearchResultSchema.parse({ ...params, type: 'text' });

  export const createImageSearchResult = (
    params: Omit<ImageSearchResult, 'type'>,
  ): ImageSearchResult => ImageSearchResultSchema.parse({ ...params, type: 'image' });

  const TextSearchResultSchema = z.object({
    content: z.string(),
    favicon: z.string(),
    name: z.string(),
    type: z.literal('text'),
    url: z.string(),
  });

  const ImageSearchResultSchema = z.object({
    name: z.string(),
    type: z.literal('image'),
    url: z.string(),
  });

  const SearchResultSchema = z.discriminatedUnion('type', [
    TextSearchResultSchema,
    ImageSearchResultSchema,
  ]);

  const SearchResultsSchema = z.object({
    results: z.array(SearchResultSchema),
    type: z.literal('searchResults'),
  });

  const SourcedAnswerSchema = z.object({
    answer: z.string(),
    sources: z.array(
      z.object({
        favicon: z.string(),
        name: z.string(),
        snippet: z.string(),
        url: z.string(),
      }),
    ),
    type: z.literal('sourcedAnswer'),
  });

  const StructuredSchema = z.object({
    data: z.unknown(),
    type: z.literal('structured'),
  });

  export const SearchResponseSchema = z.discriminatedUnion('type', [
    SearchResultsSchema,
    SourcedAnswerSchema,
    StructuredSchema,
  ]);

  type TextSearchResult = z.infer<typeof TextSearchResultSchema>;
  type ImageSearchResult = z.infer<typeof ImageSearchResultSchema>;

  export class QueryNoResultError extends LinkupError {
    constructor() {
      super(400, 'SEARCH_QUERY_NO_RESULT', 'The query did not yield any result', [], true);
    }
  }
}
