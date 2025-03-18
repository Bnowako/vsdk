import asyncio
import logging

from fastapi import WebSocket

from app.conversation.conversation_processor import ConversationState, process
from app.conversation.models import Conversation
from app.voice_agent.domain import RespondToHumanResult
from app.voice_agent.outbound_events import (
    send_mark,
    send_media,
    send_result,
    send_stop_speaking,
)
from app.voice_agent.voice_agent_coordinator import respond_to_human

logger = logging.getLogger(__name__)


async def audio_interpreter_loop(conversation: Conversation, websocket: WebSocket):
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
                        await send_stop_speaking(websocket, conversation)

                    case ConversationState.SHORT_INTERRUPTION_DURING_AGENT_SPEAKING:
                        await restream_audio(
                            websocket, conversation
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
                                handle_respond_to_human(conversation, websocket)
                            )
                        )

                    case _:
                        raise ValueError(f"Unknown state: {conversation_state}")

            await asyncio.sleep(0.01)
    except Exception as e:
        logger.error(f"Exception in audio_interpreter_loop: {e}")


async def handle_respond_to_human(conversation: Conversation, websocket: WebSocket):
    try:
        result: RespondToHumanResult = RespondToHumanResult.empty()
        conversation.new_agent_speech_start()
        async for chunk in respond_to_human(
            pcm_audio_buffer=conversation.human_speech_without_response,
            sid=conversation.sid,
            callback=lambda x: result.update(x),
        ):
            await send_media(chunk, websocket, conversation.sid)
            mark_id = conversation.agent_speech_sent(chunk)
            await send_mark(websocket, mark_id, conversation.sid)

        await send_result(
            websocket=websocket,
            result=result,
        )
    except Exception as e:
        logger.error(f"Exception in handle_respond_to_human: {e}")


async def restream_audio(websocket: WebSocket, conversation: Conversation):
    try:
        logger.info(
            "Resending audio. All chunks: "  # todo add more logs
        )
        unspoken_chunks = conversation.get_unspoken_agent_speech()
        conversation.new_agent_speech_start()
        for agent_speech_chunk in unspoken_chunks:
            await send_media(agent_speech_chunk.audio, websocket, conversation.sid)
            mark_id = conversation.agent_speech_sent(agent_speech_chunk.audio)

            await send_mark(websocket, mark_id, conversation.sid)
    except Exception as e:
        logger.error(f"Exception in restream_audio: {e}")
