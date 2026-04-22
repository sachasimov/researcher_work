import { Injectable, Logger } from '@nestjs/common';
import { PaginatedInput } from '@/commons/pagination/pagination.zod';
import { Searcher } from '@/modules/searcher/searcher.model';
import { TasksRepository } from '@/modules/tasks/persistence/prisma/tasks.repository';
import { TasksProcessors } from '@/modules/tasks/processors/tasks-processors.constants';
import { TasksRouterService } from '@/modules/tasks/processors/tasks-router.service';
import { Tasks } from '@/modules/tasks/tasks.model';

@Injectable()
export class TasksService {
  private readonly LOG = new Logger(TasksService.name);
  private static readonly IN_FLIGHT_FILTER: Tasks.ListFilters = {
    status: [Tasks.Status.Pending, Tasks.Status.Processing],
  };

  constructor(
    private readonly tasksRepository: TasksRepository,
    private readonly tasksRouterService: TasksRouterService,
  ) {}

  public async submitBatch(
    organizationId: string,
    serviceAccountId: string,
    requestId: string,
    data: Array<Tasks.Submission>,
    skipWalletDebit = false,
  ): Promise<Array<Tasks.Model>> {
    await this.enforceQueueLimit(organizationId, data.length);
    const tasks = await this.tasksRepository.create(
      this.createTasksBatch(organizationId, requestId, serviceAccountId, data),
    );
    const taskJobs = await this.tasksRouterService.enqueueTasks(tasks, skipWalletDebit);
    const failures = taskJobs.flatMap((job, index) =>
      job.status === 'rejected'
        ? [
            {
              reason: job.reason instanceof Error ? job.reason.message : String(job.reason),
              taskId: tasks[index].id,
            },
          ]
        : [],
    );

    if (failures.length > 0) {
      const errorLog = failures
        .map(({ taskId, reason }) => `Task ${taskId} failed: ${reason}`)
        .join('\n');

      this.LOG.error(errorLog);
      await this.markFailed(
        failures.map(({ taskId }) => taskId),
        'Task submission failed',
      );
    }

    return tasks;
  }

  public getByIdAndOrganizationId(taskId: string, organizationId: string): Promise<Tasks.Model> {
    return this.tasksRepository
      .findOneByIdAndOrganizationId(taskId, organizationId)
      .then(task => task.orElseThrow(() => new Tasks.NotFoundError(taskId)));
  }

  public async listByOrganizationId(
    organizationId: string,
    options: PaginatedInput & Tasks.ListFilters,
  ): Promise<{ inFlight: number; limit: number; tasks: Array<Tasks.Model>; total: number }> {
    const [tasks, total, inFlight] = await Promise.all([
      this.tasksRepository.findByOrganizationId(organizationId, options),
      this.tasksRepository.countByOrganizationId(organizationId, options),
      this.tasksRepository.countByOrganizationId(organizationId, TasksService.IN_FLIGHT_FILTER),
    ]);

    return {
      inFlight,
      limit: TasksProcessors.MAX_JOBS_PER_ORGANIZATION,
      tasks,
      total,
    };
  }

  public markProcessing(taskIds: Array<string>): Promise<void> {
    return this.tasksRepository.updateStatusByIds(taskIds, {
      fromStatus: Tasks.Status.Pending,
      toStatus: Tasks.Status.Processing,
    });
  }

  public markCompleted(taskIds: Array<string>, output: Record<string, unknown>): Promise<void> {
    return this.tasksRepository.updateStatusByIds(taskIds, {
      fromStatus: Tasks.Status.Processing,
      output,
      toStatus: Tasks.Status.Completed,
    });
  }

  public markFailed(taskIds: Array<string>, error: string): Promise<void> {
    return this.tasksRepository.setFailedStatus(taskIds, error);
  }

  private countByOrganizationId(
    organizationId: string,
    filter?: Tasks.ListFilters,
  ): Promise<number> {
    return this.tasksRepository.countByOrganizationId(organizationId, filter);
  }

  private async enforceQueueLimit(
    organizationId: string,
    incomingBatchSize: number,
  ): Promise<void> {
    const pendingTasksCount = await this.countByOrganizationId(
      organizationId,
      TasksService.IN_FLIGHT_FILTER,
    );
    const availableSlots = Math.max(
      0,
      TasksProcessors.MAX_JOBS_PER_ORGANIZATION - pendingTasksCount,
    );

    if (incomingBatchSize > availableSlots) {
      throw new TasksProcessors.QueueLimitExceededError(availableSlots);
    }
  }

  private getTaskDefaultProperties(
    organizationId: string,
    requestId: string,
    serviceAccountId: string,
  ) {
    return {
      organizationId,
      requestId,
      serviceAccountId,
      status: Tasks.Status.Pending,
    };
  }

  private getResearchTaskDefaultProperties() {
    return {
      depth: Searcher.SearchDepth.Research,
      includeInlineCitations: true,
      includeSources: false,
      maxResults: undefined,
    };
  }

  private createTasksBatch(
    organizationId: string,
    requestId: string,
    serviceAccountId: string,
    data: Array<Tasks.Submission>,
  ): Array<Tasks.Create> {
    return data.map(task => this.createTask(organizationId, requestId, serviceAccountId, task));
  }

  private createTask(
    organizationId: string,
    requestId: string,
    serviceAccountId: string,
    task: Tasks.Submission,
  ): Tasks.Create {
    const defaultProperties = this.getTaskDefaultProperties(
      organizationId,
      requestId,
      serviceAccountId,
    );

    switch (task.type) {
      case Tasks.Type.Search:
        return {
          ...defaultProperties,
          input: task.input,
          type: task.type,
        };
      case Tasks.Type.Fetch:
        return {
          ...defaultProperties,
          input: task.input,
          type: task.type,
        };
      case Tasks.Type.Research:
        return {
          ...defaultProperties,
          input: {
            ...task.input,
            ...this.getResearchTaskDefaultProperties(),
            researchDepth: task.input.depth ?? Searcher.ResearchDepth.L,
            researchMode: task.input.mode,
          },
          type: task.type,
        };
    }
  }
}
