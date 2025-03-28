from pydantic import BaseModel


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
