"""
TODO This class needs refactoring!!! Mostly hacked audio processing here.
"""

import logging
from asyncio import Task
from enum import Enum
from typing import List

from vsdk.config import Config
from vsdk.vad.vad import VADResult

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    BOTH_SPEAKING = 1
    HUMAN_SILENT = 2
    SHORT_INTERRUPTION_DURING_AGENT_SPEAKING = 3
    LONG_INTERRUPTION_DURING_AGENT_SPEAKING = 4
    SHORT_SPEECH = 5
    LONG_SPEECH = 6
    HUMAN_STARTED_SPEAKING = 7


class AgentSpeechChunk:
    def __init__(self, audio: bytes, mark_id: str):
        self.audio = audio
        self.mark_id = mark_id


class AgentResponseTask:
    def __init__(self, human_speech: bytes, task: Task[None]):
        self.human_speech = human_speech
        self.task = task


class AgentSpeech:
    def __init__(self, speech_chunks: List[AgentSpeechChunk], pointer: int):
        self.speech_chunks = speech_chunks
        self.pointer = 0
        self.stop_sent_at = None

    def mark(self, chunk_idx: int):
        self.pointer = chunk_idx

    def stop_sent(self):
        logger.debug(f"🤖🗣️Stop sent at {self.pointer}")
        if self.stop_sent_at is not None:
            logger.error("Stop sent multiple times, something is wrong")

        self.stop_sent_at = self.pointer

    def get_unspoken(self):
        return self.speech_chunks[self.stop_sent_at :]

    def was_interrupted(self):
        logger.debug(
            f"🤖🗣️Checking speech was interrupted stop sent at: {self.stop_sent_at}"
        )
        return self.stop_sent_at is not None

    def ended(self):
        logger.debug(
            f"🤖🗣️Checking if speech ended. Pointer: {self.pointer}, len: {len(self.speech_chunks)}"
        )
        return (
            len(self.speech_chunks) == 0 or self.pointer == len(self.speech_chunks) - 1
        )


class AgentVoice:
    def __init__(self, id: str):
        self.speeches: List[AgentSpeech] = []
        self.id = id

    @property
    def last_speech(self):
        return self.speeches[-1]

    @property
    def speech_exists(self):
        return len(self.speeches) > 0

    def chunk_sent(self, chunk: bytes):
        mark_id = (
            self.id
            + "_"
            + str(self.speeches_count - 1)
            + "_"
            + str(self.last_speech_chunks_count)
        )
        self.speeches[-1].speech_chunks.append(
            AgentSpeechChunk(audio=chunk, mark_id=mark_id)
        )
        return mark_id

    @property
    def speeches_count(self):
        return len(self.speeches)

    @property
    def last_speech_chunks_count(self):
        return len(self.speeches[-1].speech_chunks)

    def mark_received(self, speech_idx: int, chunk_idx: int):
        if speech_idx != self.speeches_count - 1:
            logger.error("🤖🗣 Received mark for speech that is not the last one")
            return
        self.last_speech.mark(chunk_idx)

    def get_unspoken_chunks(self):
        return self.last_speech.get_unspoken()

    def is_interrupted(self):
        logger.debug(
            f"🤖🗣️Checking if agent was interrupted speech_exists {self.speech_exists}, "
        )
        agent_was_interrupted = (
            self.speech_exists and self.last_speech.was_interrupted()
        )
        return agent_was_interrupted

    def stop_speaking(self):
        self.last_speech.stop_sent()

    def is_speaking(self) -> bool:
        is_agent_speaking = self.speech_exists and not self.last_speech.ended()
        logger.debug(
            f"🤖🗣️Checking if agent is speaking. is_agent_speaking: {is_agent_speaking}"
        )

        return is_agent_speaking

    def new_speech_started(self):
        self.speeches.append(AgentSpeech(speech_chunks=[], pointer=0))
        logger.debug(
            f"🤖🗣️ New agent speech started. Currently {self.speeches_count} speeches."
        )


