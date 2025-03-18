import asyncio
import base64
import dataclasses
import json
import wave
from io import BytesIO
from typing import Iterator, AsyncGenerator, List, Tuple, Optional

import websockets
from groq.types.audio import Transcription

from app.config import Config, Secrets


@dataclasses.dataclass
class NormalizedAlignment:
    chars: List[str]
    charStartTimesMs: List[int]
    charDurationsMs: List[int]


@dataclasses.dataclass
class AudioChunk:
    audio: bytes
    normalized_alignment: Optional[NormalizedAlignment]


def calculate_word_start_times(
    full_alignment: NormalizedAlignment,
) -> List[Tuple[str, int]]:
    zipped_start_times = list(
        zip(full_alignment.chars, full_alignment.charStartTimesMs)
    )

    start_times = []
    for i, (char, start_time) in enumerate(zipped_start_times):
        if i != 0 and zipped_start_times[i - 1][0] == " ":
            start_times.append((char, start_time))

    return start_times


def split_by_words_or_by_fixed_interval_if_silence(audio_chunk: AudioChunk):
    if audio_chunk.normalized_alignment is None:
        chunk_size = 500 * 2
        for i in range(0, len(audio_chunk.audio), chunk_size):
            yield audio_chunk.audio[i : i + chunk_size]

    if audio_chunk.normalized_alignment is None:
        return

    word_start_times = calculate_word_start_times(audio_chunk.normalized_alignment)

    for idx, wst in enumerate(word_start_times):
        bytes_offset = wst[1] * 2
        next_word_start = (
            word_start_times[idx + 1][1] * 2
            if idx + 1 < len(word_start_times)
            else len(audio_chunk.audio)
        )
        yield audio_chunk.audio[bytes_offset:next_word_start]

#todo THIS FAILS REALLY QUIETLY IF THERE ARE SOME ISSUES WITH ELEVEN API, FIX THIS!!!!
# to reproduce for example break api key
class VoiceAgent:
    def __init__(self, eleven=Config.Eleven, groq=Config.Groq, async_groq=Config.Groq):
        self.eleven = eleven
        self.groq = groq
        self.async_groq = async_groq

    async def speech_to_text(self, pcm_audio: bytes) -> (Transcription, bytes):
        wav_io = BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(Config.Audio.channels)
            wav_file.setsampwidth(Config.Audio.bytes_per_sample)
            wav_file.setframerate(Config.Audio.sample_rate)
            wav_file.writeframes(pcm_audio)
        wav_io.seek(0)

        transcription = await self.async_groq.async_client.audio.transcriptions.create(
            file=("audio.wav", wav_io),
            model=self.groq.transcription_model,
            prompt="Audio klip jest częścią konwersacji w której pacjent dzwoni do lekarza rodzinnego",
            language=self.groq.transcription_language,
        )

        return transcription, wav_io.getvalue()

    def text_to_speech_streaming(self, text: str) -> Iterator[bytes]:
        response = self.eleven.client.text_to_speech.convert_as_stream(
            voice_id=self.eleven.voice,
            optimize_streaming_latency="0",
            output_format=self.eleven.output_format,
            text=text,
            model_id=self.eleven.model,
        )
        return response

    async def text_to_speech_streaming_ws(
        self, input_generator: AsyncGenerator[str, None]
    ):
        audio_queue = asyncio.Queue()

        async def send_and_listen():
            uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{self.eleven.voice}/stream-input?model_id=eleven_turbo_v2_5&output_format=ulaw_8000&language_code=pl"

            async with websockets.connect(uri) as websocket:
                await websocket.send(
                    json.dumps(
                        {
                            "text": " ",
                            "voice_settings": {
                                "stability": 0.5,
                                "similarity_boost": 0.8,
                            },
                            "xi_api_key": Secrets.ELEVENLABS_API_KEY,
                        }
                    )
                )

                async def listen():
                    while True:
                        try:
                            message = await websocket.recv()
                            data = json.loads(message)
                            if data.get("audio"):
                                audio_data = base64.b64decode(data["audio"])
                                alignment = None
                                if data.get("normalizedAlignment"):
                                    normalized_alignment = data["normalizedAlignment"]
                                    alignment = NormalizedAlignment(
                                        chars=normalized_alignment["chars"],
                                        charStartTimesMs=normalized_alignment[
                                            "charStartTimesMs"
                                        ],
                                        charDurationsMs=normalized_alignment[
                                            "charDurationsMs"
                                        ],
                                    )

                                await audio_queue.put(
                                    AudioChunk(
                                        audio=audio_data, normalized_alignment=alignment
                                    )
                                )
                            elif data.get("isFinal"):
                                break
                        except websockets.exceptions.ConnectionClosed:
                            break
                    # Signal that we're done
                    await audio_queue.put(None)

                listen_task = asyncio.create_task(listen())

                async for text in self._text_chunker(input_generator):
                    await websocket.send(json.dumps({"text": text}))

                await websocket.send(json.dumps({"text": ""}))
                await listen_task

        send_task = asyncio.create_task(send_and_listen())

        while True:
            audio_chunk = await audio_queue.get()
            if audio_chunk is None:
                break
            yield audio_chunk.audio
            #TODO uncomment this
            # for word_audio_chunk in split_by_words_or_by_fixed_interval_if_silence(
            #     audio_chunk
            # ):
            #     yield word_audio_chunk

        await send_task  # Ensure send_and_listen() completes

    async def _text_chunker(self, chunks: AsyncGenerator[str, None]):
        """Split text into chunks, ensuring to not break sentences."""
        splitters = (
            ".",
            ",",
            "?",
            "!",
            ";",
            ":",
            "—",
            "-",
            "(",
            ")",
            "[",
            "]",
            "}",
            " ",
        )
        buffer = ""

        async for text in chunks:
            if buffer.endswith(splitters):
                yield buffer + " "
                buffer = text
            elif text.startswith(splitters):
                yield buffer + text[0] + " "
                buffer = text[1:]
            else:
                buffer += text

        if buffer:
            yield buffer + " "
