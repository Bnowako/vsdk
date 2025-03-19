from pydantic import BaseModel

from app.voice_agent.stt.domain import STTResult
from app.voice_agent.ttt.domain import LLMResult


class TTSResult(BaseModel):
    start_time: float
    end_time: float
    first_chunk_time: float
    response: str

    @classmethod
    def empty(cls) -> "TTSResult":
        return cls(start_time=0, end_time=0, first_chunk_time=0, response="")


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
