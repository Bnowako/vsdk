from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from vsdk.tts.ElevenTTSProcessor import AudioChunk


class BaseTTS(ABC):
    @abstractmethod
    def __call__(
        self, input_generator: AsyncIterator[str]
    ) -> AsyncIterator[AudioChunk]:
        pass
