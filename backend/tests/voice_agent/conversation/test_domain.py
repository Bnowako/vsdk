import pytest
from unittest.mock import MagicMock, Mock, patch

from app.voice_agent.conversation.models import Conversation, ConversationState


# Mock class for VADResult
class MockVADResult:
    def __init__(self, ended: bool, is_short: bool, is_long: bool):
        self.ended = ended
        self._is_short = is_short
        self._is_long = is_long
        self.start_sample = 0
        self.end_sample = 0

    def is_short(self):
        return self._is_short

    def is_long(self):
        return self._is_long


@patch("app.voice_agent.conversation.models.Conversation.check_for_speech")
def test_human_silent(mock_check_for_speech: MagicMock):
    """Test when no speech is detected (speech_result is None)."""
    mock_check_for_speech.return_value = None
    conversation = Conversation(id="test_sid")
    state = conversation.process()
    assert state == ConversationState.HUMAN_SILENT


@patch("app.voice_agent.conversation.models.Conversation.check_for_speech")
def test_short_speech(mock_check_for_speech: MagicMock):
    """Test when a short human speech ends without interrupting the agent."""
    mock_speech_result = MockVADResult(ended=True, is_short=True, is_long=False)
    mock_check_for_speech.return_value = mock_speech_result

    conversation = Conversation(id="test_sid")
    conversation.agent_was_interrupted = Mock(return_value=False)
    conversation.human_speech_ended = Mock()

    state = conversation.process()
    assert state == ConversationState.SHORT_SPEECH


@patch("app.voice_agent.conversation.models.Conversation.check_for_speech")
def test_long_speech(mock_check_for_speech: MagicMock):
    """Test when a long human speech ends without interrupting the agent."""
    mock_speech_result = MockVADResult(ended=True, is_short=False, is_long=True)
    mock_check_for_speech.return_value = mock_speech_result

    conversation = Conversation(id="test_sid")
    conversation.agent_was_interrupted = Mock(return_value=False)
    conversation.human_speech_ended = Mock()

    state = conversation.process()
    assert state == ConversationState.LONG_SPEECH


@patch("app.voice_agent.conversation.models.Conversation.check_for_speech")
def test_short_interruption_during_agent_speaking(mock_check_for_speech: MagicMock):
    """Test when a short human speech ends while interrupting the agent."""
    mock_speech_result = MockVADResult(ended=True, is_short=True, is_long=False)
    mock_check_for_speech.return_value = mock_speech_result

    conversation = Conversation(id="test_sid")
    conversation.agent_was_interrupted = Mock(return_value=True)
    conversation.human_speech_ended = Mock()

    state = conversation.process()
    assert state == ConversationState.SHORT_INTERRUPTION_DURING_AGENT_SPEAKING


@patch("app.voice_agent.conversation.models.Conversation.check_for_speech")
def test_long_interruption_during_agent_speaking(mock_check_for_speech: MagicMock):
    """Test when a long human speech ends while interrupting the agent."""
    mock_speech_result = MockVADResult(ended=True, is_short=False, is_long=True)
    mock_check_for_speech.return_value = mock_speech_result

    conversation = Conversation(id="test_sid")
    conversation.agent_was_interrupted = Mock(return_value=True)
    conversation.human_speech_ended = Mock()

    state = conversation.process()
    assert state == ConversationState.LONG_INTERRUPTION_DURING_AGENT_SPEAKING


@patch("app.voice_agent.conversation.models.Conversation.check_for_speech")
def test_both_speaking(mock_check_for_speech: MagicMock):
    """Test when both human and agent are speaking simultaneously."""
    mock_speech_result = MockVADResult(ended=False, is_short=False, is_long=False)
    mock_check_for_speech.return_value = mock_speech_result

    conversation = Conversation(id="test_sid")
    conversation.is_agent_speaking = Mock(return_value=True)

    state = conversation.process()
    assert state == ConversationState.BOTH_SPEAKING


@patch("app.voice_agent.conversation.models.Conversation.check_for_speech")
def test_human_started_speaking(mock_check_for_speech: MagicMock):
    """Test when human starts speaking and the agent is silent."""
    mock_speech_result = MockVADResult(ended=False, is_short=False, is_long=False)
    mock_check_for_speech.return_value = mock_speech_result

    conversation = Conversation(id="test_sid")
    conversation.is_agent_speaking = Mock(return_value=False)

    state = conversation.process()
    assert state == ConversationState.HUMAN_STARTED_SPEAKING


@patch("app.voice_agent.conversation.models.Conversation.check_for_speech")
def test_unmatched_state_raises_error(mock_check_for_speech: MagicMock):
    """Test when speech ends but does not match any state, expecting a ValueError."""
    mock_speech_result = MockVADResult(ended=True, is_short=False, is_long=False)
    mock_speech_result.is_short = Mock(return_value=False)
    mock_speech_result.is_long = Mock(return_value=False)
    mock_check_for_speech.return_value = mock_speech_result

    conversation = Conversation(id="test_sid")
    conversation.agent_was_interrupted = Mock(return_value=False)
    conversation.human_speech_ended = Mock()

    with pytest.raises(ValueError):
        conversation.process()
