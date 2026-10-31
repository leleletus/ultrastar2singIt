"""Sync editor: plays a song with its video, its lyrics and its notes the way the game shows them.

- Moves all the lyrics (#GAP) or, after a cut, only the lines from the cut on (a gap in the middle of the song).
- "Analyze voice" isolates the singer (Demucs) and draws the voice over the notes; the map under the video shows,
  line by line, whether the lyrics match the voice, and the wand moves a part to where the voice really is.
- Sing mode listens to the microphone and checks the notes, like the game.
"""
import bisect
import json
import os
import sys
import threading
from html import escape

import numpy as np
from PySide6.QtCore import Qt, QUrl, QTimer, QElapsedTimer, QRectF, QPointF, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QKeySequence, QShortcut, QPolygonF
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider,
                               QWidget, QMessageBox, QComboBox, QSpinBox, QStyle, QFrame, QSizePolicy, QToolButton)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudioSource, QAudioFormat, QMediaDevices
from PySide6.QtMultimediaWidgets import QVideoWidget

import SyncModel
import UltrastarToSingit
import naming
from GuiElement import make_icon
from SyncModel import detect_pitch, hz_to_midi, fold_to, note_name, load_txt, HIT_SEMITONES  # noqa: F401
from i18n import tr

LANE_SECONDS = 6.0        # seconds of notes visible in the lane
PLAYHEAD = 0.3            # playhead position in the lane (fraction of its width)
SPEEDS = (0.5, 0.75, 1.0, 1.25)
BLUE, GREEN, ORANGE, RED, GREY = '#2b7bb9', '#16a34a', '#d97706', '#dc2626', '#6b7280'


def fmt_time(seconds):
    sign = '-' if seconds < 0 else ''
    seconds = abs(seconds)
    return f"{sign}{int(seconds // 60):02d}:{seconds % 60:05.2f}"


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
    """Notes as bars by pitch and time, with the playhead, the isolated voice and the sung pitch, like the game."""

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

        # cuts: everything after them moves on its own
        p.setPen(QPen(QColor(ORANGE), 1, Qt.DashLine))
        for line in ed.splits:
            x = x_of(ed.line_time(line))
            if 0 <= x <= w:
                p.drawLine(int(x), 0, int(x), h)

        # isolated voice (after "Analyze voice"): where the singer really is
        if ed.voice is not None:
            frame = SyncModel.FRAME
            a, b = max(0, int(t0 / frame)), min(len(ed.voice['pitch']), int((t0 + LANE_SECONDS) / frame) + 1)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(120, 220, 255, 110))
            for i in range(a, b):
                pitch = ed.voice['pitch'][i]
                if ed.voice['active'][i] and not np.isnan(pitch):
                    near = ed.note_near(i * frame)
                    shown = fold_to(float(pitch), near.pitch if near is not None and near.sung
                                    else (lo + hi) / 2)
                    p.drawEllipse(QPointF(x_of(i * frame), y_of(shown)), 1.6, 1.6)

        bar = max(6.0, (rap_band - 24) / max(hi - lo, 1) * 0.9)
        current = None
        for note in ed.notes_between(t0, t0 + LANE_SECONDS):
            t = ed.note_time(note)
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


