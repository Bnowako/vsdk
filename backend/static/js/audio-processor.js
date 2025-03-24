class AudioProcessor extends AudioWorkletProcessor {
    process(inputs, outputs, parameters) {
        const input = inputs[0][0];
        if (!input) return true;

        // Convert Float32Array to Int16Array to MuLaw
        const int16Data = Int16Array.from(input, s => {
            s = Math.max(-1, Math.min(1, s));
            return s < 0 ? s * 32768 : s * 32767;
        });

        // Convert to MuLaw (using the same conversion logic)
        const muLawData = new Uint8Array(int16Data.length);
        for (let i = 0; i < int16Data.length; i++) {
            muLawData[i] = this.linearToMuLawSample(int16Data[i]);
        }

        // Send the processed data to the main thread
        this.port.postMessage({
            audioData: muLawData
        });

        return true;
    }

    linearToMuLawSample(sample) {
        const CLIP = 32635;
        const BIAS = 0x84;

        sample = Math.max(-CLIP, Math.min(CLIP, sample));
        let sign = sample < 0 ? 0x80 : 0;
        if (sign) sample = -sample;
        sample += BIAS;

        const exponent = this.getExponent(sample);
        const mantissa = (sample >> (exponent + 3)) & 0x0F;
        return ~(sign | (exponent << 4) | mantissa);
    }

    getExponent(sample) {
        let exponent = 7;
        for (let expMask = 0x4000; (sample & expMask) === 0 && exponent > 0; exponent--, expMask >>= 1);
        return exponent;
    }
}

registerProcessor('audio-processor', AudioProcessor);
