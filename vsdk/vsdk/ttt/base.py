from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import AsyncIterator, Optional

from vsdk.stt.domain import STTResult
from vsdk.ttt.domain import LLMResult


class BaseAgent(ABC):
    @abstractmethod
    def __call__(
        self,
        stt_result: STTResult,
        conversation_id: str,
        callback: Optional[Callable[[LLMResult], None]] = None,
    ) -> AsyncIterator[str]:
        pass
