from abc import ABC, abstractmethod

from pydantic import BaseModel


class Store(ABC):
    @abstractmethod
    def save(self, key: str, model: BaseModel) -> None:
        ...

    @abstractmethod
    def load(self, key: str, model_cls: type[BaseModel]) -> BaseModel | None:
        ...
