from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResult:
    text: str


class LLMAdapter(ABC):
    @abstractmethod
    def chat(self, messages: list[dict]) -> LLMResult:
        ...
