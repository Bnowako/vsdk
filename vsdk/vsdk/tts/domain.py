from pydantic import BaseModel


class TTSResult(BaseModel):
    start_time: float
    end_time: float
    first_chunk_time: float
    response: str

    @classmethod
    def empty(cls) -> "TTSResult":
        return cls(start_time=0, end_time=0, first_chunk_time=0, response="")
