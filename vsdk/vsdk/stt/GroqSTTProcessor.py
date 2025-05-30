import time
import wave
from io import BytesIO

from vsdk.config import Config
from vsdk.stt.base import BaseSTT, STTResult


class GroqSTTProcessor(BaseSTT):
    def __init__(
        self,
        groq: Config.Groq,
    ):
        self.groq = groq

    async def __call__(self, pcm_audio: bytes) -> STTResult:
        return await self.speech_to_text(pcm_audio)

    async def speech_to_text(self, pcm_audio: bytes) -> STTResult:
        stt_start_time = time.time()
        wav_io = BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(self.groq.audio_channels)
            wav_file.setsampwidth(self.groq.bytes_per_sample)
            wav_file.setframerate(self.groq.sample_rate)
            wav_file.writeframes(pcm_audio)
        wav_io.seek(0)

        transcription = await self.groq.async_client.audio.transcriptions.create(
            file=("audio.wav", wav_io),
            model=self.groq.transcription_model,
            language=self.groq.transcription_language,
        )
        stt_end_time = time.time()

        return STTResult(
            stt_start_time=stt_start_time,
            stt_end_time=stt_end_time,
            transcript=transcription.text,
            speech_file=wav_io.getvalue(),
        )
