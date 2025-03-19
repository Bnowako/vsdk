/***** Configuration Constants *****/
const CONFIG = {
  SOCKET_URL: 'ws://localhost:8000/ws',
  AUDIO_SAMPLE_RATE: 8000,
  SCRIPT_PROCESSOR_BUFFER_SIZE: 256,
  INT16_NEGATIVE_MULTIPLIER: 0x8000, // 32768 for negative values
  INT16_POSITIVE_MULTIPLIER: 0x7FFF, // 32767 for positive values
  BIAS: 0x84,                      // 132
  CLIP: 32635
};

/***** Global Variables *****/
let socket;
let pendingAudioChunks = [];
let audioQueue = [];
let isPlaying = false;
let audioContext = new (window.AudioContext || window.webkitAudioContext)({
  sampleRate: CONFIG.AUDIO_SAMPLE_RATE
});

/***** DOM Elements *****/
document.addEventListener('DOMContentLoaded', () => {
  const talkButton = document.getElementById('talkButton');
  const connectButton = document.getElementById('connectButton');
  const disconnectButton = document.getElementById('disconnectButton');

  talkButton.addEventListener('click', toggleTalking);
  connectButton.addEventListener('click', startConversation);
  disconnectButton.addEventListener('click', endConversation);

  // Auto-connect when sidebar opens for better user experience
  startConversation();
});

/***** Utility Functions *****/
function generateId(length) {
  const characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < length; i++) {
    result += characters.charAt(Math.floor(Math.random() * characters.length));
  }
  return result;
}

function float32ToInt16(float32Array) {
  const int16Array = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    int16Array[i] = s < 0
      ? s * CONFIG.INT16_NEGATIVE_MULTIPLIER
      : s * CONFIG.INT16_POSITIVE_MULTIPLIER;
  }
  return int16Array;
}

function int16ToMuLaw(int16Array) {
  const muLawArray = new Uint8Array(int16Array.length);
  for (let i = 0; i < int16Array.length; i++) {
    muLawArray[i] = linearToMuLawSample(int16Array[i]);
  }
  return muLawArray;
}

function linearToMuLawSample(sample) {
  // Clip the sample
  sample = Math.max(-CONFIG.CLIP, Math.min(CONFIG.CLIP, sample));

  // Determine sign and adjust sample if negative
  let sign = (sample < 0) ? 0x80 : 0;
  if (sign !== 0) {
    sample = -sample;
  }

  // Add bias and compute exponent and mantissa
  sample += CONFIG.BIAS;
  const exponent = getExponent(sample);
  const mantissa = (sample >> (exponent + 3)) & 0x0F;
  const muLawByte = ~(sign | (exponent << 4) | mantissa);
  return muLawByte;
}

function getExponent(sample) {
  let exponent = 7;
  for (let expMask = 0x4000; (sample & expMask) === 0 && exponent > 0; exponent--, expMask >>= 1);
  return exponent;
}

function muLawDecode(muLawByte) {
  muLawByte = ~muLawByte & 0xFF;
  const sign = (muLawByte & 0x80) ? -1 : 1;
  const exponent = (muLawByte & 0x70) >> 4;
  const mantissa = muLawByte & 0x0F;
  const magnitude = ((mantissa << 4) + 8) << exponent;
  return sign * magnitude;
}

/***** WebSocket Functions *****/
function updateConnectionStatus(status, text) {
  const statusDot = document.getElementById('wsStatus');
  const statusText = document.getElementById('wsStatusText');

  statusDot.className = `status-dot ${status}`;
  statusText.textContent = text;
}

