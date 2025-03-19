from pydantic import BaseModel

from app.voice_agent.stt.domain import STTResult


class LLMResult(BaseModel):
    start_time: float
    end_time: float
    first_chunk_time: float
    response: str

    @classmethod
    def empty(cls) -> "LLMResult":
        return cls(start_time=0, end_time=0, first_chunk_time=0, response="")

    def update(self, other: "LLMResult") -> None:
        self.start_time = other.start_time
        self.end_time = other.end_time
        self.first_chunk_time = other.first_chunk_time
        self.response = other.response


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
