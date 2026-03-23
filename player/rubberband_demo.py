import rubberband
import soundfile

data, rate = soundfile.read('./player_redo/gravity.mp3', dtype='int16')
# rubberband expects mono (1D); convert stereo to mono if needed
if data.ndim > 1:
    data = data.mean(axis=1).astype('int16')
bitrate = rate * 16
nFrames = len(data)
print(f'Raw input type is : {type(data)}')

oldDuration = nFrames / rate
newDuration = oldDuration / 2  # 2x faster
ratio = (newDuration / oldDuration) ** 0.5  # rubberband applies ratio twice, so sqrt for desired 2x
print(f'Ratio is : {ratio}')

out=rubberband.stretch(data,rate=rate,ratio=ratio,crispness=5,formants=False,precise=True)
soundfile.write('./outfile.wav',out,rate,'PCM_16')
