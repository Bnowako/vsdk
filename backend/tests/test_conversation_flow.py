import asyncio
import logging
import time
from pathlib import Path
from typing import Any, AsyncIterator, Generator
from unittest.mock import MagicMock, patch

import pytest
from app.voice_agent.conversation_orchestrator import ConversationOrchestrator
from app.voice_agent.domain import RespondToHumanResult
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
def mock_voice_agent() -> Generator[MagicMock, None, None]:
    """
    Sets up a mock for the VoiceAgent's respond_to_human method and yields it.
    The mock is automatically stopped after the test.
    """
    mock_agent = MagicMock()

    async def mock_respond_to_human(
        *args: Any, **kwargs: Any
    ) -> AsyncIterator[AudioChunk]:
        result = RespondToHumanResult.empty()
        result.stt_result = STTResult(
            stt_start_time=time.time(),
            stt_end_time=time.time(),
            transcript="test transcript",
            speech_file=b"mock_speech_file",
        )
        yield AudioChunk(
            audio=b"synthetic_audio_data",
            base64_audio="base64_encoded_audio",
            normalized_alignment=None,
        )
        kwargs["callback"](result)

    mock_agent.respond_to_human.side_effect = mock_respond_to_human

    with patch("app.voice_agent.voice_agent.VoiceAgent", return_value=mock_agent):
        yield mock_agent


@pytest.mark.asyncio
async def test_agent_should_detect_speech_and_respond_to_human(
    mock_voice_agent: MagicMock,
):
    """
    Test that when a human speaks while the agent is not talking, the agent detects the speech,
    transcribes it, and responds appropriately.

    The test audio file (8 seconds long) has:
      - 00:00 - 01:18: Silence
      - 01:18 - 03:90: Speech ("chciałbym umówić się do lekarza rodzinnego")
      - 03:90 - 08:05: Silence

    Expectations:
      - The voice agent's respond_to_human method is called with the correct audio segment.
      - The callback is invoked with the appropriate result.
    """

    pcm_data = read_wav_to_pcm("single_speech.wav")
    pcm_data_expected = read_wav_to_pcm("single_speech_expected.wav")

    orchestrator = ConversationOrchestrator(
        conversation_id="test_conversation",
        callback=lambda x: asyncio.sleep(0),
        voice_agent=mock_voice_agent,
    )

    try:
        send_audio(pcm_data, orchestrator)
        await asyncio.sleep(0.1)

        mock_voice_agent.respond_to_human.assert_called_once()
        transcribed_audio = mock_voice_agent.respond_to_human.call_args.kwargs[
            "pcm_audio_buffer"
        ]

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

    finally:
        orchestrator.end_conversation()
