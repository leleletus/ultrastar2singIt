"""Sync editor: plays a song with its video, its lyrics and its notes the way the game shows them, moves the lyrics
(#GAP) and can listen to the microphone to check the notes while singing."""
import bisect
import json
import math
import os
import re
import sys
from html import escape

import numpy as np
from PySide6.QtCore import Qt, QUrl, QTimer, QElapsedTimer, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
                               QSlider, QWidget, QMessageBox, QComboBox, QCheckBox, QSpinBox, QStyle, QFrame,
                               QSizePolicy)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudioSource, QAudioFormat, QMediaDevices
from PySide6.QtMultimediaWidgets import QVideoWidget

import UltrastarToSingit
import naming
from i18n import tr

LANE_SECONDS = 6.0        # seconds of notes visible in the lane
PLAYHEAD = 0.3            # playhead position in the lane (fraction of its width)
HIT_SEMITONES = 1.0       # sung pitch counted as right within this distance (any octave, like the game)
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
SPEEDS = (0.5, 0.75, 1.0, 1.25)


def note_name(midi):
    m = int(round(midi))
    return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


def fmt_time(seconds):
    sign = '-' if seconds < 0 else ''
    seconds = abs(seconds)
    return f"{sign}{int(seconds // 60):02d}:{seconds % 60:05.2f}"


def detect_pitch(samples, sample_rate, fmin=70.0, fmax=1100.0, threshold=0.15, min_rms=0.01):
    """Fundamental frequency (Hz) of a mono float block in [-1, 1] with the YIN method, None if there is no voice."""
    x = np.asarray(samples, dtype=np.float64)
    x = x - x.mean()
    if len(x) < 64 or math.sqrt(float(np.mean(x * x))) < min_rms:
        return None
    n = len(x)
    tau_max = min(int(sample_rate / fmin), n // 2)
    tau_min = max(2, int(sample_rate / fmax))
    if tau_max <= tau_min + 2:
        return None
    w = n - tau_max
    size = 1 << (n + w).bit_length()
    corr = np.fft.irfft(np.fft.rfft(x, size) * np.conj(np.fft.rfft(x[:w], size)), size)[:tau_max + 1]
    cum = np.concatenate(([0.0], np.cumsum(x * x)))
    taus = np.arange(tau_max + 1)
    diff = cum[w] + (cum[taus + w] - cum[taus]) - 2 * corr
    cmnd = np.ones_like(diff)
    running = np.cumsum(diff[1:])
    cmnd[1:] = diff[1:] * taus[1:] / np.where(running > 0, running, 1)
    below = np.nonzero(cmnd[tau_min:tau_max] < threshold)[0]
    if len(below):
        tau = tau_min + int(below[0])
        while tau + 1 < tau_max and cmnd[tau + 1] < cmnd[tau]:
            tau += 1
    else:
        tau = tau_min + int(np.argmin(cmnd[tau_min:tau_max]))
        if cmnd[tau] > 0.35:
            return None
    if 1 <= tau < tau_max:  # parabolic interpolation around the minimum
        a, b, c = cmnd[tau - 1], cmnd[tau], cmnd[tau + 1]
        den = a - 2 * b + c
        if den:
            tau = tau + 0.5 * (a - c) / den
    return sample_rate / tau if tau > 0 else None


def hz_to_midi(hz):
    return 69 + 12 * math.log2(hz / 440.0)


def fold_to(midi, target):
    """The same pitch class in the octave closest to target (the game does not care about the octave)."""
    return midi + 12 * round((target - midi) / 12)


class Note:
    __slots__ = ('t', 'd', 'pitch', 'kind')

    def __init__(self, t, d, pitch, kind):
        self.t, self.d, self.pitch, self.kind = t, d, pitch, kind

    @property
    def sung(self):  # rap/freestyle notes have no pitch
        return self.kind in (':', '*')


def load_txt(us_data):
    """Notes and shown syllables of an UltraStar txt, in seconds without #GAP."""
    bpm = float(us_data["BPM"].replace(',', '.'))
    beat = 60.0 / bpm / 4
    notes, syllables, lines, line = [], [], [], []
    for n in us_data["notes"]:
        if n[0] in (':', '*', 'F', 'R', 'G'):
            t, d = int(n[1]) * beat, max(int(n[2]), 1) * beat
            notes.append(Note(t, d, int(n[3]) + 60, n[0]))  # UltraStar pitch 0 = C4 = MIDI 60
            text = n[4].replace('~', '')
            if text.strip():
                line.append(len(syllables))
                syllables.append((t, d, text))
            elif text and syllables:  # "~ ": the space ends the previous word
                t0, d0, prev = syllables[-1]
                syllables[-1] = (t0, d0, prev if prev.endswith(' ') else prev + ' ')
        elif n[0] == '-' and line:
            lines.append(line)
            line = []
    if line:
        lines.append(line)
    return notes, syllables, lines


def load_official(path):
    """Notes and shown syllables of an official vxla, in seconds (the converter uses it as it is)."""
    import OfficialVxla
    layers, _ = OfficialVxla.read_layers(path)
    sing_it = OfficialVxla.to_sing_it(layers, 3600.0)
    notes = []
    for item in sing_it["notes"]:
        m = re.match(r'#p(\d+)#\.(.*)', item["value"])
        if not m:
            continue
        pitch, rest = int(m.group(1)), m.group(2)
        kind = 'F' if pitch <= 1 else ('*' if '#g' in rest else ':')
        notes.append(Note(item["t1"], item["t2"] - item["t1"], pitch, kind))
    syllables = [(s["t1"], s["t2"] - s["t1"], s["value"]) for s in sorted(sing_it["text"], key=lambda s: s["t1"])]
    pages = sorted((p["t1"], p["t2"]) for p in sing_it["pages"]) or [(0.0, 3600.0)]
    lines, page_ends = {}, [p[1] for p in pages]
    for i, (t, _, _) in enumerate(syllables):
        lines.setdefault(min(bisect.bisect_right(page_ends, t), len(pages) - 1), []).append(i)
    return sorted(notes, key=lambda n: n.t), syllables, [lines[k] for k in sorted(lines)]


class ClickSlider(QSlider):
    """Timeline: a click jumps to that point (a normal slider only moves one page)."""

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(),
                                                   int(event.position().x()), self.width())
            self.setValue(value)
            self.sliderMoved.emit(value)
        super().mousePressEvent(event)


