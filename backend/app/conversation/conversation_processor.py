from enum import Enum

import logging

from app.audio.vad import VADResult, silero_iterator
from app.config import Config
from app.conversation.models import Conversation

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    BOTH_SPEAKING = 1
    HUMAN_SILENT = 2
    SHORT_INTERRUPTION_DURING_AGENT_SPEAKING = 3
    LONG_INTERRUPTION_DURING_AGENT_SPEAKING = 4
    SHORT_SPEECH = 5
    LONG_SPEECH = 6
    HUMAN_STARTED_SPEAKING = 7


def process(conversation: Conversation):
    speech_result = check_for_speech(conversation)

    if speech_result is None:
        return ConversationState.HUMAN_SILENT

    if speech_result.ended:
        logger.info(
            f"Human speach ended. Speach length: {speech_result.end_sample or 0 - speech_result.start_sample}. "  # todo add more to his log
        )

        conversation.human_speech_ended(speech_result)

        if conversation.agent_was_interrupted() and speech_result.is_short():
            logger.info("🎙️🏁Short Human speech, agent was interrupted")
            return ConversationState.SHORT_INTERRUPTION_DURING_AGENT_SPEAKING

        if conversation.agent_was_interrupted() and speech_result.is_long():
            logger.info("🎙️🏁Long Human speech, agent was interrupted")
            return ConversationState.LONG_INTERRUPTION_DURING_AGENT_SPEAKING

        if speech_result.is_short():
            logger.info("🎙️🏁Short Human speech detected")
            return ConversationState.SHORT_SPEECH

        if speech_result.is_long():
            logger.info("🎙️🏁Long Human speech detected")
            return ConversationState.LONG_SPEECH

        raise ValueError("🎙️🏁Human speech ended, but no state was matched")

    elif not speech_result.ended:
        if conversation.is_agent_speaking():
            logger.info("🎙️🟢 Human and Agent are speaking.")
            return ConversationState.BOTH_SPEAKING
        else:
            logger.info("🎙️🟢 Human started speaking")
            return ConversationState.HUMAN_STARTED_SPEAKING


def check_for_speech(conversation: Conversation) -> VADResult | None:
    data_to_process = conversation.get_data_to_process_and_clear()
    if (
        len(data_to_process)
        > 1 * Config.Audio.sample_rate * Config.Audio.bytes_per_sample
    ):
        logger.warning("Too much audio data to process. Get rid off me")
    return silero_iterator(data_to_process, conversation.sid)