class HumanVoice:
    def __init__(self):
        self._pcm_audio_buffer: bytes = b""
        self._new_pcm_audio: bytes = b""
        self._last_human_speech: bytes = b""
        self._human_speech_without_response: bytes = b""

    # Human Voice
    def audio_received(self, pcm_audio: bytes) -> None:
        self._new_pcm_audio += pcm_audio
        self._pcm_audio_buffer += pcm_audio
        logger.debug(
            f"👩🏼🗣️ Audio of length: {len(pcm_audio)} received. Updated state {self._state_string()}"
        )

    def clear_human_speech(self):
        logger.debug(f"👩🏼🗣️ Clearing client data state {self._state_string()}")
        self._pcm_audio_buffer = b""

    def get_data_to_process_and_clear(self) -> bytes:
        k = (
            len(self._new_pcm_audio) // Config.Audio.silero_samples_size_bytes
        ) * Config.Audio.silero_samples_size_bytes
        data_to_process = self._new_pcm_audio[:k]
        self._new_pcm_audio = self._new_pcm_audio[k:]
        logger.debug(
            f"✨👩🏼🗣️ Took audio of length: {len(data_to_process)}. Current pcm_audio_buffer length: {len(self._pcm_audio_buffer)}, Current new audio length: {len(self._new_pcm_audio)}"
        )
        return data_to_process

    def human_speech_ended(self, speech_result: VADResult):
        logger.debug("👩🏼🗣️ Human speech ended. ")  # todo add more logs
        if speech_result.end_sample is not None:
            self._last_human_speech = self._get_audio(
                from_sample=speech_result.start_sample,
                to_sample=speech_result.end_sample,
            )
            self.clear_human_speech()
        else:
            logger.error(
                f"👩🏼🗣️ Human speech ended invoked but end_sample is None. start_sample: {speech_result.start_sample}, end_sample: {speech_result.end_sample}"
            )

    def prepare_human_speech_for_interpretation(
        self, human_speech_without_response_buffers: List[bytes]
    ) -> bytes:
        """
        Prepare human speech for interpretation by adding all previous human speeches and last human speech
        This function will cancel all unfinished tasks and add them to the buffer
        :return:
        """
        logger.debug("👩🏼🗣Preparing human speech for interpretation.")

        if human_speech_without_response_buffers:
            human_speech_without_response = (
                (b"\x00" * 2 * 80).join(human_speech_without_response_buffers)
                + b"\x00" * 2 * 80
                + self._last_human_speech
            )
            self._human_speech_without_response = human_speech_without_response
        else:
            self._human_speech_without_response = self._last_human_speech

        return self._human_speech_without_response

    def is_new_audio_ready_to_process(self):
        return len(self._new_pcm_audio) >= Config.Audio.silero_samples_size_bytes

    def get_human_speech_without_response(self):
        return self._human_speech_without_response

    def _get_audio(self, from_sample: int, to_sample: int):
        logger.info(
            f"👩🏼🗣️ Get audio requested, Requested audio length: {(to_sample - from_sample) // Config.Audio.bytes_per_sample / Config.Audio.sample_rate}s. pcm_audio_buffer length: {(len(self._pcm_audio_buffer) // Config.Audio.bytes_per_sample) / Config.Audio.sample_rate}s"
        )
        from_bytes = (
            from_sample * Config.Audio.bytes_per_sample
        )  # 2 bytes per sample for 16-bit audio
        to_bytes = (
            to_sample * Config.Audio.bytes_per_sample
        )  # 2 bytes per sample for 16-bit audio
        return self._pcm_audio_buffer[from_bytes:to_bytes]

    def _state_string(self):
        return f"Conversation state:  new_pcm_audio: {len(self._new_pcm_audio)} pcm_audio_buffer: {len(self._pcm_audio_buffer)} human_speech_without_response: {len(self._human_speech_without_response)}"  # todo add more to this log


