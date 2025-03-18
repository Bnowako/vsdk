import audioop


def mulaw_to_pcm(mulaw_data: bytes):
    pcm_data = audioop.ulaw2lin(mulaw_data, 2)
    return pcm_data
