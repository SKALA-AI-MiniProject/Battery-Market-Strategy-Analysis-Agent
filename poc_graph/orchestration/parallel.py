from __future__ import annotations

import logging

from ..state_models import GraphState

logger = logging.getLogger(__name__)


class InitialParallelFanOut:
    name = "initial_parallel_fanout"

    def run(self, state: GraphState) -> dict:
        logger.info("Entering initial parallel fan-out")
        return {}


class InitialParallelJoin:
    name = "initial_parallel_join"

    def run(self, state: GraphState) -> dict:
        logger.info("Joining initial parallel phase")
        return {}


class SWOTParallelFanOut:
    name = "swot_parallel_fanout"

    def run(self, state: GraphState) -> dict:
        logger.info("Entering SWOT parallel fan-out")
        return {}


class SWOTParallelJoin:
    name = "swot_parallel_join"

    def run(self, state: GraphState) -> dict:
        logger.info("Joining SWOT parallel phase")
        return {}
