from pydantic import BaseModel


class STTResult(BaseModel):
    stt_start_time: float
    stt_end_time: float

    transcript: str
    speech_file: bytes

    @classmethod
    def empty(cls) -> "STTResult":
        return cls(
            stt_start_time=0,
            stt_end_time=0,
            transcript="",
            speech_file=b"",
        )