function startConversation() {
  updateConnectionStatus('connecting', 'Connecting...');
  socket = new WebSocket(CONFIG.SOCKET_URL);

  socket.onopen = () => {
    updateConnectionStatus('connected', 'Connected');
    // Send StartEvent conforming to the Pydantic model
    const startEvent = {
      event: 'start',
      start: {
        streamSid: generateId(32),
        accountSid: generateId(32),
        callSid: generateId(32)
      }
    };
    socket.send(JSON.stringify(startEvent));
  };

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    switch (data.event) {
      case 'result':
        handleResultEvent(data);
        break;
      case 'media':
        handleMediaEvent(data);
        break;
      case 'mark':
        handleMarkEvent(data);
        break;
      case 'clear':
        handleClearEvent();
        break;
      default:
        console.warn('Unknown event type:', data.event);
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

  // Stop all audio tracks
  if (window.currentAudioStream) {
    window.currentAudioStream.getTracks().forEach(track => track.stop());
    window.currentAudioStream = null;
  }

  // Disconnect audio nodes
  if (window.currentAudioSource) {
    window.currentAudioSource.disconnect();
    window.currentAudioSource = null;
  }

  if (window.currentAudioProcessor) {
    window.currentAudioProcessor.disconnect();
    window.currentAudioProcessor = null;
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
    // Try to get the audio stream directly - the browser will show permission dialog
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    });

    button.textContent = 'Listening...';
    console.log('Audio stream obtained:', stream);

    // Create a dedicated AudioContext for this stream
    const localAudioContext = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: CONFIG.AUDIO_SAMPLE_RATE
    });
    console.log('AudioContext sample rate:', localAudioContext.sampleRate);

    const source = localAudioContext.createMediaStreamSource(stream);
    const processor = localAudioContext.createScriptProcessor(
      CONFIG.SCRIPT_PROCESSOR_BUFFER_SIZE, 1, 1
    );

    source.connect(processor);
    processor.connect(localAudioContext.destination);

    // Keep track of the stream to stop it later
    button.dataset.streamActive = "true";

    // Save the stream and track to be stopped later
    window.currentAudioStream = stream;
    window.currentAudioProcessor = processor;
    window.currentAudioSource = source;

    processor.onaudioprocess = (e) => {
      // Only process if we're still listening
      if (button.dataset.streamActive !== "true") {
        return;
      }

      const inputBuffer = e.inputBuffer.getChannelData(0);
      const int16Buffer = float32ToInt16(inputBuffer);
      const muLawBuffer = int16ToMuLaw(int16Buffer);
      const base64Buffer = btoa(String.fromCharCode.apply(null, muLawBuffer));

      // Send MediaEvent conforming to the Pydantic model
      const mediaEvent = {
        event: 'media',
        media: { payload: base64Buffer }
      };

      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(mediaEvent));
      }
    };
  } catch (err) {
    console.error('Error accessing audio stream:', err);
    button.classList.remove('listening');
    button.textContent = 'Talk to AI Assistant';

    // Show error to user
    const errorDiv = document.createElement('div');
    errorDiv.className = 'message error';
    errorDiv.innerHTML = `
      <div class="message-content">
        <div class="error-message"><strong>Error:</strong> ${err.message || 'Microphone access denied'}</div>
        <div class="error-help">Please click the camera icon in the browser address bar and allow microphone access.</div>
      </div>
    `;
    document.getElementById('conversation').appendChild(errorDiv);
    errorDiv.scrollIntoView({ behavior: 'smooth' });
  }
}

function handleMediaEvent(data) {
  const encodedPayload = data.media.payload;
  // Decode base64 to Uint8Array (μ-law encoded bytes)
  const muLawBytes = Uint8Array.from(atob(encodedPayload), c => c.charCodeAt(0));

  // Decode μ-law bytes to PCM samples
  const pcmSamples = new Int16Array(muLawBytes.length);
  for (let i = 0; i < muLawBytes.length; i++) {
    pcmSamples[i] = muLawDecode(muLawBytes[i]);
  }

  // Normalize PCM samples to Float32Array in range [-1, 1]
  const float32Samples = new Float32Array(pcmSamples.length);
  for (let i = 0; i < pcmSamples.length; i++) {
    float32Samples[i] = pcmSamples[i] / 32768;
  }

  // Enqueue audio samples for playback
  audioQueue.push(float32Samples);
  pendingAudioChunks.push({ samples: float32Samples, markId: null });
}

