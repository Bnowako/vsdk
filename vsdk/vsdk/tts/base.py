from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import List, Optional

from pydantic import BaseModel


class NormalizedAlignment(BaseModel):
    chars: List[str]
    charStartTimesMs: List[int]
    charDurationsMs: List[int]


class AudioChunk(BaseModel):
    audio: bytes
    base64_audio: str
    normalized_alignment: Optional[NormalizedAlignment]


class BaseTTS(ABC):
    @abstractmethod
    def __call__(
        self, input_generator: AsyncIterator[str]
    ) -> AsyncIterator[AudioChunk]:
        pass
