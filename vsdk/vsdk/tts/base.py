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


class TTSResult(BaseModel):
    start_time: float
    end_time: float
    first_chunk_time: float
    response: str

    @classmethod
    def empty(cls) -> "TTSResult":
        return cls(start_time=0, end_time=0, first_chunk_time=0, response="")
