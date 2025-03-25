import asyncio
import base64
import logging
from typing import Awaitable, Callable

from app.voice_agent.conversation.conversation_processor import (
    ConversationState,
    process,
)
from app.voice_agent.conversation.domain import (
    ConversationEvent,
    MarkEvent,
    MediaEvent,
    RestreamAudioEvent,
    ResultEvent,
    StartRespondingEvent,
    StopSpeakingEvent,
)
from app.voice_agent.conversation.models import Conversation
from app.voice_agent.domain import RespondToHumanResult
from app.voice_agent.voice_agent import VoiceAgent

logger = logging.getLogger(__name__)


async def audio_interpreter_loop(
    conversation: Conversation,
    voice_agent: VoiceAgent,
    callback: Callable[[ConversationEvent], Awaitable[None]],
):
    try:
        while True:
            if conversation.is_new_audio_ready_to_process():
                conversation_state = process(conversation)
                logger.debug(f"🖥️ Conversation state: {conversation_state}")

                match conversation_state:
                    case (
                        ConversationState.HUMAN_SILENT
                        | ConversationState.HUMAN_STARTED_SPEAKING
                    ):
                        pass

                    case ConversationState.BOTH_SPEAKING:
                        conversation.stop_speaking_agent()

                        await callback(StopSpeakingEvent())

                    case ConversationState.SHORT_INTERRUPTION_DURING_AGENT_SPEAKING:
                        await restream_audio(
                            conversation, callback
                        )  # todo should be done on another task?
                        conversation.clear_human_speech()  # todo this forgets what was the short interruption "tak" / "nie". For now it is ok

                    case (
                        ConversationState.LONG_INTERRUPTION_DURING_AGENT_SPEAKING
                        | ConversationState.SHORT_SPEECH
                        | ConversationState.LONG_SPEECH
                    ):
                        conversation.prepare_human_speech_for_interpretation()
                        conversation.add_agent_response_task(
                            task=asyncio.create_task(
                                handle_respond_to_human(
                                    conversation, voice_agent, callback
                                )
                            )
                        )

                    case _:
                        raise ValueError(f"Unknown state: {conversation_state}")

            await asyncio.sleep(0.01)
    except Exception as e:
        logger.error(f"Exception in audio_interpreter_loop: {e}")


async def handle_respond_to_human(
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


async def restream_audio(
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