function handleMarkEvent(data) {
  console.log("Received mark");
  const markId = data.mark.name;
  // Associate the markId with the first unmarked audio chunk
  const unmarkedChunk = pendingAudioChunks.find(chunk => chunk.markId === null);
  if (unmarkedChunk) {
    unmarkedChunk.markId = markId;
  }
  // Start playing if not already playing
  if (!isPlaying) {
    playNextAudio();
  }
}

function playNextAudio() {
  // Find the next chunk with an assigned markId
  const nextChunkIndex = pendingAudioChunks.findIndex(chunk => chunk.markId !== null);
  console.log("Playing next audio", nextChunkIndex);

  if (nextChunkIndex === -1) {
    isPlaying = false;
    return;
  }
  isPlaying = true;
  const chunk = pendingAudioChunks.splice(nextChunkIndex, 1)[0];

  playAudio(chunk.samples, () => {
    sendMarkEventToServer(chunk.markId);
    playNextAudio();
  });
}

function playAudio(float32Samples, callback) {
  console.log(`Playing audio chunk - ${float32Samples.length} samples`);
  const buffer = audioContext.createBuffer(1, float32Samples.length, CONFIG.AUDIO_SAMPLE_RATE);
  buffer.copyToChannel(float32Samples, 0);

  const source = audioContext.createBufferSource();
  source.buffer = buffer;
  source.connect(audioContext.destination);
  source.onended = callback;
  source.start(0);
}

function sendMarkEventToServer(markId) {
  // Send MarkEvent conforming to the Pydantic model (without extra properties)
  const markEvent = {
    event: 'mark',
    mark: { name: markId }
  };
  socket.send(JSON.stringify(markEvent));
}

function stopAudio() {
  // Clear pending audio chunks
  pendingAudioChunks = [];
  if (audioContext && audioContext.state !== 'closed') {
    audioContext.close().then(() => {
      audioContext = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: CONFIG.AUDIO_SAMPLE_RATE
      });
    }).catch(err => {
      console.error('Error closing audio context:', err);
    });
  }
  isPlaying = false;
  console.log('Audio stopped');
}

/***** Incoming Result Event Handler *****/
function handleResultEvent(data) {
  const result = data.result;
  const messageDiv = document.createElement('div');
  messageDiv.className = 'message';

  // Format timing data
  const timings = [
    { label: 'Speech-to-Text', value: result.stt_duration, unit: 's' },
    { label: 'AI Processing', value: result.llm_duration, unit: 's' },
    { label: 'Text-to-Speech', value: result.tts_duration, unit: 's' },
    { label: 'First Chunk', value: result.first_chunk_time, unit: 's' },
    { label: 'Total Duration', value: result.total_duration, unit: 's' }
  ];

  messageDiv.innerHTML = `
    <table class="metrics-table">
      <thead>
        <tr>
          <th>Metric</th>
          <th>Duration</th>
        </tr>
      </thead>
      <tbody>
        ${timings.map(timing => `
          <tr>
            <td>${timing.label}</td>
            <td>${timing.value.toLocaleString()} ${timing.unit}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
    <div class="message-content">
      <div class="transcript"><strong>You:</strong> ${result.transcript}</div>
      <div class="response"><strong>Assistant:</strong> ${result.response}</div>
    </div>
  `;

  document.getElementById('conversation').appendChild(messageDiv);
  messageDiv.scrollIntoView({ behavior: 'smooth' });
}

function handleClearEvent() {
  sendMarksForRemainingChunks();
  stopAudio();
}

function sendMarksForRemainingChunks() {
  pendingAudioChunks.forEach(chunk => {
    if (chunk.markId !== null) {
      sendMarkEventToServer(chunk.markId);
    } else {
      const tempMarkId = generateId(10);
      chunk.markId = tempMarkId;
      sendMarkEventToServer(tempMarkId);
    }
  });
  pendingAudioChunks = [];
}

function toggleTalking() {
  const button = document.getElementById('talkButton');

  if (button.classList.contains('listening')) {
    // Stop listening
    button.classList.remove('listening');
    button.textContent = 'Talk to AI Assistant';
    endConversation();
  } else {
    // Start listening
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      startConversation();
    }
    button.classList.add('listening');
    button.textContent = 'Listening...';
    startStream();
  }
}
