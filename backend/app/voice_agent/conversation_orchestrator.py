import asyncio
from typing import Awaitable, Callable

from langchain_openai import ChatOpenAI

from app.voice_agent.conversation.conversation_manager import (
    audio_interpreter_loop,
)
from app.voice_agent.conversation.domain import ConversationEvent
from app.voice_agent.conversation.models import Conversation
from app.voice_agent.stt.GroqSTTProcessor import GroqSTTProcessor
from app.voice_agent.tts.ElevenTTSProcessor import ElevenTTSProcessor
from app.voice_agent.ttt.OpenAIAgent import OpenAIAgent
from app.voice_agent.voice_agent import VoiceAgent


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
            audio_interpreter_loop(
                conversation=self.conversation,
                voice_agent=self.voice_agent,
                callback=callback,
            )
        )

    def audio_received(self, pcm_audio: bytes):
        self.conversation.audio_received(pcm_audio)

    def agent_speech_marked(self, speech_idx: int, chunk_idx: int):
        self.conversation.agent_speech_marked(speech_idx, chunk_idx)

    def end_conversation(self):
        self.conversation.end_conversation()
