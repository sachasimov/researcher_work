import { Injectable } from '@nestjs/common';
import Decimal from 'decimal.js';
import { Request } from 'express';
import { CostProvider } from '@/commons/interfaces/cost-provider';
import { Searcher } from '@/modules/searcher/searcher.model';

@Injectable()
export class ResearchCostProvider extends CostProvider {
  getCost(request: Request): Decimal {
    const depth = request.body?.depth as Searcher.ResearchDepth | undefined;
    if (depth && depth in Searcher.researchCost) {
      return Searcher.researchCost[depth];
    }
    return Searcher.researchCost[Searcher.ResearchDepth.L];
  }
}
