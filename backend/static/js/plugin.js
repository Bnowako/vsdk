/***** Configuration Constants *****/
const CONFIG = {
    SOCKET_URL: 'ws://localhost:8000/plugin/ws',
    AUDIO_SAMPLE_RATE: 8000,
    AI_VOICE_SAMPLE_RATE: 16000,
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
    audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: CONFIG.AI_VOICE_SAMPLE_RATE });


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
    };
    socket.onmessage = ({ data }) => {
        const msg = JSON.parse(data);
        console.log("Received event:", msg.type);
        switch (msg.type) {
            case 'result': handleResultEvent(msg); break;
            case 'media': handleMediaEvent(msg); break;
            case 'mark': handleMarkEvent(msg); break;
            case 'stop_speaking': handleStopSpeakingEvent(); break;
            case 'start_restream': handleRestreamEvent(); break;
            case 'start_responding': handleStartRespondingEvent(); break;
            default: console.warn('Unknown event:', msg.type);
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

        // Helper function to convert a Uint8Array to a base64 encoded string.
        function uint8ToBase64(uint8Array) {
            let binary = "";
            for (let i = 0; i < uint8Array.byteLength; i++) {
            binary += String.fromCharCode(uint8Array[i]);
            }
            return btoa(binary);
        }

        workletNode.port.onmessage = (event) => {
            if (button.dataset.streamActive !== "true") return;

            const mediaEvent = {
                type: 'media',
                audio: uint8ToBase64(event.data.uint8Buffer),
                base64_audio: uint8ToBase64(event.data.uint8Buffer),
                sid: generateId(32)
            };

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

function base64ToArrayBuffer(base64) {
    const binaryString = window.atob(base64);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
  }

function handleMediaEvent({  audio  }) {
    const pcmBytes = base64ToArrayBuffer(audio);
    console.log("ArrayBuffer byteLength:", pcmBytes.byteLength);
    if (pcmBytes.byteLength % 2 !== 0) {
        console.warn("Unexpected PCM data length, not a multiple of 2!");
    }
    const pcmSamples = new Int16Array(pcmBytes);
    console.log("First few samples:", pcmSamples.slice(0, 10));

    // Convert samples to floats.
    const float32Samples = new Float32Array(pcmSamples.length);
    for (let i = 0; i < pcmSamples.length; i++) {
        // Use proper normalization: negative samples divided by 32768, positive by 32767.
        const s = pcmSamples[i];
        float32Samples[i] = s < 0 ? s / 32768 : s / 32767;
    }

    pendingAudioChunks.push({ samples: float32Samples, markId: null });
    if (!isPlaying) playNextAudio();
}

function handleMarkEvent({ mark_id }) {
    const unmarked = pendingAudioChunks.find(chunk => chunk.markId === null);
    if (unmarked) unmarked.markId = mark_id;
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
    const buffer = audioContext.createBuffer(1, samples.length, CONFIG.AI_VOICE_SAMPLE_RATE);
    buffer.copyToChannel(samples, 0);
    const source = audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContext.destination);
    source.onended = callback;
    source.start(0);
}

function sendMarkEventToServer(markId) {
    socket.send(JSON.stringify({
        type: 'mark',
        mark_id: markId,
        sid: generateId(32)
    }));
}

function stopAudio() {
    pendingAudioChunks = [];
    if (audioContext && audioContext.state !== 'closed') {
        audioContext.close().then(() => {
        audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: CONFIG.AI_VOICE_SAMPLE_RATE });
        }).catch(err => console.error('Error closing audio context:', err));
    }
    isPlaying = false;
}

/***** Result and Clear Handlers *****/
function handleResultEvent({ result }) {
    const sttDuration = result.stt_result.stt_end_time - result.stt_result.stt_start_time;
    const llmDuration = result.llm_result.end_time - result.llm_result.start_time;
    const ttsDuration = result.tts_result.end_time - result.tts_result.start_time;

    const timings = [
        { label: 'Speech-to-Text', value: sttDuration.toFixed(2), unit: 's' },
        { label: 'AI Processing', value: llmDuration.toFixed(2), unit: 's' },
        { label: 'Text-to-Speech', value: ttsDuration.toFixed(2), unit: 's' },
        { label: 'First Chunk', value: result.tts_result.first_chunk_time.toFixed(2), unit: 's' },
        { label: 'Total Duration', value: (sttDuration + llmDuration + ttsDuration).toFixed(2), unit: 's' }
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

// Add new event handlers
function handleStopSpeakingEvent() {
    stopAudio();
}

function handleRestreamEvent() {
    // Handle restream event if needed
    console.log('Restreaming audio...');
}

function handleStartRespondingEvent() {
    // Handle start responding event if needed
    console.log('AI starting to respond...');
}
