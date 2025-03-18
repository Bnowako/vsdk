import asyncio
import base64
import json
import logging
from typing import AsyncIterator

import websockets

from vsdk.config import Config
from vsdk.tts.base import AudioChunk, BaseTTS, NormalizedAlignment

# Set up logger
logger = logging.getLogger(__name__)


class ElevenTTSProcessor(BaseTTS):
    def __init__(
        self,
        eleven: Config.Eleven,
    ):
        self.eleven = eleven
        logger.info(f"Initialized ElevenTTSProcessor with voice ID: {eleven.voice}")

    def __call__(
        self, input_generator: AsyncIterator[str]
    ) -> AsyncIterator[AudioChunk]:
        logger.debug("Starting text-to-speech streaming via websocket")
        return self.text_to_speech_streaming_ws(input_generator)

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
                                "xi_api_key": self.eleven.api_key,
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
                            except websockets.exceptions.ConnectionClosed as e:
                                logger.error(
                                    "Websocket connection closed unexpectedly",
                                    exc_info=e,
                                )
                                break
                            except Exception as e:
                                logger.error("Error in websocket listener", exc_info=e)
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
                    break

                whole_audio += audio_chunk.audio
                yield audio_chunk

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
