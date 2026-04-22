from linkup_brain import constants, enums

EXECUTOR_SOFT_TIMEOUT_BY_DEPTH: dict[enums.ResearchDepth, int] = {
    enums.ResearchDepth.S: 4 * constants.MINUTE_IN_SECONDS,
    enums.ResearchDepth.M: 6 * constants.MINUTE_IN_SECONDS,
    enums.ResearchDepth.L: 8 * constants.MINUTE_IN_SECONDS,
    enums.ResearchDepth.XL: 12 * constants.MINUTE_IN_SECONDS,
}
