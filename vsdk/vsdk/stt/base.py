from abc import ABC, abstractmethod

from vsdk.stt.domain import STTResult


class BaseSTT(ABC):
    @abstractmethod
    async def __call__(self, pcm_audio: bytes) -> STTResult:
        pass

    @abstractmethod
    async def speech_to_text(self, pcm_audio: bytes) -> STTResult:
        pass
