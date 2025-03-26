import asyncio
import logging
import time
from pathlib import Path
from typing import Any, AsyncIterator, Generator, Tuple
from unittest.mock import MagicMock, patch

import pytest
from app.voice_agent.stt.domain import STTResult
from app.voice_agent.tts.ElevenTTSProcessor import AudioChunk

logger = logging.getLogger(__name__)

# Constants for readability
WAV_HEADER_SIZE = 44
CHUNK_DURATION_MS = 20
SAMPLE_RATE_KHZ = 8  # in kHz
BYTES_PER_SAMPLE = 2
CHUNK_SIZE = CHUNK_DURATION_MS * SAMPLE_RATE_KHZ
TESTS_DIR = Path.cwd() / "tests" / "resources"


def read_wav_to_pcm(file_name: str) -> bytes:
    """
    Reads a WAV file and returns its PCM data (skipping the header).

    Args:
        file_path: The path to the WAV file.

    Returns:
        The raw PCM data as bytes.
    """
    file_path = TESTS_DIR / file_name
    try:
        with file_path.open("rb") as wav_file:
            wav_file.seek(WAV_HEADER_SIZE)
            return wav_file.read()
    except Exception as e:
        logger.error(f"Error reading WAV file {file_path}: {e}")
        raise


def send_audio(audio: bytes, orchestrator: Any) -> None:
    """
    Sends audio data in chunks to the given orchestrator.

    Args:
        audio: The complete audio data in bytes.
        orchestrator: The target orchestrator to receive audio chunks.
    """
    for i in range(0, len(audio), CHUNK_SIZE):
        chunk = audio[i : i + CHUNK_SIZE]
        orchestrator.audio_received(chunk)


@pytest.fixture
def external_patches() -> Generator[Tuple[MagicMock, MagicMock, MagicMock], None, None]:
    """
    Sets up external patches for STT, TTT, and TTS components and yields them.
    The patches are automatically stopped after the test.
    """
    mock_stt = MagicMock()

    async def mock_stt_async(*args, **kwargs):  # type: ignore
        return STTResult(
            stt_start_time=time.time(),
            stt_end_time=time.time(),
            transcript="test transcript",
            speech_file=b"mock_speech_file",
        )

    mock_stt.side_effect = mock_stt_async

    mock_ttt = MagicMock()

    async def mock_astream(*args, **kwargs):  # type: ignore
        yield "Ok, pomogę ci umówić wizytę."

    mock_ttt.return_value = mock_astream()

    mock_tts = MagicMock()

    async def mock_tts_stream(input_generator: AsyncIterator[str]):
        async for text in input_generator:
            yield AudioChunk(
                audio=b"synthetic_audio_data " + text.encode("utf-8"),
                base64_audio="base64_encoded_audio",
                normalized_alignment=None,
            )

    mock_tts.side_effect = mock_tts_stream

    patches = [
        patch(
            "app.voice_agent.stt.GroqSTTProcessor.GroqSTTProcessor",
            return_value=mock_stt,
        ),
        patch("app.voice_agent.ttt.OpenAIAgent.OpenAIAgent", return_value=mock_ttt),
        patch(
            "app.voice_agent.tts.ElevenTTSProcessor.ElevenTTSProcessor",
            return_value=mock_tts,
        ),
    ]
    for p in patches:
        p.start()

    yield mock_stt, mock_ttt, mock_tts

    for p in patches:
        p.stop()


@pytest.mark.asyncio
async def test_agent_should_detect_speech_and_respond_to_human(
    external_patches: Tuple[MagicMock, MagicMock, MagicMock],
):
    """
    Test that when a human speaks while the agent is not talking, the agent detects the speech,
    transcribes it, and responds appropriately.

    The test audio file (8 seconds long) has:
      - 00:00 - 01:18: Silence
      - 01:18 - 03:90: Speech ("chciałbym umówić się do lekarza rodzinnego")
      - 03:90 - 08:05: Silence

    Expectations:
      - The STT process is invoked with approximately the correct audio segment.
      - The language model (TTT) and TTS are called to generate a response.
    """

    pcm_data = read_wav_to_pcm("single_speech.wav")
    pcm_data_expected = read_wav_to_pcm("single_speech_expected.wav")
    mock_stt, mock_ttt, mock_tts = external_patches

    from app.voice_agent.conversation_orchestrator import ConversationOrchestrator

    orchestrator = ConversationOrchestrator(
        conversation_id="test_conversation",
        callback=lambda x: asyncio.sleep(0),
    )

    try:
        # Act: send the audio and allow asynchronous processes to run briefly
        send_audio(pcm_data, orchestrator)
        await asyncio.sleep(0.1)

        # Assert: verify that STT was called correctly
        mock_stt.assert_called_once()
        transcribed_audio = mock_stt.call_args[0][0]

        assert pcm_data_expected in transcribed_audio, (
            "Expected speech segment not found in transcribed audio."
        )

        allowable_diff = 200 * SAMPLE_RATE_KHZ * BYTES_PER_SAMPLE
        assert abs(len(transcribed_audio) - len(pcm_data_expected)) <= allowable_diff, (
            "Transcribed audio length difference exceeds allowed threshold."
        )
        logger.info(
            f"Transcribed audio length difference: {abs(len(transcribed_audio) - len(pcm_data_expected)) / (SAMPLE_RATE_KHZ * BYTES_PER_SAMPLE)} samples"
        )

        # Assert: verify that both TTT and TTS were invoked exactly once
        mock_ttt.assert_called_once()
        mock_tts.assert_called_once()

    finally:
        orchestrator.end_conversation()