class SyncMap(QWidget):
    """The whole song in one strip: every lyrics line coloured by how well it matches the voice, cuts and playhead."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setFixedHeight(26)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tr("Lyrics lines: green = on the voice, orange/red = out of time, grey = voice not "
                           "analyzed. Orange marks are cuts. Click to jump there."))

    def mousePressEvent(self, event):
        total = self.editor.total_s()
        if total:
            self.editor.seek_s(event.position().x() / self.width() * total)

    def paintEvent(self, _event):
        ed = self.editor
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor('#1b2128'))
        total = ed.total_s()
        if not total:
            p.end()
            return
        x_of = lambda t: t / total * w
        for i in range(len(ed.song.lines)):
            start, end = ed.line_time(i), ed.line_end(i)
            color = QColor('#4b5563')
            if ed.report:
                now, extra, _ = ed.report[i]
                if now is not None:
                    color = QColor(GREEN if abs(extra) < 0.3 and now >= 0.45 else
                                   ('#f59e0b' if abs(extra) < 0.8 else RED))
                    if abs(extra) < 0.3 and now < 0.45:
                        color = QColor('#a3a3a3')
            p.fillRect(QRectF(x_of(start), 6, max(2.0, x_of(end) - x_of(start)), h - 12), color)
        end_audio = x_of(total)
        p.setPen(QPen(QColor(RED), 2))
        p.drawLine(int(end_audio) - 1, 0, int(end_audio) - 1, h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(ORANGE))
        for line in ed.splits:
            x = x_of(ed.line_time(line))
            p.drawPolygon(QPolygonF([QPointF(x - 5, 0), QPointF(x + 5, 0), QPointF(x, 7)]))
        p.setPen(QPen(QColor('#ffffff'), 2))
        x = x_of(ed.position_s())
        p.drawLine(int(x), 0, int(x), h)
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


def tool_button(icon, tip, slot, parent, keys=(), text='', color=BLUE, checkable=False):
    b = QToolButton(parent)
    b.setIcon(make_icon(icon, color, 22))
    b.setIconSize(QSize(22, 22))
    b.setFocusPolicy(Qt.NoFocus)
    b.setAutoRaise(True)
    b.setCheckable(checkable)
    if text:
        b.setText(text)
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    b.setToolTip(tip + (f"  [{', '.join(keys)}]" if keys else ""))
    if checkable:
        b.toggled.connect(slot)
    else:
        b.clicked.connect(lambda _=False: slot())
    for k in keys:
        QShortcut(QKeySequence(k), parent, activated=slot)
    return b


def separator():
    line = QFrame()
    line.setFrameShape(QFrame.VLine)
    line.setStyleSheet("color: #9ca3af;")
    return line


class SyncEditorDialog(QDialog):
    def __init__(self, txt_path, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.txt_path = txt_path
        self.setWindowTitle(tr("Sync editor - {song}").format(song=os.path.basename(os.path.dirname(txt_path))))
        self.resize(1180, 900)
        self.saved = False

        self.us_data = UltrastarToSingit.parse_file(txt_path)
        self.gap_ms = float(self.us_data.get("GAP", "0").replace(',', '.') or 0)
        self.original_gap_ms = self.gap_ms
        try:
            self.video_gap_s = float(self.us_data.get("VIDEOGAP", "0").replace(',', '.') or 0)
        except ValueError:
            self.video_gap_s = 0.0

        self.song_dir = os.path.dirname(txt_path)
        folder = os.path.basename(self.song_dir).rstrip('.')
        name_id = naming.construct_name_id_from_directory_name(folder)
        official = os.path.join(self.song_dir, naming.OFFICIAL_VXLA_NAME)
        # songs rebuilt from DLC use their official vxla as it is: #GAP of the txt is not used there
        self.official = os.path.isfile(official)
        self.song = SyncModel.load_official(official) if self.official else load_txt(self.us_data)
        self.splits = {}          # first line of a cut -> extra seconds for that line and the ones after it
        self.line_extra = [0.0] * len(self.song.lines)
        sung = [n.pitch for n in self.song.notes if n.sung] or [60]
        self.pitch_lo, self.pitch_hi = min(sung) - 2, max(sung) + 2

        # The converted .ogg is what the game plays: VIDEOGAP is already applied to it, so the lyrics
        # (and not the video) are shifted by VIDEOGAP. With the original audio it is the other way round.
        converted_ogg = os.path.join(self.song_dir, name_id + naming.AUDIO_SUFFIX)
        self.audio_is_converted = os.path.isfile(converted_ogg)
        # #START handling of the converter: how much the lyrics were moved, and the audio cut
        self.start_offset_s, self.trim_start_s = 0.0, 0.0
        try:
            with open(os.path.join(self.song_dir, name_id + naming.AUDIO_META_SUFFIX), 'r', encoding='utf-8') as f:
                meta = json.load(f)
            self.start_offset_s = float(meta.get('lyrics_offset') or 0)
            self.trim_start_s = float(meta.get('trim_start') or 0)
        except (OSError, ValueError):
            pass
        self.audio_file = converted_ogg if self.audio_is_converted else None
        if self.audio_file is None:
            for tag in ("AUDIO", "MP3"):
                if self.us_data.get(tag) and os.path.isfile(os.path.join(self.song_dir, self.us_data[tag])):
                    self.audio_file = os.path.join(self.song_dir, self.us_data[tag])
                    break
        video = self.us_data.get("VIDEO")
        self.video_file = os.path.join(self.song_dir, video) \
            if video and os.path.isfile(os.path.join(self.song_dir, video)) else None

        # voice analysis (cached next to the song) and the line report made from it
        self.voice_path = SyncModel.voice_cache_path(self.song_dir)
        self.voice = SyncModel.load_voice(self.voice_path, self.audio_file) if self.audio_file else None
        self.report = []
        self.analysis = None      # running analysis: {'thread', 'error'}

        # playback clock: the player reports its position only every few frames, it is interpolated in between
        self.clock = QElapsedTimer()
        self.clock_base_ms = 0
        self.duration_ms = 0
        self.last_resync = 0
        self.mic = None
        self.sung = []          # (audio time s, folded midi, 1 right / 0 wrong / None between notes)
        self.mic_stats = {}     # note index -> [right, total]

        self.report_timer = QTimer(self)
        self.report_timer.setSingleShot(True)
        self.report_timer.timeout.connect(self.update_report)

        self.build_ui()
        self.load_media()
        self.refresh_labels()
        self.schedule_report()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(30)

    # ------------------------------------------------------------------ interface
    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(5)

        self.info = QLabel()
        self.info.setWordWrap(True)
        layout.addWidget(self.info)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(220)
        layout.addWidget(self.video_widget, stretch=3)

        self.lane = NoteLane(self)
        layout.addWidget(self.lane, stretch=2)

        self.lyrics_display = QLabel()
        self.lyrics_display.setAlignment(Qt.AlignCenter)
        self.lyrics_display.setTextFormat(Qt.RichText)
        self.lyrics_display.setMinimumHeight(105)
        self.lyrics_display.setStyleSheet("background-color: black; padding: 6px;")
        layout.addWidget(self.lyrics_display)

        self.sync_map = SyncMap(self)
        layout.addWidget(self.sync_map)
        self.slider = ClickSlider(Qt.Horizontal)
        self.slider.setFocusPolicy(Qt.NoFocus)
        self.slider.sliderMoved.connect(self.seek_ms)
        layout.addWidget(self.slider)

        # --- playback
        play = QHBoxLayout()
        play.addWidget(tool_button('player-skip-back', tr("Go to the start"), lambda: self.seek_s(0), self, ("Home",)))
        play.addWidget(tool_button('player-track-prev', tr("Previous line"), lambda: self.jump_line(-1), self, ("Up",)))
        play.addWidget(tool_button('rewind-backward-5', tr("Back 5 seconds"), lambda: self.skip(-5), self, ("J",)))
        play.addWidget(tool_button('chevron-left', tr("Back 0.1 seconds"), lambda: self.skip(-0.1), self, (",",)))
        self.btn_play = tool_button('player-play', tr("Play / pause"), self.toggle_play, self, ("Space",),
                                    color=GREEN)
        self.btn_play.setIconSize(QSize(34, 34))
        play.addWidget(self.btn_play)
        play.addWidget(tool_button('chevron-right', tr("Forward 0.1 seconds"), lambda: self.skip(0.1), self, (".",)))
        play.addWidget(tool_button('rewind-forward-5', tr("Forward 5 seconds"), lambda: self.skip(5), self, ("L",)))
        play.addWidget(tool_button('player-track-next', tr("Next line"), lambda: self.jump_line(1), self, ("Down",)))
        play.addWidget(tool_button('text-recognition', tr("Go to just before the first lyrics"),
                                   self.go_first_lyrics, self, ("F",)))
        play.addStretch(1)
        self.lbl_time = QLabel("00:00.00 / 00:00.00")
        self.lbl_time.setStyleSheet("font-family: monospace; font-size: 15px; font-weight: bold;")
        play.addWidget(self.lbl_time)
        play.addStretch(1)
        speed_icon = QLabel()
        speed_icon.setPixmap(make_icon('brand-speedtest', GREY, 20).pixmap(20, 20))
        speed_icon.setToolTip(tr("Speed"))
        play.addWidget(speed_icon)
        self.speed = QComboBox()
        self.speed.setFocusPolicy(Qt.NoFocus)
        self.speed.setToolTip(tr("Speed"))
        for s in SPEEDS:
            self.speed.addItem(f"{s:g}×", s)
        self.speed.setCurrentIndex(SPEEDS.index(1.0))
        self.speed.currentIndexChanged.connect(self.set_speed)
        play.addWidget(self.speed)
        vol_icon = QLabel()
        vol_icon.setPixmap(make_icon('volume', GREY, 20).pixmap(20, 20))
        vol_icon.setToolTip(tr("Volume"))
        play.addWidget(vol_icon)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setFocusPolicy(Qt.NoFocus)
        self.volume.setRange(0, 100)
        self.volume.setValue(100)
        self.volume.setFixedWidth(90)
        self.volume.setToolTip(tr("Volume"))
        self.volume.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100))
        play.addWidget(self.volume)
        layout.addLayout(play)

        # --- sync
        sync = QHBoxLayout()
        self.edit_buttons = []
        for icon, amount, key in (('chevrons-left', -250, "Ctrl+Left"), ('chevron-left', -50, "Left"),
                                  ('chevron-left', -10, "Shift+Left")):
            b = tool_button(icon, tr("Lyrics earlier"), lambda a=amount: self.adjust(a), self, (key,),
                            text=f"{amount}", color=ORANGE)
            sync.addWidget(b)
            self.edit_buttons.append(b)
        self.lbl_gap = QLabel()
        self.lbl_gap.setAlignment(Qt.AlignCenter)
        self.lbl_gap.setMinimumWidth(260)
        self.lbl_gap.setStyleSheet("font-weight: bold; font-size: 15px; padding: 2px 8px;")
        sync.addWidget(self.lbl_gap)
        for icon, amount, key in (('chevron-right', 10, "Shift+Right"), ('chevron-right', 50, "Right"),
                                  ('chevrons-right', 250, "Ctrl+Right")):
            b = tool_button(icon, tr("Lyrics later"), lambda a=amount: self.adjust(a), self, (key,),
                            text=f"+{amount}", color=ORANGE)
            b.setLayoutDirection(Qt.RightToLeft)
            sync.addWidget(b)
            self.edit_buttons.append(b)
        sync.addWidget(separator())
        self.btn_cut = tool_button('scissors', tr("Cut here: from this line on, the arrows move only this part "
                                                  "and what comes after it (the part before stays as it is)"),
                                   self.cut_here, self, ("C",), text=tr("Cut"), color=ORANGE)
        self.btn_uncut = tool_button('arrow-back-up', tr("Remove the cut of this part"), self.remove_cut, self,
                                     text=tr("Join"), color=GREY)
        self.btn_auto = tool_button('wand', tr("Move this part to where the voice is"), self.auto_adjust, self,
                                    ("A",), text=tr("Fit to voice"), color='#7c3aed')
        self.btn_voice = tool_button('wave-sine', tr("Isolate the voice (about 2-3 minutes) to see where the singer "
                                                     "really is and which lines are out of time"),
                                     self.analyze_voice, self, text=tr("Analyze voice"), color=BLUE)
        for b in (self.btn_cut, self.btn_uncut, self.btn_auto):
            sync.addWidget(b)
            self.edit_buttons.append(b)
        sync.addWidget(self.btn_voice)
        sync.addStretch(1)
        self.btn_reset = tool_button('arrow-back-up', tr("Undo changes"), self.undo_all, self, color=GREY)
        sync.addWidget(self.btn_reset)
        self.btn_save = QPushButton(make_icon('device-floppy', '#ffffff', 20), " " + tr("Save"))
        self.btn_save.setFocusPolicy(Qt.NoFocus)
        self.btn_save.setToolTip(tr("Save sync changes") + "  [Ctrl+S]")
        self.btn_save.clicked.connect(self.save)
        self.btn_save.setStyleSheet("QPushButton { background-color: #16a34a; color: white; font-size: 15px; "
                                    "padding: 6px 18px; border-radius: 4px; } "
                                    "QPushButton:disabled { background-color: #555; color: #aaa; }")
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save)
        sync.addWidget(self.btn_save)
        layout.addLayout(sync)

        self.lbl_part = QLabel()
        self.lbl_part.setStyleSheet("color: #6b7280;")
        layout.addWidget(self.lbl_part)

        # --- sing mode
        sing = QHBoxLayout()
        self.btn_sing = tool_button('microphone', tr("Sing mode: listens to the microphone and draws your voice over "
                                                     "the notes, like the game. Use headphones so the microphone "
                                                     "does not hear the song."),
                                    self.toggle_sing, self, text=tr("Sing"), color=RED, checkable=True)
        sing.addWidget(self.btn_sing)
        self.mic_choice = QComboBox()
        self.mic_choice.setFocusPolicy(Qt.NoFocus)
        self.mic_choice.setMaximumWidth(260)
        for dev in QMediaDevices.audioInputs():
            self.mic_choice.addItem(dev.description(), dev)
        default = QMediaDevices.defaultAudioInput().description()
        if self.mic_choice.findText(default) >= 0:
            self.mic_choice.setCurrentIndex(self.mic_choice.findText(default))
        sing.addWidget(self.mic_choice)
        self.mic_delay = QSpinBox()
        self.mic_delay.setFocusPolicy(Qt.ClickFocus)
        self.mic_delay.setRange(0, 500)
        self.mic_delay.setSingleStep(10)
        self.mic_delay.setValue(100)
        self.mic_delay.setSuffix(" ms")
        self.mic_delay.setToolTip(tr("Mic delay") + ": " +
                                  tr("How late the microphone hears you; raise it if your voice is drawn after the notes."))
        sing.addWidget(self.mic_delay)
        self.lbl_score = QLabel()
        self.lbl_score.setStyleSheet("font-weight: bold;")
        sing.addWidget(self.lbl_score, stretch=1)
        layout.addLayout(sing)

        if self.official:
            for w in self.edit_buttons + [self.btn_reset, self.btn_save]:
                w.setEnabled(False)

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
        if self.song.syllables and self.duration_ms:
            end = self.line_end(len(self.song.lines) - 1)
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
            self.info.setStyleSheet("padding: 4px 6px; border-radius: 4px; background: #1f2a33; color: #c8d2dc;")
            text = "<small>" + escape(text) + "</small>"
        self.info.setText(text)

    # ------------------------------------------------------------------ timing of the lyrics
    def shift_s(self):
        """Seconds added to every note time to place it on the audio being played (#GAP and #START)."""
        if self.official:
            return 0.0
        if self.audio_is_converted:
            return self.gap_ms / 1000.0 + self.video_gap_s - self.start_offset_s
        # original audio: only moved when it is a shorter version that already starts at #START
        return self.gap_ms / 1000.0 - (self.start_offset_s - self.trim_start_s)

    def line_shift(self, line):
        return self.shift_s() + self.line_extra[line]

    def note_time(self, note):
        return note.t + self.line_shift(note.line)

    def line_time(self, line):
        return self.song.line_starts[line] + self.line_shift(line)

    def line_end(self, line):
        return self.song.line_ends[line] + self.line_shift(line)

    def notes_between(self, t0, t1):
        margin = max((abs(e) for e in self.line_extra), default=0.0) + 10
        start = bisect.bisect_left(self.song.note_starts, t0 - self.shift_s() - margin)
        for note in self.song.notes[start:]:
            t = self.note_time(note)
            if t > t1 + margin:
                break
            if t <= t1 and t + note.d >= t0:
                yield note

    def note_near(self, t):
        best, best_dist = None, 1e9
        for note in self.notes_between(t - 2, t + 2):
            nt = self.note_time(note)
            dist = 0 if nt <= t <= nt + note.d else min(abs(t - nt), abs(t - nt - note.d))
            if dist < best_dist:
                best, best_dist = note, dist
        return best

    def current_line(self):
        now = self.position_s()
        line = 0
        for i in range(len(self.song.lines)):
            if self.line_time(i) <= now + 0.05:
                line = i
        return line

    def part_start(self, line=None):
        """First line of the part being edited: 0 (all the lyrics, #GAP) or the last cut before the line."""
        line = self.current_line() if line is None else line
        cuts = [c for c in self.splits if c <= line]
        return max(cuts) if cuts else 0

    def recompute_extra(self):
        total, cuts = 0.0, sorted(self.splits.items())
        self.line_extra = []
        for i in range(len(self.song.lines)):
            total = sum(d for c, d in cuts if c <= i)
            self.line_extra.append(total)

    # ------------------------------------------------------------------ editing
    def changed(self):
        return self.gap_ms != self.original_gap_ms or any(abs(d) > 1e-9 for d in self.splits.values())

    def beat_s(self):
        return 60.0 / self.song.bpm / 4 if self.song.bpm else 0.0

    def adjust(self, amount_ms):
        if self.official:
            return
        part = self.part_start()
        if part == 0:
            self.gap_ms += amount_ms
        else:
            self.splits[part] += amount_ms / 1000.0
            self.recompute_extra()
        self.refresh_labels()
        self.schedule_report()

    def cut_here(self):
        if self.official:
            return
        line = self.current_line()
        if line == 0:
            self.lbl_part.setText(tr("The first line already moves with the whole lyrics (#GAP)."))
            return
        if line not in self.splits:
            self.splits[line] = 0.0
            self.recompute_extra()
        self.refresh_labels()

    def remove_cut(self):
        part = self.part_start()
        if part in self.splits:
            del self.splits[part]
            self.recompute_extra()
            self.refresh_labels()
            self.schedule_report()

    def undo_all(self):
        self.gap_ms = self.original_gap_ms
        self.splits.clear()
        self.recompute_extra()
        self.refresh_labels()
        self.schedule_report()

    def auto_adjust(self):
        """Moves the part of the current line by the shift the voice analysis found for that line."""
        if self.official:
            return
        if not self.report:
            self.lbl_part.setText(tr("First press \"Analyze voice\"."))
            return
        line = self.current_line()
        now, extra, _ = self.report[line]
        if now is None or abs(extra) < 0.05:
            self.lbl_part.setText(tr("This line already matches the voice."))
            return
        if line != self.part_start(line) and line != 0:
            self.splits[line] = 0.0  # a new part starts at this line, the lines before stay
            self.recompute_extra()
        self.adjust(extra * 1000)

    def overlapping_line(self):
        """First line that starts before the previous one ends (it cannot be saved like that), or None."""
        for i in range(1, len(self.song.lines)):
            if self.line_extra[i] != self.line_extra[i - 1] and self.line_time(i) < self.line_end(i - 1) - 1e-6:
                return i
        return None

    def refresh_labels(self):
        part = self.part_start()
        if part == 0:
            self.lbl_gap.setText(tr("All the lyrics: GAP {gap} ms").format(gap=int(round(self.gap_ms))) +
                                 (f"  ({self.gap_ms - self.original_gap_ms:+.0f})"
                                  if self.gap_ms != self.original_gap_ms else ""))
        else:
            self.lbl_gap.setText(tr("From line {n} ({time}): {ms:+.0f} ms").format(
                n=part + 1, time=fmt_time(self.line_time(part)), ms=self.splits[part] * 1000))
        parts = len(self.splits) + 1
        hint = tr("{n} parts. ").format(n=parts) if self.splits else ""
        if self.splits and self.beat_s():
            hint += tr("Moving a part is saved in steps of {ms:.0f} ms (one beat of this song). ").format(
                ms=self.beat_s() * 1000)
        if self.report:
            line = self.current_line()
            now, extra, _ = self.report[line]
            if now is not None and abs(extra) >= 0.3:
                hint += tr("The voice of this line is {ms:+.0f} ms away: press the wand to fit it.").format(
                    ms=extra * 1000)
        overlap = self.overlapping_line()
        if overlap is not None:
            hint = tr("Line {n} now starts before line {m} ends: move it later or remove that cut before saving.").format(
                n=overlap + 1, m=overlap) + " " + hint
        self.lbl_part.setStyleSheet("color: #dc2626; font-weight: bold;" if overlap is not None else "color: #6b7280;")
        self.lbl_part.setText(hint)
        self.btn_save.setEnabled(overlap is None and not self.official)
        self.btn_uncut.setEnabled(part != 0 and not self.official)
        self.update_info()

    # ------------------------------------------------------------------ voice analysis
    def analyze_voice(self):
        if self.analysis is not None or not self.audio_file:
            return
        state = {'error': None}

        def work():
            try:
                SyncModel.analyze_voice(self.audio_file, self.voice_path)
            except Exception as e:  # demucs missing, out of memory...
                state['error'] = str(e)

        state['thread'] = threading.Thread(target=work, daemon=True)
        self.analysis = state
        self.btn_voice.setEnabled(False)
        self.btn_voice.setText(tr("Analyzing... (2-3 min)"))
        state['thread'].start()

    def check_analysis(self):
        if self.analysis is None or self.analysis['thread'].is_alive():
            return
        error, self.analysis = self.analysis['error'], None
        self.btn_voice.setEnabled(True)
        self.btn_voice.setText(tr("Analyze voice"))
        if error:
            QMessageBox.warning(self, tr("Error"), tr("Could not analyze the voice: {error}").format(error=error))
            return
        self.voice = SyncModel.load_voice(self.voice_path, self.audio_file)
        self.schedule_report()

    def schedule_report(self):
        if self.voice is not None:
            self.report_timer.start(300)

    def update_report(self):
        if self.voice is None:
            return
        self.report = SyncModel.line_report(self.song, self.voice, self.line_shift)
        self.refresh_labels()

    # ------------------------------------------------------------------ playback
    def playing(self):
        return self.audio_player.playbackState() == QMediaPlayer.PlayingState

    def total_s(self):
        return self.duration_ms / 1000.0

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
        self.btn_play.setIcon(make_icon('player-pause' if self.playing() else 'player-play',
                                        ORANGE if self.playing() else GREEN, 34))

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

    def jump_line(self, step):
        if not self.song.lines:
            return
        now = self.position_s() + 0.05
        current = self.current_line()
        target = min(max(current + step, 0), len(self.song.lines) - 1)
        if step < 0 and now - self.line_time(current) > 1.0:
            target = current  # like a player: first back to the start of this line
        self.seek_s(max(0.0, self.line_time(target) - 0.5))

    def go_first_lyrics(self):
        if self.song.lines:
            self.seek_s(max(0.0, self.line_time(0) - 2.0))

    def tick(self):
        now = self.position_s()
        self.lbl_time.setText(f"{fmt_time(now)} / {fmt_time(self.total_s())}")
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
        if self.analysis is not None:
            self.check_analysis()
        line = self.current_line()
        if line != getattr(self, '_shown_line', None):  # the hints depend on the line being played
            self._shown_line = line
            self.refresh_labels()
        self.update_lyrics(now)
        self.lane.update()
        self.sync_map.update()

    def update_lyrics(self, now):
        lines, syl = self.song.lines, self.song.syllables
        shown = [i for i, line in enumerate(lines) if line]
        if not shown:
            self.lyrics_display.setText("")
            return
        active = shown[-1]
        for i in shown:
            t, d, _, _ = syl[lines[i][-1]]
            if now <= t + d + self.line_shift(i) + 0.5:
                active = i
                break
        pos = shown.index(active)

        def plain(k, size):
            if not 0 <= k < len(shown):
                return f"<span style='font-size:{size}px;'>&nbsp;</span>"
            text = ''.join(escape(syl[j][2]) for j in lines[shown[k]])
            return f"<span style='color:#8a8a8a; font-size:{size}px;'>{text}</span>"

        shift = self.line_shift(active)
        current = []
        for j in lines[active]:
            t, d, text, _ = syl[j]
            color = '#3ddc84' if now >= t + d + shift else ('#ffe14d' if now >= t + shift else '#ffffff')
            current.append(f"<span style='color:{color};'>{escape(text)}</span>")
        html = (plain(pos - 1, 18) + "<br><span style='font-size:28px; font-weight:bold;'>" + ''.join(current)
                + "</span><br>" + plain(pos + 1, 18))
        self.lyrics_display.setText(f"<div align='center'>{html}</div>")

    # ------------------------------------------------------------------ sing mode
    def toggle_sing(self, on):
        if on:
            device = self.mic_choice.currentData()
            try:
                self.mic = Microphone(device or QMediaDevices.defaultAudioInput())
            except Exception as e:
                self.mic = None
                self.btn_sing.setChecked(False)
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
        note = None
        for candidate in self.notes_between(t, t):
            nt = self.note_time(candidate)
            if nt <= t < nt + candidate.d:
                note = candidate
        state, shown = None, midi
        if note is not None and note.sung:
            shown = fold_to(midi, note.pitch)
            state = 1 if abs(shown - note.pitch) <= HIT_SEMITONES else 0
            stats = self.mic_stats.setdefault(id(note), [0, 0])
            stats[0] += state
            stats[1] += 1
        else:  # between notes: drawn near the closest note
            near = self.note_near(t)
            shown = fold_to(midi, near.pitch if near is not None and near.sung else (self.pitch_lo + self.pitch_hi) / 2)
        if self.sung and t < self.sung[-1][0]:  # after a seek back
            self.sung = [s for s in self.sung if s[0] < t]
        self.sung.append((t, shown, state))
        right = sum(1 for r, n in self.mic_stats.values() if n and r / n >= 0.5)
        frames = sum(n for _, n in self.mic_stats.values())
        hits = sum(r for r, _ in self.mic_stats.values())
        detail = tr("You sing {sung}").format(sung=note_name(midi))
        if state is not None:
            detail += tr(" · note {note} ({cents:+.0f} cents)").format(
                note=note_name(note.pitch), cents=(shown - note.pitch) * 100)
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
        if self.changed():
            reply = QMessageBox.question(self, tr('Unsaved changes'),
                                         tr('Save the sync changes before closing?'),
                                         QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                if self.save():
                    event.accept()
                else:
                    event.ignore()
            elif reply == QMessageBox.No:
                self.stop_players()
                event.accept()
            else:
                event.ignore()
        else:
            self.stop_players()
            event.accept()

    def line_beats(self):
        """Extra beats of every line (cuts are saved by moving the notes; a beat is the smallest step)."""
        if not self.splits:
            return None
        return [int(round(extra / self.beat_s())) for extra in self.line_extra]

    def save(self):
        """Writes #GAP (and the notes moved by cuts) keeping the file's encoding and line endings."""
        if self.official:
            return False
        try:
            with open(self.txt_path, 'rb') as f:
                raw = f.read()
            encoding = UltrastarToSingit._detect_encoding_bytes(raw)
            if encoding == 'utf-8-sig' and not raw.startswith(b'\xef\xbb\xbf'):
                encoding = 'utf-8'
            text = raw.decode(encoding)
            newline = '\r\n' if '\r\n' in text else '\n'
            lines = SyncModel.rewrite_txt(text.splitlines(), self.gap_ms, self.line_beats(),
                                          expected_notes=len(self.song.notes))
            if not os.path.exists(self.txt_path + '.bak'):
                # the first time a song is re-synced its original txt is kept, it can always be restored
                with open(self.txt_path + '.bak', 'wb') as f:
                    f.write(raw)
            tmp_path = self.txt_path + '.tmp'
            with open(tmp_path, 'w', encoding=encoding, newline='') as f:
                f.write(newline.join(lines) + (newline if text.endswith(('\n', '\r')) else ''))
            os.replace(tmp_path, self.txt_path)

            self.original_gap_ms = self.gap_ms  # Prevent unsaved changes prompt on app exit
            self.splits.clear()
            self.saved = True
            self.accept()
            return True
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), tr("Could not save the sync changes: {error}").format(error=e))
            return False

    # kept for callers of the previous editor
    save_gap = save


if __name__ == '__main__':
    app = QApplication(sys.argv)
    if len(sys.argv) > 1:
        dialog = SyncEditorDialog(sys.argv[1])
        dialog.exec()
