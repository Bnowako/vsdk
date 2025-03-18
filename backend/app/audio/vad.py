import logging

import dataclasses

import numpy as np
import torch
from silero_vad import load_silero_vad, VADIterator  # type: ignore
from silero_vad.utils_vad import OnnxWrapper  # type: ignore
from torch import Tensor
from app.config import Config
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class VADResult:
    start_sample: int | float
    end_sample: int | float | None
    ended: bool

    def is_shorter_than(self, ms: int) -> bool:
        if self.end_sample is None:
            return False

        ms_in_s = 1000
        samples_per_ms = Config.Audio.sample_rate / ms_in_s
        duration_samples = self.end_sample - self.start_sample
        duration_ms = duration_samples / samples_per_ms

        return duration_ms < ms

    def is_short(self):
        return self.is_shorter_than(Config.Audio.interruption_duration_ms)

    def is_long(self):
        return not self.is_short()


# todo extract to class and add remove vad_iterator and speech dict after thread connection for sid is closed

# A global dictionary to store VADIterator instances per sid
vad_iterator_dict: dict[str, VADIterator] = {}
vad_speech_dict: dict[str, dict[str, int | float]] = {}


def silero_iterator(pcm_audio: bytes, sid: str) -> VADResult | None:
    # Silero vad works on fixed sample sizes. Most comonly  512 if sampling_rate == 16000 else 256
    # So in our case (Twilio sends us 8KHz audio) it will be 256 samples
    # This corresponds to 32ms of data 256 samples for 8000 samples/second (256 samples/8000 sample rate* 1 second * 1000 ms)
    # 256 samples of 16-bit audio is 512 bytes, so this function should ingest only multiply of 512 bytes
    window_size = Config.Audio.silero_samples_size
    audio_array: NDArray[np.float32] = (
        np.frombuffer(pcm_audio, dtype=np.int16).astype(np.float32) / 32768.0
    )
    audio_tensor: Tensor = torch.tensor(audio_array)

    if len(audio_tensor) % window_size != 0:
        raise ValueError(
            f"Audio data needs to be multiply of {window_size} samples for 8kHz audio"
        )

    if sid not in vad_iterator_dict:
        logger.debug(f"Creating NEW VADIterator for sid: {sid}")
        model: OnnxWrapper = (
            load_silero_vad()
        )  # Load the Silero VAD model # type: ignore
        vad_iterator = VADIterator(
            model=model,
            threshold=Config.Audio.silero_threshold,
            sampling_rate=Config.Audio.sample_rate,
            min_silence_duration_ms=Config.Audio.silero_min_silence_duration_ms,
        )
        vad_iterator_dict[sid] = vad_iterator
    else:
        vad_iterator: VADIterator = vad_iterator_dict[sid]
        logger.debug("✨Using existing VADIterator")

    if sid not in vad_speech_dict:
        vad_speech_dict[sid] = {}
    speech_dict = vad_speech_dict[sid]

    for i in range(0, len(audio_tensor), window_size):
        chunk = audio_tensor[i : i + window_size]
        if len(chunk) < window_size:
            raise ValueError(
                f"Audio data needs to be multiply of {window_size} samples for 8kHz audio"
            )  # This is checked before, but let's leave this line in case somebody removes the upper part :D

        result = vad_iterator(chunk)
        if result:
            if "start" in result:
                speech_dict["start"] = result["start"]
            if "end" in result:
                speech_dict["end"] = result["end"]

    if speech_dict:
        vad_result = VADResult(
            start_sample=speech_dict["start"],
            end_sample=speech_dict.get("end", None),
            ended="end" in speech_dict,
        )

        if "end" in speech_dict:
            logger.debug(f"🧠Reset VADIterator for sid: {sid}")

            vad_iterator.reset_states()
            speech_dict.clear()

        return vad_result
    else:
        return None
