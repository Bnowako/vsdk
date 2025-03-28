from pydantic import BaseModel

from vsdk.stt.domain import STTResult
from vsdk.tts.domain import TTSResult
from vsdk.ttt.domain import LLMResult


class RespondToHumanResult(BaseModel):
    stt_result: STTResult
    llm_result: LLMResult
    tts_result: TTSResult

    @classmethod
    def empty(cls) -> "RespondToHumanResult":
        return cls(
            stt_result=STTResult.empty(),
            llm_result=LLMResult.empty(),
            tts_result=TTSResult.empty(),
        )

    def update(self, other: "RespondToHumanResult") -> None:
        self.stt_result = other.stt_result
        self.llm_result = other.llm_result
        self.tts_result = other.tts_result
