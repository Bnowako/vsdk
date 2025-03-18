# vsdk

Production **not ready** voice sdk. If you want something serious use [pipecat](https://github.com/pipecat-ai/pipecat) or [livekit](https://github.com/livekit/livekit)

This is fun project, mostly for educational purposes. 

You can probably find leaking buffers, it's hacky, it's also very cool because it works.

The coolest feature is that the agent is able to stop speaking while you say something short for example "mhmm" and then resume.

### Why this project even exists?
Together with my best friend we were curious how hard it would be to write it without external orchestrating libraries, so we hacked it in few days. We also wrote [article](https://nomore.engineering/blog/voice-agents) about our voice-ai journey.

## Geting Started
(you need python, uv and api keys from openai, groq, elevenlabs)

1. Run `make install`
2. Setup env variables in `backend/.env` file based on `backend/.env.example`
3. Run `make run`
4. Open http://localhost:8000/vsdk and try talking to the agent

### Twilio
Twilio compatible ws interface is implemented in backend example, and available at http://localhost:8000/twilio

### Implementing your own interfaces
```python
class VoiceAgent:
    def __init__(
        self,
        stt: BaseSTT,
        tts: BaseTTS,
        agent: BaseAgent,
    ) -> None:
        self.stt = stt
        self.tts = tts
        self.agent = agent
```
If you want you can implement your own Agent with custom logic, or implement STT/TTS services from different providers.


