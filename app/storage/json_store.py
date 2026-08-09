from pathlib import Path

from pydantic import BaseModel

from app.storage.store import Store


class JsonStore(Store):
    def __init__(self, data_dir: str):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, model: BaseModel) -> None:
        path = self._data_dir / f"{key}.json"
        path.write_text(model.model_dump_json(indent=2))

    def load(self, key: str, model_cls: type[BaseModel]) -> BaseModel | None:
        path = self._data_dir / f"{key}.json"
        if not path.exists():
            return None
        return model_cls.model_validate_json(path.read_text())
