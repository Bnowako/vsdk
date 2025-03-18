/***** Configuration Constants *****/
const CONFIG = {
    SOCKET_URL: 'ws://localhost:8000/twilio/ws',
    AUDIO_SAMPLE_RATE: 8000,
    SCRIPT_PROCESSOR_BUFFER_SIZE: 256,
    INT16_NEGATIVE_MULTIPLIER: 0x8000, // 32768
    INT16_POSITIVE_MULTIPLIER: 0x7FFF, // 32767
    BIAS: 0x84,                      // 132
    CLIP: 32635
};

/***** Global Variables *****/
let socket,
    pendingAudioChunks = [],
    isPlaying = false,
    audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: CONFIG.AUDIO_SAMPLE_RATE });


/***** DOM Setup *****/
document.addEventListener('DOMContentLoaded', () => {
    const talkButton = document.getElementById('talkButton');
    document.getElementById('connectButton').addEventListener('click', startConversation);
    document.getElementById('disconnectButton').addEventListener('click', endConversation);
    talkButton.addEventListener('click', toggleTalking);
    // Auto-connect on sidebar open
    startConversation();
});

/***** Utility Functions *****/
const generateId = length =>
    Array.from({ length }, () => "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789".charAt(Math.floor(Math.random() * 62))).join('');

const float32ToInt16 = float32Array =>
    Int16Array.from(float32Array, s => {
        s = Math.max(-1, Math.min(1, s));
        return s < 0 ? s * CONFIG.INT16_NEGATIVE_MULTIPLIER : s * CONFIG.INT16_POSITIVE_MULTIPLIER;
    });

const int16ToMuLaw = int16Array => Uint8Array.from(int16Array, linearToMuLawSample);

function linearToMuLawSample(sample) {
    sample = Math.max(-CONFIG.CLIP, Math.min(CONFIG.CLIP, sample));
    let sign = sample < 0 ? 0x80 : 0;
    if (sign) sample = -sample;
    sample += CONFIG.BIAS;
    const exponent = getExponent(sample);
    const mantissa = (sample >> (exponent + 3)) & 0x0F;
    return ~(sign | (exponent << 4) | mantissa);
}

function getExponent(sample) {
    let exponent = 7;
    for (let expMask = 0x4000; (sample & expMask) === 0 && exponent > 0; exponent--, expMask >>= 1);
    return exponent;
}

const muLawDecode = muLawByte => {
    muLawByte = ~muLawByte & 0xFF;
    const sign = (muLawByte & 0x80) ? -1 : 1;
    const exponent = (muLawByte & 0x70) >> 4;
    const mantissa = muLawByte & 0x0F;
    return sign * (((mantissa << 4) + 8) << exponent);
};

/***** WebSocket Functions *****/
const updateConnectionStatus = (status, text) => {
    document.getElementById('wsStatus').className = `status-dot ${status}`;
    document.getElementById('wsStatusText').textContent = text;
};

function startConversation() {
    updateConnectionStatus('connecting', 'Connecting...');
    socket = new WebSocket(CONFIG.SOCKET_URL);
    socket.onopen = () => {
        updateConnectionStatus('connected', 'Connected');
        socket.send(JSON.stringify({
            event: 'start',
            start: { streamSid: generateId(32), accountSid: generateId(32), callSid: generateId(32) }
        }));
    };
    socket.onmessage = ({ data }) => {
        const msg = JSON.parse(data);
        switch (msg.event) {
            case 'result': handleResultEvent(msg); break;
            case 'media': handleMediaEvent(msg); break;
            case 'mark': handleMarkEvent(msg); break;
            case 'clear': handleClearEvent(); break;
            default: console.warn('Unknown event:', msg.event);
        }
    };
    socket.onclose = () => {
        updateConnectionStatus('disconnected', 'Disconnected');
        console.log('Disconnected');
    };
}

function endConversation() {
    const button = document.getElementById('talkButton');
    button.classList.remove('listening');
    button.textContent = 'Talk to AI Assistant';
    button.dataset.streamActive = "false";

    updateConnectionStatus('disconnected', 'Disconnected');

    if (window.currentAudioStream) {
        window.currentAudioStream.getTracks().forEach(track => track.stop());
        window.currentAudioStream = null;
    }
    if (window.currentAudioSource) {
        window.currentAudioSource.disconnect();
        window.currentAudioSource = null;
    }
    if (window.currentAudioWorklet) {
        window.currentAudioWorklet.disconnect();
        window.currentAudioWorklet = null;
    }
    if (socket) {
        socket.send(JSON.stringify({ event: 'closed' }));
        socket.close();
    }
}

