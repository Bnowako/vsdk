import asyncio
import base64
import logging
from typing import Awaitable, Callable

from langchain_openai import ChatOpenAI

from app.voice_agent.conversation.domain import (
    ConversationEvent,
    MarkEvent,
    MediaEvent,
    RestreamAudioEvent,
    ResultEvent,
    StartRespondingEvent,
    StopSpeakingEvent,
)
from app.voice_agent.conversation.models import Conversation, ConversationState
from app.voice_agent.domain import RespondToHumanResult
from app.voice_agent.stt.GroqSTTProcessor import GroqSTTProcessor
from app.voice_agent.tts.ElevenTTSProcessor import ElevenTTSProcessor
from app.voice_agent.ttt.OpenAIAgent import OpenAIAgent
from app.voice_agent.voice_agent import VoiceAgent

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
                    conversation_state = self.conversation.process()
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
                            self.conversation.prepare_human_speech_for_interpretation()
                            self.conversation.add_agent_response_task(
                                task=asyncio.create_task(
                                    self._handle_respond_to_human(
                                        self.conversation,
                                        self.voice_agent,
                                        self.callback,
                                    )
                                )
                            )

                        case _:
                            raise ValueError(f"Unknown state: {conversation_state}")

                await asyncio.sleep(0.01)
        except Exception as e:
            logger.error(f"Exception in audio_interpreter_loop: {e}")

    async def _handle_respond_to_human(
        self,
        conversation: Conversation,
        voice_agent: VoiceAgent,
        callback: Callable[[ConversationEvent], Awaitable[None]],
    ):
        try:
            await callback(StartRespondingEvent())
            result: RespondToHumanResult = RespondToHumanResult.empty()
            conversation.new_agent_speech_start()
            async for chunk in voice_agent.respond_to_human(
                pcm_audio_buffer=conversation.human_speech_without_response,
                sid=conversation.id,
                callback=lambda x: result.update(x),
            ):
                await callback(
                    MediaEvent(
                        audio=chunk.audio,
                        base64_audio=chunk.base64_audio,
                        sid=conversation.id,
                    )
                )
                mark_id = conversation.agent_speech_sent(chunk.audio)

                await callback(MarkEvent(mark_id=mark_id, sid=conversation.id))

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
