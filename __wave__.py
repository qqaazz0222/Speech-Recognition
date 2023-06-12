# import pyaudio
# import numpy as np
# import time
# import matplotlib.pyplot as plt
# import pyaudio
# from six.moves import queue

# # Audio recording parameters
# RATE = 16000
# CHUNK = int(RATE / 10)  # 100ms

# class MicrophoneStream(object):
#     """Opens a recording stream as a generator yielding the audio chunks."""
#     def __init__(self, rate, chunk):
#         self._rate = rate
#         self._chunk = chunk

#         # Create a thread-safe buffer of audio data
#         self._buff = queue.Queue()
#         self.closed = True

#     def __enter__(self):
#         self._audio_interface = pyaudio.PyAudio()
#         self._audio_stream = self._audio_interface.open(
#             format=pyaudio.paInt16,
#             # The API currently only supports 1-channel (mono) audio
#             # https://goo.gl/z757pE
#             channels=1, rate=self._rate,
#             input=True, frames_per_buffer=self._chunk,
#             # Run the audio stream asynchronously to fill the buffer object.
#             # This is necessary so that the input device's buffer doesn't
#             # overflow while the calling thread makes network requests, etc.
#             stream_callback=self._fill_buffer,
#         )

#         self.closed = False

#         return self

#     def __exit__(self, type, value, traceback):
#         self._audio_stream.stop_stream()
#         self._audio_stream.close()
#         self.closed = True
#         # Signal the generator to terminate so that the client's
#         # streaming_recognize method will not block the process termination.
#         self._buff.put(None)
#         self._audio_interface.terminate()

#     def _fill_buffer(self, in_data, frame_count, time_info, status_flags):
#         """Continuously collect data from the audio stream, into the buffer."""
#         self._buff.put(in_data)
#         return None, pyaudio.paContinue

#     def generator(self):
#         while not self.closed:
#             # Use a blocking get() to ensure there's at least one chunk of
#             # data, and stop iteration if the chunk is None, indicating the
#             # end of the audio stream.
#             chunk = self._buff.get()
#             if chunk is None:
#                 return
#             data = [chunk]

#             # Now consume whatever other data's still buffered.
#             while True:
#                 try:
#                     chunk = self._buff.get(block=False)
#                     if chunk is None:
#                         return
#                     data.append(chunk)
#                 except queue.Empty:
#                     break

#             yield b''.join(data)

# def plot_audio(audio_gen) :
#     full_frame=[]
#     for i, x in enumerate(audio_gen):
#         # x=np.fromstring(x, np.int16)
#         full_frame.append(x)
#         str_frame = ''.join(full_frame)
#         wav = np.fromstring(str_frame, np.int16)
#         plt.cla()
#         plt.axis([0, CHUNK * 10, -5000, 5000])
#         try:
#             plt.plot(wav[-CHUNK * 10:])
#         except:
#             plt.plot(wav)
#         plt.pause(0.01)

# def main():
#     plt.ion()
#         with MicrophoneStream(RATE, CHUNK) as stream:
#         audio_generator = stream.generator()
#         plot_audio(audio_generator)

#         print(list(audio_generator))



# if __name__ == '__main__':
#     main()
#     print("end main")

import argparse
import queue
import sys


def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    '-l', '--list-devices', action='store_true',
    help='show list of audio devices and exit')
parser.add_argument(
    '-d', '--device', type=int_or_str,
    help='input device (numeric ID or substring)')
parser.add_argument(
    '-w', '--window', type=float, default=200, metavar='DURATION',
    help='visible time slot (default: %(default)s ms)')
parser.add_argument(
    '-i', '--interval', type=float, default=30,
    help='minimum time between plot updates (default: %(default)s ms)')
parser.add_argument(
    '-b', '--blocksize', type=int, help='block size (in samples)')
parser.add_argument(
    '-r', '--samplerate', type=float, help='sampling rate of audio device')
parser.add_argument(
    '-n', '--downsample', type=int, default=10, metavar='N',
    help='display every Nth sample (default: %(default)s)')
parser.add_argument(
    'channels', type=int, default=[1], nargs='*', metavar='CHANNEL',
    help='input channels to plot (default: the first)')
args = parser.parse_args()
if any(c < 1 for c in args.channels):
    parser.error('argument CHANNEL: must be >= 1')
mapping = [c - 1 for c in args.channels]  # Channel numbers start with 1
q = queue.Queue()


def audio_callback(indata, frames, time, status):
    """This is called (from a separate thread) for each audio block."""
    if status:
        print(status, file=sys.stderr)
    # Fancy indexing with mapping creates a (necessary!) copy:
    q.put(indata[::args.downsample, mapping])


def update_plot(frame):
    """This is called by matplotlib for each plot update.

    Typically, audio callbacks happen more frequently than plot updates,
    therefore the queue tends to contain multiple blocks of audio data.

    """
    global plotdata
    while True:
        try:
            data = q.get_nowait()
        except queue.Empty:
            break
        shift = len(data)
        plotdata = np.roll(plotdata, -shift, axis=0)
        plotdata[-shift:, :] = data
    for column, line in enumerate(lines):
        line.set_ydata(plotdata[:, column])
    return lines


try:
    from matplotlib.animation import FuncAnimation
    import matplotlib.pyplot as plt
    import numpy as np
    import sounddevice as sd

    if args.list_devices:
        print(sd.query_devices())
        parser.exit(0)
    if args.samplerate is None:
        device_info = sd.query_devices(args.device, 'input')
        args.samplerate = device_info['default_samplerate']

    length = int(args.window * args.samplerate / (1000 * args.downsample))
    plotdata = np.zeros((length, len(args.channels)))

    fig, ax = plt.subplots()
    lines = ax.plot(plotdata)
    if len(args.channels) > 1:
        ax.legend(['channel {}'.format(c) for c in args.channels],
                  loc='lower left', ncol=len(args.channels))
    ax.axis((0, len(plotdata), -1, 1))
    ax.set_yticks([0])
    ax.yaxis.grid(True)
    ax.tick_params(bottom='off', top='off', labelbottom='off',
                   right='off', left='off', labelleft='off')
    fig.tight_layout(pad=0)

    stream = sd.InputStream(
        device=args.device, channels=max(args.channels),
        samplerate=args.samplerate, callback=audio_callback)
    ani = FuncAnimation(fig, update_plot, interval=args.interval, blit=True)
    with stream:
        plt.show()
except Exception as e:
    parser.exit(type(e).__name__ + ': ' + str(e))
[출처] [Python] Microphone signal real time graph|작성자 live for dream