/***** Audio Functions *****/
async function startStream() {
    const button = document.getElementById('talkButton');
    button.classList.add('listening');
    button.textContent = 'Requesting mic...';

    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
        });
        button.textContent = 'Listening...';

        const localAudioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: CONFIG.AUDIO_SAMPLE_RATE });

        // Load and register the audio worklet
        await localAudioContext.audioWorklet.addModule('/api/static/js/audio-processor.js');

        const source = localAudioContext.createMediaStreamSource(stream);
        const workletNode = new AudioWorkletNode(localAudioContext, 'audio-processor');

        // Handle processed audio data
        workletNode.port.onmessage = (event) => {
            if (button.dataset.streamActive !== "true") return;

            const muLawBuffer = event.data.mulawBuffer;
            const base64Buffer = btoa(String.fromCharCode(...muLawBuffer));
            const mediaEvent = { event: 'media', media: { payload: base64Buffer } };

            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify(mediaEvent));
            }
        };

        source.connect(workletNode);
        workletNode.connect(localAudioContext.destination);
        button.dataset.streamActive = "true";

        window.currentAudioStream = stream;
        window.currentAudioWorklet = workletNode;
        window.currentAudioSource = source;

    } catch (err) {
        console.error('Error accessing audio stream:', err);
        button.classList.remove('listening');
        button.textContent = 'Talk to AI Assistant';
        const errorDiv = document.createElement('div');
        errorDiv.className = 'message error';
        errorDiv.innerHTML = `
            <div class="message-content">
              <div class="error-message"><strong>Error:</strong> ${err.message || 'Microphone access denied'}</div>
              <div class="error-help">Please click the camera icon in the browser address bar and allow microphone access.</div>
            </div>`;
        document.getElementById('conversation').appendChild(errorDiv);
        errorDiv.scrollIntoView({ behavior: 'smooth' });
    }
}

function handleMediaEvent({ media: { payload } }) {
    const muLawBytes = Uint8Array.from(atob(payload), c => c.charCodeAt(0));
    const pcmSamples = Int16Array.from(muLawBytes, muLawDecode);
    const float32Samples = Float32Array.from(pcmSamples, s => s / 32768);
    pendingAudioChunks.push({ samples: float32Samples, markId: null });
    if (!isPlaying) playNextAudio();
}

function handleMarkEvent({ mark: { name } }) {
    const unmarked = pendingAudioChunks.find(chunk => chunk.markId === null);
    if (unmarked) unmarked.markId = name;
    if (!isPlaying) playNextAudio();
}

function playNextAudio() {
    const nextIndex = pendingAudioChunks.findIndex(chunk => chunk.markId !== null);
    if (nextIndex === -1) return isPlaying = false;
    isPlaying = true;
    const { samples, markId } = pendingAudioChunks.splice(nextIndex, 1)[0];
    playAudio(samples, () => {
        sendMarkEventToServer(markId);
        playNextAudio();
    });
}

function playAudio(samples, callback) {
    const buffer = audioContext.createBuffer(1, samples.length, CONFIG.AUDIO_SAMPLE_RATE);
    buffer.copyToChannel(samples, 0);
    const source = audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContext.destination);
    source.onended = callback;
    source.start(0);
}

function sendMarkEventToServer(markId) {
    socket.send(JSON.stringify({ event: 'mark', mark: { name: markId } }));
}

function stopAudio() {
    pendingAudioChunks = [];
    if (audioContext && audioContext.state !== 'closed') {
        audioContext.close().then(() => {
            audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: CONFIG.AUDIO_SAMPLE_RATE });
        }).catch(err => console.error('Error closing audio context:', err));
    }
    isPlaying = false;
}

/***** Result and Clear Handlers *****/
function handleResultEvent({ result }) {
    const sttDuration = result.stt_result.stt_end_time - result.stt_result.stt_start_time;
    const llmTtfToken = result.llm_result.end_time - result.llm_result.first_chunk_time;
    const ttsTtfChunk = result.tts_result.end_time - result.tts_result.first_chunk_time;

    const eosToFirstChunk = result.tts_result.first_chunk_time - result.stt_result.stt_start_time;
    const totalDuration = result.tts_result.end_time - result.stt_result.stt_start_time;

    const timings = [
        { label: 'Speech-to-Text', value: sttDuration.toFixed(2), unit: 's' },
        { label: 'LLM TTF Token', value: llmTtfToken.toFixed(2), unit: 's' },
        { label: 'Text-to-Speech TTF Chunk', value: ttsTtfChunk.toFixed(2), unit: 's' },
        { label: 'EOS to First Chunk', value: eosToFirstChunk.toFixed(2), unit: 's' },
        { label: 'Total Duration', value: totalDuration.toFixed(2), unit: 's' }
    ];

    const messageDiv = document.createElement('div');
    messageDiv.className = 'message';
    messageDiv.innerHTML = `
          <table class="metrics-table">
            <thead><tr><th>Metric</th><th>Duration</th></tr></thead>
            <tbody>${timings.map(t => `<tr><td>${t.label}</td><td>${t.value} ${t.unit}</td></tr>`).join('')}</tbody>
          </table>
          <div class="message-content">
            <div class="transcript"><strong>You:</strong> ${result.stt_result.transcript}</div>
            <div class="response"><strong>Assistant:</strong> ${result.llm_result.response}</div>
          </div>`;
    document.getElementById('conversation').appendChild(messageDiv);
    messageDiv.scrollIntoView({ behavior: 'smooth' });
}

function handleClearEvent() {
    sendMarksForRemainingChunks();
    stopAudio();
}

function sendMarksForRemainingChunks() {
    pendingAudioChunks.forEach(chunk => {
        const markId = chunk.markId || generateId(10);
        chunk.markId = markId;
        sendMarkEventToServer(markId);
    });
    pendingAudioChunks = [];
}

/***** Toggle Talking *****/
function toggleTalking() {
    const button = document.getElementById('talkButton');
    if (button.classList.contains('listening')) {
        endConversation();
    } else {
        if (!socket || socket.readyState !== WebSocket.OPEN) startConversation();
        button.classList.add('listening');
        button.textContent = 'Listening...';
        startStream();
    }
}
