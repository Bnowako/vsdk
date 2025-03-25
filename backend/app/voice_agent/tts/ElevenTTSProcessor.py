import asyncio
import base64
import dataclasses
import json
import logging
from typing import AsyncIterator, Iterator, List, Optional, Tuple

import websockets

from app.config import Config, Secrets

# Set up logger
logger = logging.getLogger(__name__)


@dataclasses.dataclass
class NormalizedAlignment:
    chars: List[str]
    charStartTimesMs: List[int]
    charDurationsMs: List[int]


@dataclasses.dataclass
class AudioChunk:
    audio: bytes
    base64_audio: str
    normalized_alignment: Optional[NormalizedAlignment]


def calculate_word_start_times(
    full_alignment: NormalizedAlignment,
) -> List[Tuple[str, int]]:
    zipped_start_times = list(
        zip(full_alignment.chars, full_alignment.charStartTimesMs)
    )

    start_times: List[Tuple[str, int]] = []
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


# todo THIS FAILS REALLY QUIETLY IF THERE ARE SOME ISSUES WITH ELEVEN API, FIX THIS!!!!
# to reproduce for example break api key
class ElevenTTSProcessor:
    def __init__(
        self,
        eleven: Config.Eleven = Config.Eleven(),
    ):
        self.eleven = eleven
        logger.info(f"Initialized ElevenTTSProcessor with voice ID: {eleven.voice}")

    def __call__(
        self, input_generator: AsyncIterator[str]
    ) -> AsyncIterator[AudioChunk]:
        logger.debug("Starting text-to-speech streaming via websocket")
        return self.text_to_speech_streaming_ws(input_generator)

    def text_to_speech_streaming(self, text: str) -> Iterator[bytes]:
        logger.debug(f"Converting text to speech using REST API: {text[:100]}...")
        try:
            response = self.eleven.client.text_to_speech.convert_as_stream(
                voice_id=self.eleven.voice,
                optimize_streaming_latency="0",
                output_format=self.eleven.output_format,
                text=text,
                model_id=self.eleven.model,
            )
            return response
        except Exception as e:
            logger.error(f"Error in text_to_speech_streaming: {str(e)}")
            raise

    async def text_to_speech_streaming_ws(
        self, input_generator: AsyncIterator[str]
    ) -> AsyncIterator[AudioChunk]:
        logger.debug("Starting websocket streaming session")
        audio_queue: asyncio.Queue[AudioChunk | None] = asyncio.Queue()

        async def send_and_listen():
            uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{self.eleven.voice}/stream-input?model_id={self.eleven.model}&output_format={self.eleven.output_format}&language_code={self.eleven.language}&enable_logging=true"
            logger.info(f"Connecting to websocket at: {uri}")

            try:
                async with websockets.connect(uri) as websocket:
                    logger.debug("Websocket connection established")
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
                                    logger.debug("Received audio chunk")
                                    audio_data = base64.b64decode(data["audio"])
                                    alignment = None
                                    if data.get("normalizedAlignment"):
                                        normalized_alignment = data[
                                            "normalizedAlignment"
                                        ]
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
                                            audio=audio_data,
                                            base64_audio=data["audio"],
                                            normalized_alignment=alignment,
                                        )
                                    )
                                elif data.get("isFinal"):
                                    logger.debug("Received final message")
                                    break
                            except websockets.exceptions.ConnectionClosed:
                                logger.error("Websocket connection closed unexpectedly")
                                break
                            except Exception as e:
                                logger.error(f"Error in websocket listener: {str(e)}")
                                break
                        logger.debug("Listener finished, sending None to queue")
                        await audio_queue.put(None)

                    listen_task = asyncio.create_task(listen())

                    async for text in self._text_chunker(input_generator):
                        logger.debug(f"Sending text chunk: {text[:100]}...")
                        await websocket.send(json.dumps({"text": text}))

                    await websocket.send(json.dumps({"text": ""}))
                    await listen_task

            except websockets.exceptions.WebSocketException as e:
                logger.error(f"Websocket connection error: {str(e)}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error in send_and_listen: {str(e)}")
                raise

        send_task = asyncio.create_task(send_and_listen())

        try:
            whole_audio: bytes = b""
            while True:
                audio_chunk = await audio_queue.get()
                if audio_chunk is None:
                    logger.debug("Received None chunk, ending stream")
                    # num_channels = 1  # e.g., 1 for mono, 2 for stereo
                    # sample_width = 2  # in bytes (2 bytes = 16-bit audio)
                    # frame_rate = 16000  # sampling frequency in Hz

                    # # Create a new wave file and write the PCM data
                    # with wave.open("output.wav", "wb") as wav_file:
                    #     wav_file.setnchannels(num_channels)
                    #     wav_file.setsampwidth(sample_width)
                    #     wav_file.setframerate(frame_rate)
                    #     wav_file.writeframes(whole_audio)
                    break
                ## save audio chunk to file
                whole_audio += audio_chunk.audio
                yield audio_chunk

                # TODO uncomment this
                # for word_audio_chunk in split_by_words_or_by_fixed_interval_if_silence(
                #     audio_chunk
                # ):
                #     yield word_audio_chunk

            await send_task
            logger.debug("Streaming session completed successfully")

        except Exception as e:
            logger.error(f"Error in streaming loop: {str(e)}")
            raise

    async def _text_chunker(self, chunks: AsyncIterator[str]):
        """Split text into chunks, ensuring to not break sentences."""
        logger.debug("Starting text chunking")
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
