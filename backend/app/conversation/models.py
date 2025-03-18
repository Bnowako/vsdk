import logging
from asyncio import Task
from typing import List


from app.audio.vad import VADResult
from app.config import Config

logger = logging.getLogger(__name__)


class AgentSpeechChunk:
    def __init__(self, audio: bytes, mark_id: str):
        self.audio = audio
        self.mark_id = mark_id


class AgentResponseTask:
    def __init__(self, human_speech: bytes, task: Task):
        self.human_speech = human_speech
        self.task = task


class AgentSpeech:
    def __init__(self, speech_chunks: List[AgentSpeechChunk], pointer: int):
        self.speech_chunks = speech_chunks
        self.pointer = 0
        self.stop_sent_at = None

    def mark(self, chunk_idx):
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
    def __init__(self, sid: str):
        self.speeches: List[AgentSpeech] = []
        self.sid = sid

    @property
    def last_speech(self):
        return self.speeches[-1]

    @property
    def speech_exists(self):
        return len(self.speeches) > 0

    def chunk_sent(self, chunk: bytes):
        mark_id = (
            self.sid
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


class Conversation:
    def __init__(self, sid: str):
        self.sid = sid

        # Audio IN
        # TODO extract all of those to separate class HumanSpeech
        # this class should be responsible for managing human speech and be aware of the current state of each speech
        self.pcm_audio_buffer = b""
        self.new_pcm_audio = b""
        self.last_human_speech = b""
        self.human_speech_without_response = b""

        # Thinking
        self.agent_response_tasks: List[AgentResponseTask] = []

        # Audio OUT
        self.agent_voice = AgentVoice(sid)

        self.audio_interpreter_loop: Task | None = None

    # Human Voice
    def audio_received(self, pcm_audio):
        self.new_pcm_audio += pcm_audio
        self.pcm_audio_buffer += pcm_audio
        logger.debug(
            f"👩🏼🗣️ Audio of length: {len(pcm_audio)} received. Updated state {self.state_string()}"
        )

    def clear_human_speech(self):
        logger.debug(f"👩🏼🗣️ Clearing client data state {self.state_string()}")
        self.pcm_audio_buffer = b""

    def get_data_to_process_and_clear(self):
        k = (
            len(self.new_pcm_audio) // Config.Audio.silero_samples_size_bytes
        ) * Config.Audio.silero_samples_size_bytes
        data_to_process = self.new_pcm_audio[:k]
        self.new_pcm_audio = self.new_pcm_audio[k:]
        logger.debug(
            f"✨👩🏼🗣️ Took audio of length: {len(data_to_process)}. Current pcm_audio_buffer length: {len(self.pcm_audio_buffer)}, Current new audio length: {len(self.new_pcm_audio)}"
        )
        return data_to_process

    def human_speech_ended(self, speech_result: VADResult):
        logger.debug("👩🏼🗣️ Human speech ended. ")  # todo add more logs
        self.last_human_speech = self._get_audio(
            from_sample=speech_result.start_sample, to_sample=speech_result.end_sample
        )
        self.clear_human_speech()

    def prepare_human_speech_for_interpretation(self):
        """
        Prepare human speech for interpretation by adding all previous human speeches and last human speech
        This function will cancel all unfinished tasks and add them to the buffer
        :return:
        """
        logger.debug("👩🏼🗣Preparing human speech for interpretation.")
        human_speech_without_response_buffers = self._cancel_unfinished_tasks()
        if human_speech_without_response_buffers:
            human_speech_without_response = (
                    (b"\x00" * 2 * 80).join(human_speech_without_response_buffers)
                    + b"\x00" * 2 * 80
                    + self.last_human_speech
            )
            self.human_speech_without_response = human_speech_without_response
        else:
            self.human_speech_without_response = self.last_human_speech

    def _get_audio(self, from_sample: int, to_sample: int):
        logger.info(
            f"👩🏼🗣️ Get audio requested, Requested audio length: {(to_sample - from_sample) // Config.Audio.bytes_per_sample / Config.Audio.sample_rate }s. pcm_audio_buffer length: {(len(self.pcm_audio_buffer) // Config.Audio.bytes_per_sample) / Config.Audio.sample_rate}s"
        )
        from_bytes = (
                from_sample * Config.Audio.bytes_per_sample
        )  # 2 bytes per sample for 16-bit audio
        to_bytes = (
                to_sample * Config.Audio.bytes_per_sample
        )  # 2 bytes per sample for 16-bit audio
        return self.pcm_audio_buffer[from_bytes:to_bytes]


    # Agent Voice
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

    def add_agent_response_task(self, task: Task):
        logger.debug("🧠 Adding agent response task.")
        self.agent_response_tasks.append(
            AgentResponseTask(
                task=task, human_speech=self.human_speech_without_response
            )
        )

    def _cancel_unfinished_tasks(self) -> List[bytes]:
        """
        Cancel all unfinished tasks and return their human_speech
        :return:
        """
        logger.debug("🧠 Cancelling unfinished tasks.")
        cancelled_speeches = []
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
        self.audio_interpreter_loop.cancel()

    def is_new_audio_ready_to_process(self):
        return len(self.new_pcm_audio) >= Config.Audio.silero_samples_size_bytes

    def state_string(self):
        return f"Conversation state:  new_pcm_audio: {len(self.new_pcm_audio)} pcm_audio_buffer: {len(self.pcm_audio_buffer)} human_speech_without_response: {len(self.human_speech_without_response)}"  # todo add more to this log

    class Config:
        arbitrary_types_allowed = True
