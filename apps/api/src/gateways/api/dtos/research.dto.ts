import { z } from 'zod';
import {
  createPaginatedInputSchema,
  PaginationMetadataSchema,
} from '@/commons/pagination/pagination.zod';
import {
  BaseSearchInputSchema,
  withDateRangeAndOutputTypeValidation,
} from '@/gateways/api/dtos/base-search.dto';
import { BaseTaskSchema, LIST_TASKS_SORTABLE_FIELDS } from '@/gateways/api/dtos/base-task.dto';
import {
  SourcedAnswerOutputSchema,
  StructuredOutputSchema,
  StructuredWithSourcesOutputSchema,
} from '@/gateways/api/dtos/search.dto';
import { createApiGatewayZodDto } from '@/gateways/api/zod/api-gateway-zod-dto';
import { Searcher } from '@/modules/searcher/searcher.model';
import { Tasks } from '@/modules/tasks/tasks.model';

const RESEARCH_OMITTED_FIELDS = {
  includeInlineCitations: true,
  includeSources: true,
  maxResults: true,
} as const;

type ResearchInputSchemaOptions = {
  id?: string;
  example?: Record<string, unknown>;
};

const createResearchInputSchema = ({
  id = 'PostResearchInput',
  example,
}: ResearchInputSchemaOptions = {}) =>
  withDateRangeAndOutputTypeValidation(
    BaseSearchInputSchema.omit(RESEARCH_OMITTED_FIELDS).extend({
      depth: z
        .enum(
          [
            Searcher.ResearchDepth.S,
            Searcher.ResearchDepth.M,
            Searcher.ResearchDepth.L,
            Searcher.ResearchDepth.XL,
          ],
          {
            error: `depth must be one of the following values: ${[
              Searcher.ResearchDepth.S,
              Searcher.ResearchDepth.M,
              Searcher.ResearchDepth.L,
              Searcher.ResearchDepth.XL,
            ].join(', ')}`,
          },
        )
        .default(Searcher.ResearchDepth.L)
        .meta({
          description:
            'The depth of the research. `s` is the fastest and cheapest, `xl` is the most thorough and expensive. Defaults to `l`.',
          enum: [
            Searcher.ResearchDepth.S,
            Searcher.ResearchDepth.M,
            Searcher.ResearchDepth.L,
            Searcher.ResearchDepth.XL,
          ],
        }),
      outputType: z
        .enum([Searcher.SearchOutputType.SourcedAnswer, Searcher.SearchOutputType.Structured], {
          error: `outputType must be one of the following values: ${[
            Searcher.SearchOutputType.SourcedAnswer,
            Searcher.SearchOutputType.Structured,
          ].join(', ')}`,
        })
        .meta({
          description:
            'The type of output you want to get. Use `structured` for a custom-formatted response defined by `structuredOutputSchema`.',
          enum: [Searcher.SearchOutputType.SourcedAnswer, Searcher.SearchOutputType.Structured],
        }),
    }),
  ).meta({ id, ...(example ? { example } : {}) });

export const ResearchInputSchema = createResearchInputSchema({
  example: {
    depth: 'l',
    excludeDomains: ['wikipedia.org'],
    includeDomains: ['microsoft.com', 'agolution.com'],
    includeImages: true,
    outputType: 'sourcedAnswer',
    q: "What is Microsoft's 2024 revenue?",
  },
});

export class ResearchInputContract extends createApiGatewayZodDto(ResearchInputSchema) {}

const ResearchOutputSchema = z.union([
  SourcedAnswerOutputSchema,
  StructuredWithSourcesOutputSchema,
  StructuredOutputSchema,
]);

export const ResearchTaskInputSchema = createResearchInputSchema({ id: 'ResearchTaskInput' });

export const ResearchTaskOutputSchema = BaseTaskSchema.extend({
  input: ResearchTaskInputSchema,
  output: ResearchOutputSchema.nullable(),
  type: z.literal(Tasks.Type.Research),
}).meta({ id: 'ResearchTaskOutput' });
export type ResearchTaskOutput = z.output<typeof ResearchTaskOutputSchema>;

export const ResearchTaskOutputContract = createApiGatewayZodDto(ResearchTaskOutputSchema, {
  codec: true,
});

const PostResearchOutputSchema = ResearchTaskOutputSchema.meta({ id: 'PostResearchOutput' });

export type PostResearchOutput = z.infer<typeof PostResearchOutputSchema>;
export class PostResearchOutputContract extends createApiGatewayZodDto(PostResearchOutputSchema) {}

export const ListResearchOutputSchema = PaginationMetadataSchema.extend({
  data: z.array(ResearchTaskOutputSchema),
}).meta({ id: 'ListResearchOutput' });

export type ListResearchOutput = z.output<typeof ListResearchOutputSchema>;

export const ListResearchOutputContract = createApiGatewayZodDto(ListResearchOutputSchema, {
  codec: true,
});

export const ListResearchInputSchema = createPaginatedInputSchema(LIST_TASKS_SORTABLE_FIELDS);
export type ListResearchInput = z.infer<typeof ListResearchInputSchema>;
