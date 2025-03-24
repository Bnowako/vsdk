from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import AsyncIterator, Optional

from app.voice_agent.domain import LLMResult, STTResult


class BaseAgent(ABC):
    @abstractmethod
    def __call__(
        self,
        stt_result: STTResult,
        conversation_id: str,
        callback: Optional[Callable[[LLMResult], None]] = None,
    ) -> AsyncIterator[str]:
        pass

    @abstractmethod
    def astream(
        self,
        stt_result: STTResult,
        conversation_id: str,
        callback: Optional[Callable[[LLMResult], None]] = None,
    ) -> AsyncIterator[str]:
        pass
