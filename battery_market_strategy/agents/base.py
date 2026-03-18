from __future__ import annotations

from abc import ABC, abstractmethod

from ..state_models import GraphState


class BaseAgent(ABC):
    name: str

    @abstractmethod
    def run(self, state: GraphState) -> dict:
        raise NotImplementedError

