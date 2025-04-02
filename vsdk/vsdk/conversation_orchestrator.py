import asyncio
import base64
import logging
from typing import Awaitable, Callable

from langchain_openai import ChatOpenAI

from vsdk.config import Config
from vsdk.conversation.base import Conversation, ConversationState
from vsdk.conversation.domain import (
    ConversationEvent,
    MarkEvent,
    MediaEvent,
    RestreamAudioEvent,
    ResultEvent,
    StartRespondingEvent,
    StopSpeakingEvent,
)
from vsdk.domain import RespondToHumanResult
from vsdk.stt.GroqSTTProcessor import GroqSTTProcessor
from vsdk.tts.ElevenTTSProcessor import ElevenTTSProcessor
from vsdk.ttt.OpenAIAgent import OpenAIAgent
from vsdk.vad.vad import VAD, VADResult
from vsdk.voice_agent import VoiceAgent

logger = logging.getLogger(__name__)


class ConversationOrchestrator:
    def __init__(
        self,
        conversation_id: str,
        callback: Callable[[ConversationEvent], Awaitable[None]],
        voice_agent: VoiceAgent = VoiceAgent(
            tts=ElevenTTSProcessor(),
            stt=GroqSTTProcessor(),
            agent=OpenAIAgent(
                llm=ChatOpenAI(model="gpt-4o"),
                system_prompt="You are a helpful assistant that can answer questions and help with tasks.",
            ),
        ),
    ):
        self.voice_agent = voice_agent
        self.conversation = Conversation(id=conversation_id)

        self.conversation.audio_interpreter_loop = asyncio.create_task(
            self._conversation_turn_manager()
        )
        self.callback = callback
        self.vad = VAD(id=conversation_id)

    def audio_received(self, pcm_audio: bytes):
        self.conversation.audio_received(pcm_audio)

    def agent_speech_marked(self, speech_idx: int, chunk_idx: int):
        self.conversation.agent_speech_marked(speech_idx, chunk_idx)

    # todo this should be done on orchestrator
    def end_conversation(self):
        self.conversation.end_conversation()

    async def _conversation_turn_manager(self):
        try:
            while True:
                if (
                    self.conversation.is_new_audio_ready_to_process()
                ):  # todo add queue and wait here for new audio ready to process
                    vad_result = self._check_for_speech()
                    if vad_result is not None and vad_result.ended:
                        self.conversation.human_speech_ended(vad_result)
                    conversation_state = self.conversation.get_conversation_state(
                        vad_result
                    )
                    logger.debug(f"🖥️ Conversation state: {conversation_state}")

                    match conversation_state:
                        case (
                            ConversationState.HUMAN_SILENT
                            | ConversationState.HUMAN_STARTED_SPEAKING
                        ):
                            pass

                        case ConversationState.BOTH_SPEAKING:
                            self.conversation.stop_speaking_agent()
                            await self.callback(StopSpeakingEvent())

                        case ConversationState.SHORT_INTERRUPTION_DURING_AGENT_SPEAKING:
                            await self._restream_audio(
                                self.conversation, self.callback
                            )  # todo should be done on another task?
                            self.conversation.clear_human_speech()  # todo this forgets what was the short interruption "yes" / "no". For now it is ok

                        case (
                            ConversationState.LONG_INTERRUPTION_DURING_AGENT_SPEAKING
                            | ConversationState.SHORT_SPEECH
                            | ConversationState.LONG_SPEECH
                        ):
                            human_speech = (
                                self.conversation.get_human_speech_without_response()
                            )
                            self.conversation.add_agent_response_task(
                                task=asyncio.create_task(
                                    self._handle_respond_to_human(
                                        human_speech,
                                        self.callback,
                                    )
                                ),
                                invoked_with_speech=human_speech,
                            )

                        case _:
                            raise ValueError(f"Unknown state: {conversation_state}")

                await asyncio.sleep(0.01)
        except Exception as e:
            logger.error(f"Exception in audio_interpreter_loop: {e}")

    async def _handle_respond_to_human(
        self,
        human_speech: bytes,
        callback: Callable[[ConversationEvent], Awaitable[None]],
    ):
        try:
            result: RespondToHumanResult = RespondToHumanResult.empty()

            await callback(StartRespondingEvent())
            self.conversation.new_agent_speech_start()

            async for chunk in self.voice_agent.respond_to_human(
                human_speech=human_speech,
                id=self.conversation.id,
                callback=lambda x: result.update(x),
            ):
                await callback(
                    MediaEvent(
                        audio=chunk.audio,
                        base64_audio=chunk.base64_audio,
                        sid=self.conversation.id,
                    )
                )
                mark_id = self.conversation.agent_speech_sent(chunk.audio)

                await callback(MarkEvent(mark_id=mark_id, sid=self.conversation.id))

            await callback(ResultEvent(result=result))
        except Exception as e:
            logger.error(
                f"Exception in handle_respond_to_human: {e}",
                exc_info=True,
            )

    async def _restream_audio(
        self,
        conversation: Conversation,
        callback: Callable[[ConversationEvent], Awaitable[None]],
    ):
        try:
            await callback(RestreamAudioEvent())
            logger.info(
                "Resending audio. All chunks: "  # todo add more logs
            )
            unspoken_chunks = conversation.get_unspoken_agent_speech()
            conversation.new_agent_speech_start()
            for agent_speech_chunk in unspoken_chunks:
                await callback(
                    MediaEvent(
                        audio=agent_speech_chunk.audio,
                        base64_audio=base64.b64encode(agent_speech_chunk.audio).decode(
                            "utf-8"
                        ),
                        sid=conversation.id,
                    )
                )
                mark_id = conversation.agent_speech_sent(agent_speech_chunk.audio)

                await callback(MarkEvent(mark_id=mark_id, sid=conversation.id))
        except Exception as e:
            logger.error(f"Exception in restream_audio: {e}")

    def _check_for_speech(self) -> VADResult | None:
        data_to_process = self.conversation.get_data_to_process_and_clear()
        if (
            len(data_to_process)
            > 1 * Config.Audio.sample_rate * Config.Audio.bytes_per_sample
        ):
            logger.warning(
                "Too much audio data to process. Something is off. Get rid off me"
            )
        return self.vad.silero_iterator(data_to_process)
