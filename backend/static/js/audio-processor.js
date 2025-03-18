// Add µ-law encoding function
function encodeMuLaw(sample) {
  // Clamp input to [-1, 1]
  sample = Math.max(-1, Math.min(1, sample));

  // Convert to 14-bit linear
  let value = Math.abs(sample) * 8192;

  // Calculate the segment
  let segment = 7;
  for (let i = 7; i >= 0; i--) {
    if (value >= (1 << i)) {
      segment = i;
      break;
    }
  }

  // Combine sign, segment, and quantization
  let sign = sample < 0 ? 0x80 : 0;
  let position = (value >> (segment + 3)) & 0x0F;
  return ~(sign | (segment << 4) | position);
}

class AudioProcessor extends AudioWorkletProcessor {
    process(inputs, outputs, parameters) {
      // Get the first input and channel data.
      const input = inputs[0];
      if (!input || input.length === 0 || !input[0]) {
        return true;
      }
      const channelData = input[0]; // Float32Array of audio samples

      const targetRate = 8000;
      // sampleRate is a global available in the AudioWorkletGlobalScope,
      // and it equals the AudioContext sampleRate (CONFIG.AUDIO_SAMPLE_RATE)
      let processedBuffer;
      if (sampleRate !== targetRate) {
        // Downsample if the current sampleRate is not 8000Hz.
        processedBuffer = downsampleBuffer(channelData, sampleRate, targetRate);
      } else {
        // If the AudioContext is already at 8kHz, no need to downsample.
        processedBuffer = channelData;
      }

      // Convert to PCM
      const pcmBuffer = new Int16Array(processedBuffer.length);
      // Convert to µ-law
      const mulawBuffer = new Uint8Array(processedBuffer.length);

      for (let i = 0; i < processedBuffer.length; i++) {
        let s = processedBuffer[i];
        s = Math.max(-1, Math.min(1, s));
        pcmBuffer[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        mulawBuffer[i] = encodeMuLaw(s);
      }

      // Create a Uint8Array view over the PCM data.
      const byteBuffer = new Uint8Array(pcmBuffer.buffer);

      // Send the base64 encoded PCM audio to the main thread.
      this.port.postMessage({
        pcmBuffer: pcmBuffer,
        uint8Buffer: byteBuffer,
        mulawBuffer: mulawBuffer
      });

      // Returning true keeps the processor alive.
      return true;
    }
  }

  // Helper function to downsample a Float32Array buffer from inputRate to outputRate.
  function downsampleBuffer(buffer, inputRate, outputRate) {
    if (outputRate > inputRate) {
      throw new Error("Output rate must be lower than input rate for downsampling.");
    }
    const sampleRateRatio = inputRate / outputRate;
    const newLength = Math.floor(buffer.length / sampleRateRatio);
    const result = new Float32Array(newLength);
    let offsetResult = 0;
    let offsetBuffer = 0;
    while (offsetResult < result.length) {
      const nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio);
      // Average samples in the chunk to reduce aliasing.
      let accum = 0, count = 0;
      for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
        accum += buffer[i];
        count++;
      }
      result[offsetResult] = accum / count;
      offsetResult++;
      offsetBuffer = nextOffsetBuffer;
    }
    return result;
  }



  // Register the processor under the name 'audio-processor'
  registerProcessor('audio-processor', AudioProcessor);
