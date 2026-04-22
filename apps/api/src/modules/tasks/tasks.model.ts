import { LinkupError } from '@/commons/exceptions/linkup.error';
import { Fetch } from '@/modules/fetch/fetch.model';
import { Searcher } from '@/modules/searcher/searcher.model';

export namespace Tasks {
  export const Status = {
    Completed: 'completed',
    Failed: 'failed',
    Pending: 'pending',
    Processing: 'processing',
  } as const;
  export type Status = (typeof Status)[keyof typeof Status];

  export const Type = {
    Fetch: 'fetch',
    Research: 'research',
    Search: 'search',
  } as const;
  export type Type = (typeof Type)[keyof typeof Type];

  export type ListFilters = Readonly<{
    status?: Status[];
    type?: Type[];
  }>;

  type TaskBase = Readonly<{
    createdAt: Date;
    error: string | null;
    id: string;
    organizationId: string;
    requestId: string;
    serviceAccountId: string;
    status: Status;
    updatedAt: Date;
  }>;

  export type SearchInput = Omit<Searcher.SearchInput, 'depth'> & {
    depth: Exclude<Searcher.SearchDepth, typeof Searcher.SearchDepth.Research>;
  };

  export type ResearchInput = Omit<Searcher.SearchInput, 'depth' | 'outputType'> & {
    depth: typeof Searcher.SearchDepth.Research;
    outputType: Exclude<Searcher.SearchOutputType, typeof Searcher.SearchOutputType.SearchResults>;
  };

  export type SearchModel = TaskBase &
    Readonly<{
      input: SearchInput;
      output: Searcher.SearchResponse | null;
      type: typeof Type.Search;
    }>;

  export type FetchModel = TaskBase &
    Readonly<{
      input: Fetch.FetchInput;
      output: Fetch.Model | null;
      type: typeof Type.Fetch;
    }>;

  export type ResearchModel = TaskBase &
    Readonly<{
      input: ResearchInput;
      output: Searcher.SearchResponse | null;
      type: typeof Type.Research;
    }>;

  export type Model = SearchModel | FetchModel | ResearchModel;

  type CreateBase = Pick<TaskBase, 'organizationId' | 'requestId' | 'serviceAccountId' | 'status'>;

  export type SearchCreate = CreateBase &
    Readonly<{
      input: SearchInput;
      type: typeof Type.Search;
    }>;

  export type FetchCreate = CreateBase &
    Readonly<{
      input: Fetch.FetchInput;
      type: typeof Type.Fetch;
    }>;

  export type ResearchCreate = CreateBase &
    Readonly<{
      input: ResearchInput;
      type: typeof Type.Research;
    }>;

  export type Create = SearchCreate | FetchCreate | ResearchCreate;

  export type ResearchSubmissionInput = Omit<
    ResearchInput,
    'depth' | 'includeInlineCitations' | 'includeSources' | 'maxResults' | 'researchDepth'
  > & {
    depth?: Searcher.ResearchDepth;
  };

  export type Submission =
    | Readonly<{ input: SearchInput; type: typeof Type.Search }>
    | Readonly<{ input: Fetch.FetchInput; type: typeof Type.Fetch }>
    | Readonly<{ input: ResearchSubmissionInput; type: typeof Type.Research }>;

  export class NotFoundError extends LinkupError {
    constructor(taskId: string) {
      super(404, 'TASK_NOT_FOUND', `Task ${taskId} not found.`, []);
    }
  }

  export function isResearchModel(task: Model): task is ResearchModel {
    return task.type === Type.Research;
  }
}