class NoteLane(QWidget):
    """Notes as bars by pitch and time, with the playhead and the sung pitch, like the game."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def paintEvent(self, _event):
        ed = self.editor
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor('#101418'))
        now = ed.position_s()
        shift = ed.shift_s()
        t0 = now - PLAYHEAD * LANE_SECONDS
        x_of = lambda t: (t - t0) / LANE_SECONDS * w
        lo, hi = ed.pitch_lo, ed.pitch_hi
        rap_band = h - 14
        y_of = lambda m: 8 + (hi - m) / max(hi - lo, 1) * (rap_band - 24)

        for m in range(int(lo), int(hi) + 1):  # one guide per semitone, stronger on C
            p.setPen(QPen(QColor('#2a3440' if m % 12 == 0 else '#182028'), 1))
            p.drawLine(0, int(y_of(m)), w, int(y_of(m)))
            if m % 12 == 0:
                p.setPen(QColor('#5a6a7a'))
                p.drawText(4, int(y_of(m)) - 2, note_name(m))

        bar = max(6.0, (rap_band - 24) / max(hi - lo, 1) * 0.9)
        start = bisect.bisect_left(ed.note_starts, t0 - shift - 10)
        current = None
        for note in ed.notes[start:]:
            t = note.t + shift
            if t > t0 + LANE_SECONDS:
                break
            if t + note.d < t0:
                continue
            active = t <= now < t + note.d
            if note.sung:
                rect = QRectF(x_of(t), y_of(note.pitch) - bar / 2, max(3.0, note.d / LANE_SECONDS * w), bar)
                color = QColor('#ffcc33' if note.kind == '*' else '#4aa3ff')
                if active:
                    current = note
                    color = color.lighter(140)
            else:
                rect = QRectF(x_of(t), rap_band - 6, max(3.0, note.d / LANE_SECONDS * w), 6)
                color = QColor('#9a9a9a')
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(rect, 3, 3)

        # sung pitch (microphone): green right, red wrong, grey between notes
        for t, midi, state in ed.sung_window(t0, t0 + LANE_SECONDS):
            p.setBrush(QColor({1: '#3ddc84', 0: '#ff5c5c'}.get(state, '#8090a0')))
            p.drawEllipse(QPointF(x_of(t), y_of(midi)), 3, 3)

        x = x_of(now)
        p.setPen(QPen(QColor('#ffffff'), 2))
        p.drawLine(int(x), 0, int(x), h)
        if current is not None:
            p.setPen(QColor('#d0d8e0'))
            p.setFont(QFont(self.font().family(), 9, QFont.Bold))
            p.drawText(int(x) + 6, 14, tr("Note: {name}").format(name=note_name(current.pitch)))
        p.end()


class Microphone:
    """Reads the microphone and gives the pitch of the last ~50 ms."""

    def __init__(self, device):
        fmt = device.preferredFormat()
        self.rate = fmt.sampleRate()
        self.channels = max(1, fmt.channelCount())
        self.sample_format = fmt.sampleFormat()
        self.source = QAudioSource(device, fmt)
        self.io = self.source.start()
        self.buffer = np.zeros(0, dtype=np.float32)

    def read(self):
        data = bytes(self.io.readAll()) if self.io is not None else b''
        if not data:
            return
        width = {QAudioFormat.SampleFormat.Int16: 2, QAudioFormat.SampleFormat.Int32: 4,
                 QAudioFormat.SampleFormat.Float: 4}.get(self.sample_format, 1)
        data = data[:len(data) // width * width]
        if self.sample_format == QAudioFormat.SampleFormat.Int16:
            x = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        elif self.sample_format == QAudioFormat.SampleFormat.Int32:
            x = np.frombuffer(data, dtype=np.int32).astype(np.float32) / 2147483648.0
        elif self.sample_format == QAudioFormat.SampleFormat.Float:
            x = np.frombuffer(data, dtype=np.float32)
        else:  # UInt8
            x = (np.frombuffer(data, dtype=np.uint8).astype(np.float32) - 128) / 128.0
        if self.channels > 1:
            x = x[:len(x) // self.channels * self.channels].reshape(-1, self.channels).mean(axis=1)
        self.buffer = np.concatenate((self.buffer, x))[-self.rate:]

    def pitch(self):
        block = self.buffer[-int(self.rate * 0.05):]
        hz = detect_pitch(block, self.rate) if len(block) else None
        return hz_to_midi(hz) if hz else None

    def stop(self):
        self.source.stop()
        self.io = None


class SyncEditorDialog(QDialog):
    def __init__(self, txt_path, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.txt_path = txt_path
        self.setWindowTitle(tr("Sync editor - {song}").format(song=os.path.basename(os.path.dirname(txt_path))))
        self.resize(1150, 860)
        self.saved = False

        self.us_data = UltrastarToSingit.parse_file(txt_path)
        self.gap_ms = float(self.us_data.get("GAP", "0").replace(',', '.') or 0)
        self.original_gap_ms = self.gap_ms
        try:
            self.video_gap_s = float(self.us_data.get("VIDEOGAP", "0").replace(',', '.') or 0)
        except ValueError:
            self.video_gap_s = 0.0

        song_dir = os.path.dirname(txt_path)
        folder = os.path.basename(song_dir).rstrip('.')
        name_id = naming.construct_name_id_from_directory_name(folder)
        official = os.path.join(song_dir, naming.OFFICIAL_VXLA_NAME)
        # songs rebuilt from DLC use their official vxla as it is: #GAP of the txt is not used there
        self.official = os.path.isfile(official)
        if self.official:
            self.notes, self.syllables, self.lines = load_official(official)
        else:
            self.notes, self.syllables, self.lines = load_txt(self.us_data)
        self.note_starts = [n.t for n in self.notes]
        sung = [n.pitch for n in self.notes if n.sung] or [60]
        self.pitch_lo, self.pitch_hi = min(sung) - 2, max(sung) + 2

        # The converted .ogg is what the game plays: VIDEOGAP is already applied to it, so the lyrics
        # (and not the video) are shifted by VIDEOGAP. With the original audio it is the other way round.
        converted_ogg = os.path.join(song_dir, name_id + naming.AUDIO_SUFFIX)
        self.audio_is_converted = os.path.isfile(converted_ogg)
        # #START handling of the converter: how much the lyrics were moved, and the audio cut
        self.start_offset_s, self.trim_start_s = 0.0, 0.0
        try:
            with open(os.path.join(song_dir, name_id + naming.AUDIO_META_SUFFIX), 'r', encoding='utf-8') as f:
                meta = json.load(f)
            self.start_offset_s = float(meta.get('lyrics_offset') or 0)
            self.trim_start_s = float(meta.get('trim_start') or 0)
        except (OSError, ValueError):
            pass
        self.audio_file = converted_ogg if self.audio_is_converted else None
        if self.audio_file is None:
            for tag in ("AUDIO", "MP3"):
                if self.us_data.get(tag) and os.path.isfile(os.path.join(song_dir, self.us_data[tag])):
                    self.audio_file = os.path.join(song_dir, self.us_data[tag])
                    break
        video = self.us_data.get("VIDEO")
        self.video_file = os.path.join(song_dir, video) if video and os.path.isfile(os.path.join(song_dir, video)) \
            else None

        # playback clock: the player reports its position only every few frames, it is interpolated in between
        self.clock = QElapsedTimer()
        self.clock_base_ms = 0
        self.duration_ms = 0
        self.last_resync = 0
        self.mic = None
        self.sung = []          # (audio time s, folded midi, 1 right / 0 wrong / None between notes)
        self.mic_stats = {}     # note index -> [right, total]

        self.build_ui()
        self.load_media()
        self.update_info()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(30)

    # ------------------------------------------------------------------ interface
    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setStyleSheet("padding: 6px; border-radius: 4px;")
        layout.addWidget(self.info)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(240)
        layout.addWidget(self.video_widget, stretch=3)

        self.lane = NoteLane(self)
        layout.addWidget(self.lane, stretch=2)

        self.lyrics_display = QLabel()
        self.lyrics_display.setAlignment(Qt.AlignCenter)
        self.lyrics_display.setTextFormat(Qt.RichText)
        self.lyrics_display.setMinimumHeight(110)
        self.lyrics_display.setStyleSheet("background-color: black; padding: 8px;")
        layout.addWidget(self.lyrics_display)

        # timeline
        time_row = QHBoxLayout()
        self.lbl_time = QLabel("00:00.00 / 00:00.00")
        self.lbl_time.setStyleSheet("font-family: monospace; font-size: 14px;")
        self.slider = ClickSlider(Qt.Horizontal)
        self.slider.setFocusPolicy(Qt.NoFocus)
        self.slider.sliderMoved.connect(self.seek_ms)
        time_row.addWidget(self.slider, stretch=1)
        time_row.addWidget(self.lbl_time)
        layout.addLayout(time_row)

        # transport
        transport = QHBoxLayout()

        def button(text, tip, slot, keys=()):
            b = QPushButton(text)
            b.setFocusPolicy(Qt.NoFocus)
            b.setToolTip(tip + (f"  [{', '.join(keys)}]" if keys else ""))
            b.clicked.connect(slot)
            for k in keys:
                QShortcut(QKeySequence(k), self, activated=slot)
            transport.addWidget(b)
            return b

        button("⏮", tr("Go to the start"), lambda: self.seek_s(0), ("Home",))
        button("⤒ " + tr("Previous line"), tr("Previous line"), lambda: self.jump_line(-1), ("Up",))
        button("⏪ 5 s", tr("Back 5 seconds"), lambda: self.skip(-5), ("J",))
        button("◀ 0.1 s", tr("Back 0.1 seconds"), lambda: self.skip(-0.1), (",",))
        self.btn_play = button("▶ / ⏸", tr("Play / pause"), self.toggle_play, ("Space",))
        self.btn_play.setMinimumWidth(90)
        button("0.1 s ▶", tr("Forward 0.1 seconds"), lambda: self.skip(0.1), (".",))
        button("5 s ⏩", tr("Forward 5 seconds"), lambda: self.skip(5), ("L",))
        button(tr("Next line") + " ⤓", tr("Next line"), lambda: self.jump_line(1), ("Down",))
        button("🎤 " + tr("First lyrics"), tr("Go to just before the first lyrics"), self.go_first_lyrics, ("F",))
        transport.addStretch(1)
        transport.addWidget(QLabel(tr("Speed")))
        self.speed = QComboBox()
        self.speed.setFocusPolicy(Qt.NoFocus)
        for s in SPEEDS:
            self.speed.addItem(f"{s:g}×", s)
        self.speed.setCurrentIndex(SPEEDS.index(1.0))
        self.speed.currentIndexChanged.connect(self.set_speed)
        transport.addWidget(self.speed)
        transport.addWidget(QLabel(tr("Volume")))
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setFocusPolicy(Qt.NoFocus)
        self.volume.setRange(0, 100)
        self.volume.setValue(100)
        self.volume.setFixedWidth(90)
        self.volume.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100))
        transport.addWidget(self.volume)
        layout.addLayout(transport)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        # lyrics offset
        gap_grid = QGridLayout()
        self.gap_buttons = []
        for col, (text, amount, keys) in enumerate((("◀◀◀ -250 ms", -250, ("Ctrl+Left",)),
                                                    ("◀◀ " + tr("Lyrics earlier") + " -50 ms", -50, ("Left",)),
                                                    ("◀ -10 ms", -10, ("Shift+Left",)),
                                                    (None, 0, ()),
                                                    ("+10 ms ▶", 10, ("Shift+Right",)),
                                                    (tr("Lyrics later") + " +50 ms ▶▶", 50, ("Right",)),
                                                    ("+250 ms ▶▶▶", 250, ("Ctrl+Right",)))):
            if text is None:
                self.lbl_gap = QLabel()
                self.lbl_gap.setAlignment(Qt.AlignCenter)
                self.lbl_gap.setStyleSheet("font-weight: bold; font-size: 16px;")
                gap_grid.addWidget(self.lbl_gap, 0, col)
                continue
            b = QPushButton(text)
            b.setFocusPolicy(Qt.NoFocus)
            b.setToolTip(tr("Move the lyrics") + f"  [{keys[0]}]")
            b.clicked.connect(lambda _=False, a=amount: self.adjust_gap(a))
            QShortcut(QKeySequence(keys[0]), self, activated=lambda a=amount: self.adjust_gap(a))
            gap_grid.addWidget(b, 0, col)
            self.gap_buttons.append(b)
        self.gap_slider = QSlider(Qt.Horizontal)
        self.gap_slider.setFocusPolicy(Qt.NoFocus)
        self.gap_slider.setRange(int(min(-10000, self.gap_ms - 10000)), int(max(10000, self.gap_ms + 10000)))
        self.gap_slider.setValue(int(self.gap_ms))
        self.gap_slider.sliderMoved.connect(lambda v: self.set_gap(float(v)))
        self.gap_slider.setStyleSheet("QSlider::handle:horizontal { background: #ffaa00; width: 15px; }")
        gap_grid.addWidget(QLabel(tr("Move the whole lyrics track (left / right):")), 1, 0, 1, 2)
        gap_grid.addWidget(self.gap_slider, 1, 2, 1, 5)
        layout.addLayout(gap_grid)

        # sing mode and saving
        bottom = QHBoxLayout()
        self.chk_sing = QCheckBox("🎤 " + tr("Sing mode (check the notes)"))
        self.chk_sing.setFocusPolicy(Qt.NoFocus)
        self.chk_sing.setToolTip(tr("Listens to the microphone and draws your voice over the notes, like the game. "
                                    "Use headphones so the microphone does not hear the song."))
        self.chk_sing.toggled.connect(self.toggle_sing)
        bottom.addWidget(self.chk_sing)
        self.mic_choice = QComboBox()
        self.mic_choice.setFocusPolicy(Qt.NoFocus)
        for dev in QMediaDevices.audioInputs():
            self.mic_choice.addItem(dev.description(), dev)
        default = QMediaDevices.defaultAudioInput().description()
        if self.mic_choice.findText(default) >= 0:
            self.mic_choice.setCurrentIndex(self.mic_choice.findText(default))
        bottom.addWidget(self.mic_choice)
        bottom.addWidget(QLabel(tr("Mic delay")))
        self.mic_delay = QSpinBox()
        self.mic_delay.setFocusPolicy(Qt.ClickFocus)
        self.mic_delay.setRange(0, 500)
        self.mic_delay.setSingleStep(10)
        self.mic_delay.setValue(100)
        self.mic_delay.setSuffix(" ms")
        self.mic_delay.setToolTip(tr("How late the microphone hears you; raise it if your voice is drawn after the notes."))
        bottom.addWidget(self.mic_delay)
        self.lbl_score = QLabel()
        self.lbl_score.setStyleSheet("font-weight: bold;")
        bottom.addWidget(self.lbl_score, stretch=1)

        self.btn_reset = QPushButton(tr("Undo changes"))
        self.btn_reset.setFocusPolicy(Qt.NoFocus)
        self.btn_reset.clicked.connect(lambda: self.set_gap(self.original_gap_ms))
        bottom.addWidget(self.btn_reset)
        self.btn_save = QPushButton(tr("Save sync changes"))
        self.btn_save.setFocusPolicy(Qt.NoFocus)
        self.btn_save.clicked.connect(self.save_gap)
        self.btn_save.setStyleSheet("QPushButton { background-color: green; color: white; font-size: 15px; "
                                    "padding: 8px 16px; } QPushButton:disabled { background-color: #555; color: #aaa; }")
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_gap)
        bottom.addWidget(self.btn_save)
        layout.addLayout(bottom)

        if self.official:
            for w in self.gap_buttons + [self.gap_slider, self.btn_reset, self.btn_save]:
                w.setEnabled(False)
        self.set_gap(self.gap_ms)

    def load_media(self):
        self.video_player = QMediaPlayer(self)
        self.video_player.setVideoOutput(self.video_widget)
        self.audio_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(1.0)
        self.audio_player.setAudioOutput(self.audio_output)
        if self.video_file:
            self.video_player.setSource(QUrl.fromLocalFile(self.video_file))
        if self.audio_file:
            self.audio_player.setSource(QUrl.fromLocalFile(self.audio_file))
        self.audio_player.positionChanged.connect(self.on_position)
        self.audio_player.durationChanged.connect(self.on_duration)
        self.audio_player.playbackStateChanged.connect(self.on_state)

    def update_info(self):
        notes = []
        if self.official:
            notes.append(tr("This song uses the official Let's Sing lyrics file: its timing is the game's own and "
                            "#GAP is not used, so it cannot be moved here. You can still play it and check the "
                            "notes with the sing mode."))
        if self.syllables and self.duration_ms:
            end = self.syllables[-1][0] + self.syllables[-1][1] + self.shift_s()
            if end > self.duration_ms / 1000 + 1:
                notes.append(tr("The lyrics end {s:.1f} s after the audio: the audio is probably another version of "
                                "the song and no #GAP will fix it.").format(s=end - self.duration_ms / 1000))
        if not self.audio_file:
            notes.append(tr("No audio file found for this song."))
        audio = os.path.basename(self.audio_file) if self.audio_file else "-"
        video = os.path.basename(self.video_file) if self.video_file else tr("no video")
        text = tr("Audio: {audio} · Video: {video}").format(audio=audio, video=video)
        if notes:
            self.info.setStyleSheet("padding: 6px; border-radius: 4px; background: #5a4300; color: white;")
            text = "⚠ " + "<br>⚠ ".join(escape(n) for n in notes) + "<br><small>" + escape(text) + "</small>"
        else:
            self.info.setStyleSheet("padding: 6px; border-radius: 4px; background: #1f2a33; color: #c8d2dc;")
            text = escape(text)
        self.info.setText(text)

    # ------------------------------------------------------------------ playback
    def playing(self):
        return self.audio_player.playbackState() == QMediaPlayer.PlayingState

    def position_s(self):
        if self.playing() and self.clock.isValid():
            return (self.clock_base_ms + self.clock.elapsed() * self.audio_player.playbackRate()) / 1000.0
        return self.audio_player.position() / 1000.0

    def on_position(self, position):
        self.clock_base_ms = position
        self.clock.restart()
        if not self.slider.isSliderDown():
            self.slider.blockSignals(True)
            self.slider.setValue(position)
            self.slider.blockSignals(False)

    def on_duration(self, duration):
        self.duration_ms = duration
        self.slider.setRange(0, duration)
        self.update_info()

    def on_state(self, _state):
        self.clock_base_ms = self.audio_player.position()
        self.clock.restart()

    def video_offset_ms(self):
        return 0 if self.audio_is_converted else int(self.video_gap_s * 1000)

    def toggle_play(self):
        if self.playing():
            self.audio_player.pause()
            self.video_player.pause()
        else:
            self.video_player.setPosition(max(0, self.audio_player.position() + self.video_offset_ms()))
            self.audio_player.play()
            self.video_player.play()

    def seek_ms(self, position):
        position = int(max(0, min(position, self.duration_ms or position)))
        self.audio_player.setPosition(position)
        self.video_player.setPosition(max(0, position + self.video_offset_ms()))
        self.clock_base_ms = position
        self.clock.restart()

    def seek_s(self, seconds):
        self.seek_ms(seconds * 1000)

    def skip(self, seconds):
        self.seek_s(self.position_s() + seconds)

    def set_speed(self, _index):
        rate = self.speed.currentData()
        self.audio_player.setPlaybackRate(rate)
        self.video_player.setPlaybackRate(rate)

    def line_start_s(self, index):
        return self.syllables[self.lines[index][0]][0] + self.shift_s()

    def jump_line(self, step):
        if not self.lines:
            return
        now = self.position_s() + 0.05
        starts = [self.line_start_s(i) for i in range(len(self.lines))]
        current = max(0, bisect.bisect_right(starts, now) - 1)
        target = min(max(current + step, 0), len(self.lines) - 1)
        if step < 0 and now - starts[current] > 1.0:
            target = current  # like a player: first back to the start of this line
        self.seek_s(max(0.0, starts[target] - 0.5))

    def go_first_lyrics(self):
        if self.lines:
            self.seek_s(max(0.0, self.line_start_s(0) - 2.0))

    def tick(self):
        now = self.position_s()
        total = self.duration_ms / 1000.0
        self.lbl_time.setText(f"{fmt_time(now)} / {fmt_time(total)}")
        if self.playing() and self.video_file and self.clock.isValid():
            # keep the video on the audio (the two players drift apart a little)
            self.last_resync += 1
            if self.last_resync >= 30:
                self.last_resync = 0
                expected = now * 1000 + self.video_offset_ms()
                if abs(self.video_player.position() - expected) > 150:
                    self.video_player.setPosition(max(0, int(expected)))
        if self.mic is not None:
            self.listen(now)
        self.update_lyrics(now)
        self.lane.update()

    # ------------------------------------------------------------------ lyrics offset
    def shift_s(self):
        """Seconds added to the times of the notes to place them on the audio being played."""
        if self.official:
            return 0.0
        if self.audio_is_converted:
            return self.gap_ms / 1000.0 + self.video_gap_s - self.start_offset_s
        # original audio: only moved when it is a shorter version that already starts at #START
        return self.gap_ms / 1000.0 - (self.start_offset_s - self.trim_start_s)

    def gap_text(self):
        text = tr("Offset (GAP): {gap} ms").format(gap=int(round(self.gap_ms)))
        change = self.gap_ms - self.original_gap_ms
        return text + (f"  ({change:+.0f})" if change else "")

    def set_gap(self, value):
        self.gap_ms = float(value)
        self.lbl_gap.setText(self.gap_text())
        self.gap_slider.blockSignals(True)
        self.gap_slider.setValue(int(self.gap_ms))
        self.gap_slider.blockSignals(False)
        self.update_info()

    def adjust_gap(self, amount):
        if not self.official:
            self.set_gap(self.gap_ms + amount)

    def update_lyrics(self, now):
        shift = self.shift_s()
        if not self.lines:
            self.lyrics_display.setText("")
            return
        active = len(self.lines) - 1
        for i, line in enumerate(self.lines):
            t, d, _ = self.syllables[line[-1]]
            if now <= t + d + shift + 0.5:
                active = i
                break

        def plain(i, color, size):
            if not 0 <= i < len(self.lines):
                return f"<span style='font-size:{size}px;'>&nbsp;</span>"
            text = ''.join(escape(self.syllables[k][2]) for k in self.lines[i])
            return f"<span style='color:{color}; font-size:{size}px;'>{text}</span>"

        current = []
        for k in self.lines[active]:
            t, d, text = self.syllables[k]
            if now >= t + d + shift:
                color = '#3ddc84'
            elif now >= t + shift:
                color = '#ffe14d'
            else:
                color = '#ffffff'
            current.append(f"<span style='color:{color};'>{escape(text)}</span>")
        html = (plain(active - 1, '#8a8a8a', 18) + "<br>"
                + f"<span style='font-size:28px; font-weight:bold;'>{''.join(current)}</span><br>"
                + plain(active + 1, '#8a8a8a', 18))
        self.lyrics_display.setText(f"<div align='center'>{html}</div>")

    # ------------------------------------------------------------------ sing mode
    def toggle_sing(self, on):
        if on:
            device = self.mic_choice.currentData()
            try:
                self.mic = Microphone(device or QMediaDevices.defaultAudioInput())
            except Exception as e:
                self.mic = None
                self.chk_sing.setChecked(False)
                QMessageBox.warning(self, tr("Error"), tr("Could not open the microphone: {error}").format(error=e))
                return
            self.sung, self.mic_stats = [], {}
            self.lbl_score.setText(tr("Sing! Your voice is drawn over the notes."))
        elif self.mic is not None:
            self.mic.stop()
            self.mic = None

    def sung_window(self, t0, t1):
        start = bisect.bisect_left(self.sung, (t0,))
        for item in self.sung[start:]:
            if item[0] > t1:
                break
            yield item

    def listen(self, now):
        self.mic.read()
        if not self.playing():
            return
        midi = self.mic.pitch()
        t = now - self.mic_delay.value() / 1000.0
        if midi is None:
            return
        shift = self.shift_s()
        i = bisect.bisect_right(self.note_starts, t - shift) - 1
        state, shown = None, midi
        if i >= 0 and self.notes[i].t + shift <= t < self.notes[i].t + self.notes[i].d + shift:
            note = self.notes[i]
            if note.sung:
                shown = fold_to(midi, note.pitch)
                state = 1 if abs(shown - note.pitch) <= HIT_SEMITONES else 0
                stats = self.mic_stats.setdefault(i, [0, 0])
                stats[0] += state
                stats[1] += 1
        if state is None:  # between notes: drawn near the closest note
            near = self.notes[max(0, min(i, len(self.notes) - 1))] if self.notes else None
            shown = fold_to(midi, near.pitch if near and near.sung else (self.pitch_lo + self.pitch_hi) / 2)
        if self.sung and t < self.sung[-1][0]:  # after a seek back
            self.sung = [s for s in self.sung if s[0] < t]
        self.sung.append((t, shown, state))
        right = sum(1 for r, n in self.mic_stats.values() if n and r / n >= 0.5)
        frames = sum(n for _, n in self.mic_stats.values())
        hits = sum(r for r, _ in self.mic_stats.values())
        detail = tr("You sing {sung}").format(sung=note_name(midi))
        if state is not None:
            cents = (shown - self.notes[i].pitch) * 100
            detail += tr(" · note {note} ({cents:+.0f} cents)").format(note=note_name(self.notes[i].pitch), cents=cents)
        self.lbl_score.setText(tr("Notes right: {right}/{total} · on pitch {pct:.0f}%").format(
            right=right, total=len(self.mic_stats), pct=100 * hits / frames if frames else 0) + " · " + detail)

    # ------------------------------------------------------------------ closing and saving
    def stop_players(self):
        if getattr(self, 'mic', None) is not None:
            self.mic.stop()
            self.mic = None
        if hasattr(self, 'audio_player'):
            self.audio_player.stop()
        if hasattr(self, 'video_player'):
            self.video_player.stop()

    def accept(self):
        self.stop_players()
        super().accept()

    def reject(self):
        self.stop_players()
        super().reject()

    def closeEvent(self, event):
        if self.gap_ms != self.original_gap_ms:
            reply = QMessageBox.question(self, tr('Unsaved changes'),
                                         tr('Save the sync changes before closing?'),
                                         QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                self.save_gap()
                event.accept()
            elif reply == QMessageBox.No:
                self.stop_players()
                event.accept()
            else:
                event.ignore()
        else:
            self.stop_players()
            event.accept()

    def save_gap(self):
        """Writes #GAP back keeping the file's encoding and line endings (and adds it if missing)."""
        if self.official:
            return
        try:
            with open(self.txt_path, 'rb') as f:
                raw = f.read()
            encoding = UltrastarToSingit._detect_encoding_bytes(raw)
            if encoding == 'utf-8-sig' and not raw.startswith(b'\xef\xbb\xbf'):
                encoding = 'utf-8'
            text = raw.decode(encoding)
            newline = '\r\n' if '\r\n' in text else '\n'
            lines = text.splitlines()

            gap_value = int(round(self.gap_ms))
            gap_line = f"#GAP:{gap_value}"
            for i, line in enumerate(lines):
                if line.upper().startswith("#GAP:"):
                    lines[i] = gap_line
                    break
            else:
                # no #GAP tag: insert it after the last header line
                insert_at = 0
                for i, line in enumerate(lines):
                    if line.startswith('#'):
                        insert_at = i + 1
                    elif line.strip():
                        break
                lines.insert(insert_at, gap_line)

            if not os.path.exists(self.txt_path + '.bak'):
                # the first time a song is re-synced its original txt is kept, the GAP can always be restored
                with open(self.txt_path + '.bak', 'wb') as f:
                    f.write(raw)
            tmp_path = self.txt_path + '.tmp'
            with open(tmp_path, 'w', encoding=encoding, newline='') as f:
                f.write(newline.join(lines) + newline)
            os.replace(tmp_path, self.txt_path)

            self.original_gap_ms = self.gap_ms  # Prevent unsaved changes prompt on app exit
            self.saved = True
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), tr("Could not save the sync changes: {error}").format(error=e))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    if len(sys.argv) > 1:
        dialog = SyncEditorDialog(sys.argv[1])
        dialog.exec()
