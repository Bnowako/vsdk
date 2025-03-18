"""
TODO This class needs refactoring!!!
"""

import logging
from typing import Dict

import numpy as np
import torch
from numpy.typing import NDArray
from pydantic import BaseModel
from silero_vad import VADIterator, load_silero_vad  # type: ignore
from silero_vad.utils_vad import OnnxWrapper  # type: ignore
from torch import Tensor

from vsdk.config import Config

logger = logging.getLogger(__name__)


class VADResult(BaseModel):
    start_sample: int
    end_sample: int | None
    ended: bool
    interruption_duration_ms: int
    sample_rate: int

    def is_shorter_than(self, ms: int) -> bool:
        if self.end_sample is None:
            return False

        ms_in_s = 1000
        samples_per_ms = self.sample_rate / ms_in_s
        duration_samples = self.end_sample - self.start_sample
        duration_ms = duration_samples / samples_per_ms

        return duration_ms < ms

    def is_short(self):
        return self.is_shorter_than(self.interruption_duration_ms)

    def is_long(self):
        return not self.is_short()


class VAD:
    def __init__(self, id: str, audio_config: Config.Audio):
        logger.debug(f"Creating NEW VADIterator for {id}")

        self.id = id
        self.audio_config = audio_config
        model: OnnxWrapper = (  # type: ignore
            load_silero_vad()
        )  # Load the Silero VAD model
        self.vad_iterator = VADIterator(
            model=model,
            threshold=self.audio_config.silero_threshold,
            sampling_rate=self.audio_config.sample_rate,
            min_silence_duration_ms=self.audio_config.silero_min_silence_duration_ms,
        )

        self.speech_dict: Dict[str, int] = {}

    def silero_iterator(self, pcm_audio: bytes) -> VADResult | None:
        # Silero vad works on fixed sample sizes. Most comonly  512 if sampling_rate == 16000 else 256
        # So in our case (Twilio sends us 8KHz audio) it will be 256 samples
        # This corresponds to 32ms of data 256 samples for 8000 samples/second (256 samples/8000 sample rate* 1 second * 1000 ms)
        # 256 samples of 16-bit audio is 512 bytes, so this function should ingest only multiply of 512 bytes
        window_size = self.audio_config.silero_samples_size
        audio_array: NDArray[np.float32] = (
            np.frombuffer(pcm_audio, dtype=np.int16).astype(np.float32) / 32768.0
        )
        audio_tensor: Tensor = torch.tensor(audio_array)

        if len(audio_tensor) % window_size != 0:
            raise ValueError(
                f"Audio data needs to be multiply of {window_size} samples for 8kHz audio"
            )

        for i in range(0, len(audio_tensor), window_size):
            chunk = audio_tensor[i : i + window_size]
            if len(chunk) < window_size:
                raise ValueError(
                    f"Audio data needs to be multiply of {window_size} samples for 8kHz audio"
                )  # This is checked before, but let's leave this line in case somebody removes the upper part :D

            result: dict[str, int] | None = self.vad_iterator(
                x=chunk, return_seconds=False
            )  # type: ignore return_seconds = False implies int as a return type
            if result:
                if "start" in result:
                    self.speech_dict["start"] = result["start"]
                if "end" in result:
                    self.speech_dict["end"] = result["end"]

        if self.speech_dict:
            vad_result = VADResult(
                start_sample=self.speech_dict["start"],
                end_sample=self.speech_dict.get("end", None),
                ended="end" in self.speech_dict,
                interruption_duration_ms=self.audio_config.interruption_duration_ms,
                sample_rate=self.audio_config.sample_rate,
            )

            if "end" in self.speech_dict:
                logger.debug(f"🧠Reset VADIterator for {self.id}")

                self.vad_iterator.reset_states()
                self.speech_dict.clear()

            return vad_result
        else:
            return None