class Conversation:
    def __init__(self, id: str):
        self.id = id

        # Audio IN
        self.human_voice = HumanVoice()

        # Thinking
        self.agent_response_tasks: List[AgentResponseTask] = []

        # Audio OUT
        self.agent_voice = AgentVoice(id)

        self.audio_interpreter_loop: Task[None] | None = None

    # Human Voice
    def audio_received(self, pcm_audio: bytes) -> None:
        self.human_voice.audio_received(pcm_audio)

    def clear_human_speech(self) -> None:
        self.human_voice.clear_human_speech()

    def get_data_to_process_and_clear(self):
        return self.human_voice.get_data_to_process_and_clear()

    def human_speech_ended(self, speech_result: VADResult) -> None:
        self.human_voice.human_speech_ended(speech_result=speech_result)

    def is_new_audio_ready_to_process(self):
        return self.human_voice.is_new_audio_ready_to_process()

    def get_human_speech_without_response(self):
        human_speech_without_response_buffers = self._cancel_unfinished_tasks()
        return self.human_voice.prepare_human_speech_for_interpretation(
            human_speech_without_response_buffers=human_speech_without_response_buffers
        )

    # Audio OUT
    def new_agent_speech_start(self):
        self.agent_voice.new_speech_started()

    def agent_speech_sent(self, audio_chunk: bytes) -> str:
        return self.agent_voice.chunk_sent(audio_chunk)

    def agent_speech_marked(self, speech_idx: int, chunk_idx: int):
        self.agent_voice.mark_received(speech_idx, chunk_idx)

    def get_unspoken_agent_speech(self):
        return self.agent_voice.get_unspoken_chunks()

    def agent_was_interrupted(self):
        return self.agent_voice.is_interrupted()

    def stop_speaking_agent(self):
        self.agent_voice.stop_speaking()

    def is_agent_speaking(self) -> bool:
        return self.agent_voice.is_speaking()

    # Thinking
    def add_agent_response_task(self, task: Task[None], invoked_with_speech: bytes):
        logger.debug("🧠 Adding agent response task.")
        self.agent_response_tasks.append(
            AgentResponseTask(task=task, human_speech=invoked_with_speech)
        )

    def _cancel_unfinished_tasks(self) -> List[bytes]:
        """
        Cancel all unfinished tasks and return their human_speech
        :return:
        """
        logger.debug("🧠 Cancelling unfinished tasks.")
        cancelled_speeches: list[bytes] = []
        for agent_response_task in self.agent_response_tasks:
            if (
                not agent_response_task.task.done()
                or agent_response_task.task.cancelled()
            ):
                logger.info(
                    "Agent task not done. Cancelling task and adding to the buffer."
                )
                agent_response_task.task.cancel()
                cancelled_speeches.append(agent_response_task.human_speech)
        return cancelled_speeches

    # Conversation management

    def end_conversation(self):
        logger.debug("💬 Ending conversation.")
        if self.audio_interpreter_loop:
            self.audio_interpreter_loop.cancel()
        else:
            logger.warning("💬 Audio interpreter loop not found. Cannot cancel.")

    def vad_update(self, vad_result: VADResult | None):
        if vad_result is None:
            return ConversationState.HUMAN_SILENT

        if vad_result.ended:
            logger.info(
                f"Human speach ended. Speach length: {vad_result.end_sample or 0 - vad_result.start_sample}. "  # todo add more to his log
            )

            self.human_speech_ended(vad_result)

            if self.agent_was_interrupted() and vad_result.is_short():
                logger.info("🎙️🏁Short Human speech, agent was interrupted")
                return ConversationState.SHORT_INTERRUPTION_DURING_AGENT_SPEAKING

            if self.agent_was_interrupted() and vad_result.is_long():
                logger.info("🎙️🏁Long Human speech, agent was interrupted")
                return ConversationState.LONG_INTERRUPTION_DURING_AGENT_SPEAKING

            if vad_result.is_short():
                logger.info("🎙️🏁Short Human speech detected")
                return ConversationState.SHORT_SPEECH

            if vad_result.is_long():
                logger.info("🎙️🏁Long Human speech detected")
                return ConversationState.LONG_SPEECH

            raise ValueError("🎙️🏁Human speech ended, but no state was matched")

        elif not vad_result.ended:
            if self.is_agent_speaking():
                logger.info("🎙️🟢 Human and Agent are speaking.")
                return ConversationState.BOTH_SPEAKING
            else:
                logger.info("🎙️🟢 Human started speaking")
                return ConversationState.HUMAN_STARTED_SPEAKING

    class Config:
        arbitrary_types_allowed = True
