from __future__ import annotations
import numpy as np
from stftpitchshift import StftPitchShift

INPUT_BUFFER_MIN_LENGTH = 2048 * 2 # At this length, shift and start to generate additional output
INPUT_BUFFER_MAX_LENGTH = 2048 * 4 # Roughly 2 output requests worth of lookahead

# Unlike other stretchers, this one doesn't directly transform input frames into output.
# It asynchronously pulls in input to keep its buffer filled and transforms it into an internal buffer.
# Then all the output stream does is request frames, which it provides.
class StftStretcher:
    stftPitchShift: StftPitchShift = StftPitchShift(
        1024, # Frame size
        256, # Hop size
        44100 # Sample rate
        # Normalization (bool)
        # Chronometry (bool)
    )

    # Input buffer needs to remain over X length to have enough information for the Fourier transform
    input_buffer: np.ndarray = np.zeros(0, dtype=np.float32)

    # Output buffer contains results of stretch operation.
    # Generally should be speed * the number of frames coming in.
    output_buffer: np.ndarray = np.zeros(0, dtype=np.float32)

    speed: float = 1.0

    # Since it's a circular buffer, we need to know where we are in it.
    input_buffer_position: float = 0.0

    def __init__(self, audioTrack):
        self.reset()
        self.audioTrack = audioTrack

    def get_samples(self, num_frames_requested: int) -> np.ndarray:
        result = self.drain_output_buffer(num_frames_requested)
        # For now assume we'll always have enough. In exception just return zeros.
        if result is None:
            result = np.zeros(num_frames_requested * 2, dtype=np.float32)
        
        # Since input buffer doesn't actually know how many frames are in it, we need to calculate how many we've consumed.
        num_input_frames_consumed = int(num_frames_requested / self.speed)

        # Check if we need to pull more input data.
        input_buffer_len = len(self.input_buffer) // 2
        if (input_buffer_len - self.input_buffer_position) < INPUT_BUFFER_MIN_LENGTH:
            # Shift the input buffer by the amount of frames we've consumed.
            self.input_buffer = self.input_buffer[num_input_frames_consumed:]
            self.input_buffer_position -= num_input_frames_consumed
            # Pull in additional input data
            start_track_position = int(self.audioTrack.position * self.audioTrack.duration * 2)
            end_track_position = (start_track_position + INPUT_BUFFER_MIN_LENGTH * 2) # Pull half max frames
            new_samples = self.audioTrack.buffer.buffer[start_track_position:end_track_position]
            self.input_buffer = np.concatenate([self.input_buffer, new_samples])

            # Generate additional output.
            self.generate_output()

        return result

    def drain_output_buffer(self, num_frames_requested: int) -> np.ndarray | None:
        if self.output_buffer is None:
            return None
        if self.output_buffer.shape[0] < num_frames_requested:
            # Not enough output data to drain! Should never get here.
            return None
        
        num_samples_requested = num_frames_requested * 2

        # Enough data in the output buffer to return, do so
        result = self.output_buffer[:num_samples_requested].copy()
        self.output_buffer = self.output_buffer[num_samples_requested:]
        return result
    
    def generate_output(self):
        # Actually run the stretch operation
        left_channel = self.input_buffer[0::2]
        right_channel = self.input_buffer[1::2]
        left_channel_stretched = self.stretch_channel(left_channel)
        right_channel_stretched = self.stretch_channel(right_channel)
        stereo_stretched = np.concatenate([left_channel_stretched, right_channel_stretched])
        self.output_buffer = np.concatenate([self.output_buffer, stereo_stretched])
        self.input_buffer_position += len(stereo_stretched) / 2

    def stretch_channel(self, channel: np.ndarray) -> np.ndarray:
        semitones = self.speed_to_semitones(self.speed)
        if semitones == 0:
            return channel
        pitch_shifted = self.stftPitchShift.shiftpitch(channel, semitones)
        return pitch_shifted

    def speed_to_semitones(self, speed: float) -> float:
        # 2x speed is 12 semitones down,
        # 0.5x speed is 12 semitones up.
        return 12 * -np.log2(speed)


    def set_speed(self, speed: float):
        self.speed = speed
        self.reset()

    def on_seek(self):
        return self.reset()
    
    def reset(self):
        self.input_buffer = np.zeros(0, dtype=np.float32)
        self.output_buffer = np.zeros(0, dtype=np.float32)
        self.input_buffer_position = 0.0
