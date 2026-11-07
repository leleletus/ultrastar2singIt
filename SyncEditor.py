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
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QUrl, QTimer, QElapsedTimer, QRectF, QPointF, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QKeySequence, QShortcut, QPolygonF
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider,
                               QWidget, QMessageBox, QComboBox, QSpinBox, QStyle, QFrame, QSizePolicy, QToolButton,
                               QInputDialog)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudioSource, QAudioFormat, QMediaDevices
from PySide6.QtMultimediaWidgets import QVideoWidget

import ConvertFiles
import SupportedFormats
import SyncModel
import UltrastarToSingit
import naming
from GuiElement import make_icon
from SyncModel import detect_pitch, hz_to_midi, fold_to, note_name, load_txt, HIT_SEMITONES  # noqa: F401
from i18n import tr

def looks_still(video, duration):
    """Three tiny frames (20/50/80 % of the song) that are all alike: a still image. Takes well under a second."""
    import subprocess
    frames = []
    for at in (0.2, 0.5, 0.8):
        try:
            out = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{duration * at:.1f}', '-i', video, '-frames:v', '1',
                                  '-vf', 'scale=32:18,format=gray', '-f', 'rawvideo', '-'],
                                 capture_output=True, timeout=5).stdout
        except (OSError, subprocess.TimeoutExpired):
            return False
        if len(out) != 32 * 18:
            return False
        frames.append(np.frombuffer(out, dtype=np.uint8).astype(np.int16))
    return max(float(np.abs(a - b).mean()) for a, b in zip(frames, frames[1:])) < 2.0


LANE_SECONDS = 6.0        # seconds of notes visible in the lane
EDGE_PX = 7                # a note's edge this wide is dragged to make it longer/shorter
DRAG_START_PX = 6          # moving a note: the first move this far decides sideways (time) or up/down (pitch)
PLAYHEAD = 0.3            # playhead position in the lane (fraction of its width)
SPEEDS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
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
        self.setMouseTracking(True)  # the cursor shows what dragging a note would do (move / make longer)
        self._drag = None

    def geometry_now(self):
        """(start time, x of a time, y of a pitch, pitch of a y, bar height, rap band y) of the lane as drawn now."""
        ed = self.editor
        w, h = self.width(), self.height()
        t0 = ed.position_s() - PLAYHEAD * LANE_SECONDS
        lo, hi = ed.pitch_lo, ed.pitch_hi
        rap_band = h - 14
        span = max(hi - lo, 1)
        x_of = lambda t: (t - t0) / LANE_SECONDS * w
        y_of = lambda m: 8 + (hi - m) / span * (rap_band - 24)
        pitch_of = lambda y: hi - (y - 8) / (rap_band - 24) * span
        bar = max(6.0, (rap_band - 24) / span * 0.9)
        return t0, x_of, y_of, pitch_of, bar, rap_band

    def note_at(self, pos):
        ed = self.editor
        t0, x_of, y_of, _, bar, _ = self.geometry_now()
        _, _, _, _, _, rap_band = self.geometry_now()
        for note in ed.notes_between(t0, t0 + LANE_SECONDS):
            t = ed.note_time(note)
            width = max(3.0, note.d / LANE_SECONDS * self.width())
            rect = QRectF(x_of(t), y_of(note.pitch) - bar / 2 - 3, width, bar + 6) if note.sung \
                else QRectF(x_of(t), rap_band - 10, width, 14)  # rap notes: the grey band at the bottom
            if rect.contains(QPointF(pos)):
                return note
        return None

    def zone_at(self, note, pos):
        """What dragging a note from pos does: 'end' (its right edge: longer/shorter), 'start' (its left edge) or
        'body' (move it: sideways in time, up/down in pitch)."""
        _, x_of, _, _, _, _ = self.geometry_now()
        x1 = x_of(self.editor.note_time(note))
        width = max(3.0, note.d / LANE_SECONDS * self.width())
        x = pos.x()
        edge = min(EDGE_PX, width / 3)
        if x >= x1 + width - edge:
            return 'end'
        if x <= x1 + edge and width >= 3 * EDGE_PX:
            return 'start'
        return 'body'

    def wheelEvent(self, event):
        """The mouse wheel (or a touchpad) moves through the song: half a second a step, 2 s with Ctrl."""
        wheel_seek(self.editor, event)

    def mousePressEvent(self, event):
        """Click a note to select it (an empty place: drag it to move through the song). Drag its middle up/down to change its pitch or sideways to move it in time,
        drag its right edge to make it longer or shorter (its left edge moves its start)."""
        ed = self.editor
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        if ed.official:  # read-only: the lane only scrolls
            self._drag = {'zone': 'pan', 'x': event.position().x(), 'time': ed.position_s()}
            return
        pos, mods = event.position(), event.modifiers()
        note = self.note_at(pos)
        self._drag = None
        if note is None:
            if mods & Qt.ShiftModifier:  # Shift + drag the empty lane: select the notes in a time range
                t0, _, _, _, _, _ = self.geometry_now()
                at = t0 + pos.x() / max(1, self.width()) * LANE_SECONDS
                self._drag = {'zone': 'box', 'x': pos.x(), 'from': at, 'to': at,
                              'keep': set(ed.selected_indices()) if mods & Qt.ControlModifier else set()}
            else:  # dragging the empty lane scrolls through the song
                ed.clear_selection()
                self._drag = {'zone': 'pan', 'x': pos.x(), 'time': ed.position_s()}
                self.setCursor(Qt.ClosedHandCursor)
        elif mods & Qt.ControlModifier:  # Ctrl + click: add the note to the selection, or take it out
            ed.toggle_selected(note)
        elif mods & Qt.ShiftModifier:    # Shift + click: every note from the selected one to this one
            ed.select_range(note)
        else:
            if not ed.is_selected(note) or len(ed.selected_indices()) < 2:
                ed.clear_selection()
            ed.selected_note = note
            zone = self.zone_at(note, pos)
            group = ed.selection() if zone == 'body' and len(ed.selected_indices()) > 1 else [note]
            self._drag = {'zone': zone, 'x': pos.x(), 'y': pos.y(), 'pitch': note.pitch,
                          't': note.t, 'd': note.d, 'axis': None, 'moved': False,
                          'group': [(n, n.t, n.d, n.pitch) for n in group],
                          'range': ed.group_range(group) if len(group) > 1 else None}
        self.update()
        ed.refresh_labels()

    def mouseDoubleClickEvent(self, event):
        """Double click a note to fix its text."""
        ed = self.editor
        note = self.note_at(event.position()) if not ed.official and event.button() == Qt.LeftButton else None
        if note is None:
            return super().mouseDoubleClickEvent(event)
        self._drag = None
        ed.selected_note = note
        ed.edit_note_text(note)

    def mouseMoveEvent(self, event):
        ed = self.editor
        pos = event.position()
        if self._drag is not None and self._drag['zone'] == 'pan':
            dx = pos.x() - self._drag['x']
            ed.seek_s(max(0.0, self._drag['time'] - dx / max(1, self.width()) * LANE_SECONDS))
            return
        if self._drag is not None and self._drag['zone'] == 'box':
            t0, _, _, _, _, _ = self.geometry_now()
            self._drag['to'] = t0 + pos.x() / max(1, self.width()) * LANE_SECONDS
            ed.select_time_range(self._drag['from'], self._drag['to'], self._drag['keep'])
            self.update()
            return
        if self._drag is None or ed.selected_note is None:
            if not ed.official and not event.buttons():  # hover: the cursor tells what a drag would do
                note = self.note_at(pos)
                zone = self.zone_at(note, pos) if note is not None else None
                self.setCursor(Qt.SizeHorCursor if zone in ('start', 'end') else
                               Qt.OpenHandCursor if zone == 'body' else Qt.ArrowCursor)
            return super().mouseMoveEvent(event)
        drag, note = self._drag, ed.selected_note
        dx, dy = pos.x() - drag['x'], pos.y() - drag['y']
        seconds = dx / max(1, self.width()) * LANE_SECONDS
        if max(abs(dx), abs(dy)) > DRAG_START_PX:
            drag['moved'] = True
        if drag['zone'] == 'end':
            ed.set_note_time(note, drag['t'], drag['t'] + drag['d'] + seconds)
        elif drag['zone'] == 'start':
            ed.set_note_time(note, drag['t'] + seconds, drag['t'] + drag['d'])
        else:
            if drag['axis'] is None and max(abs(dx), abs(dy)) > DRAG_START_PX:  # the first move decides
                drag['axis'] = 'x' if abs(dx) > abs(dy) or not note.sung else 'y'
            if drag['axis'] == 'x' and drag['range'] is not None:  # several notes selected: they move together
                ed.shift_group(drag['group'], seconds, drag['range'])
            elif drag['axis'] == 'x':
                ed.set_note_time(note, drag['t'] + seconds, drag['t'] + drag['d'] + seconds, keep_length=True)
            elif drag['axis'] == 'y':
                _, _, _, pitch_of, _, _ = self.geometry_now()
                steps = int(round(pitch_of(pos.y()) - pitch_of(drag['y'])))
                ed.set_group_pitch(drag['group'], steps)

    def mouseReleaseEvent(self, event):
        drag = self._drag
        if drag is not None and drag['zone'] == 'pan':
            self.setCursor(Qt.ArrowCursor)
        if drag is not None and drag.get('group') and len(drag['group']) > 1 and not drag['moved']:
            self.editor.clear_selection()  # a plain click on one of the selected notes: only that one is left
        self._drag = None
        self.update()
        self.editor.refresh_labels()
        self.editor.record_state()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event):
        ed = self.editor
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor('#101418'))
        now = ed.position_s()
        t0, x_of, y_of, _, bar, rap_band = self.geometry_now()
        lo, hi = ed.pitch_lo, ed.pitch_hi

        for m in range(int(lo), int(hi) + 1):  # one guide per semitone, stronger on C
            p.setPen(QPen(QColor('#2a3440' if m % 12 == 0 else '#182028'), 1))
            p.drawLine(0, int(y_of(m)), w, int(y_of(m)))
            if m % 12 == 0:
                p.setPen(QColor('#5a6a7a'))
                p.drawText(4, int(y_of(m)) - 2, note_name(m))

        # the selected part (the one the arrows move) is tinted; cuts are orange lines
        if ed.selected:
            x1 = max(0.0, x_of(ed.line_time(ed.selected)))
            x2 = min(float(w), x_of(ed.line_end(ed.part_end(ed.selected))))
            if x2 > x1:
                p.fillRect(QRectF(x1, 0, x2 - x1, h), QColor(217, 119, 6, 40))
        for line in ed.splits:
            x = x_of(ed.line_time(line))
            if 0 <= x <= w:
                p.setPen(QPen(QColor(ORANGE), 2 if line == ed.selected else 1,
                              Qt.SolidLine if line == ed.selected else Qt.DashLine))
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

        current = None
        syllable_font = QFont(self.font().family(), 8)
        chosen = set(ed.selected_indices())
        if self._drag is not None and self._drag['zone'] == 'box':  # the range being selected
            xa, xb = sorted((x_of(self._drag['from']), x_of(self._drag['to'])))
            p.fillRect(QRectF(xa, 0, xb - xa, h), QColor(255, 255, 255, 28))
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
            picked = ed.note_index.get(id(note)) in chosen
            p.setPen(QPen(QColor('#ffffff'), 3 if note is ed.selected_note else 2) if picked else Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(rect, 3, 3)
            text = ed.note_text(note)
            if text:  # the syllable under its note (above it for rap notes, at the bottom)
                p.setPen(QColor('#ffffff' if picked else '#aab4be'))
                p.setFont(syllable_font)
                y = rect.bottom() + 12 if note.sung else rect.top() - 3
                p.drawText(QPointF(rect.left() + 1, y), text)

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


def wheel_seek(editor, event):
    """Moves through the song with the mouse wheel: down/right = forward, half a second a step (2 s with Ctrl)."""
    delta = event.angleDelta()
    steps = (delta.y() or -delta.x()) / 120.0
    if steps:
        step = 2.0 if event.modifiers() & Qt.ControlModifier else 0.5
        editor.seek_s(max(0.0, editor.position_s() - steps * step))
    event.accept()


class SyncMap(QWidget):
    """The whole song in one strip: every lyrics line coloured by how well it matches the voice, cuts and playhead."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setFixedHeight(26)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tr("Lyrics lines: green = on the voice, orange/red = out of time, grey = voice not "
                           "analyzed. Orange marks are cuts. Click to jump there."))

    def wheelEvent(self, event):
        wheel_seek(self.editor, event)

    def mousePressEvent(self, event):
        total = self.editor.total_s()
        if total:
            seconds = event.position().x() / self.width() * total
            self.editor.seek_s(seconds)
            if self.editor.splits:
                self.editor.select_part_at(seconds)

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
        if ed.selected or ed.splits:  # the part the arrows move
            first = ed.selected
            last = ed.part_end(first) if first else len(ed.song.lines) - 1
            x1, x2 = x_of(ed.line_time(first)), x_of(ed.line_end(last))
            p.setPen(QPen(QColor('#ffffff'), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(x1, 2, max(4.0, x2 - x1), h - 4))
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
        if self.official:
            self.song = SyncModel.load_official(official)
            self.all_notes, self.raw_texts, self.line_count = self.song.notes, [], len(self.song.lines)
        else:
            # every note of the file (in its order, the one saving uses); self.song leaves out the deleted ones
            self.all_notes, self.raw_texts, self.line_count, bpm = SyncModel.txt_notes(self.us_data)
            self.song = SyncModel.song_from_notes(self.all_notes, self.raw_texts, self.line_count, bpm)
        self.note_index = {id(n): i for i, n in enumerate(self.all_notes)}
        # notes added in the editor (a note split in two) go at the end of all_notes; order is the time order
        self.file_notes = len(self.all_notes)
        self.order = list(range(self.file_notes))
        self.text_edits = {}      # note index -> new text (fixed lyrics)
        self.deleted = set()      # note indices taken out (lyrics that are not sung there)
        self.original_pitches = [n.pitch for n in self.all_notes]
        self.original_times = [(n.t, n.d) for n in self.all_notes]
        self.selected_note = None  # note whose pitch is being edited (click it in the lane)
        self.chosen = set()        # more notes selected with it (Ctrl/Shift + click): they move together
        self.splits = {}          # first line of a part -> extra seconds of that part (up to the next cut)
        self.selected = 0         # part moved by the arrows: 0 = all the lyrics (#GAP)
        self.line_extra = [0.0] * len(self.song.lines)
        sung = [n.pitch for n in self.song.notes if n.sung] or [60]
        self.pitch_lo, self.pitch_hi = min(sung) - 2, max(sung) + 2

        # The converted .ogg is what the game plays: VIDEOGAP is already applied to it, so the lyrics
        # (and not the video) are shifted by VIDEOGAP. With the original audio it is the other way round.
        converted_ogg = os.path.join(self.song_dir, name_id + naming.AUDIO_SUFFIX)
        self.audio_is_converted = os.path.isfile(converted_ogg)
        # #START handling of the converter: how much the lyrics were moved, and the audio cut
        self.start_offset_s, self.trim_start_s, self.video_gap_s = 0.0, 0.0, 0.0
        try:
            with open(os.path.join(self.song_dir, name_id + naming.AUDIO_META_SUFFIX), 'r', encoding='utf-8') as f:
                meta = json.load(f)
            self.start_offset_s = float(meta.get('lyrics_offset') or 0)
            self.trim_start_s = float(meta.get('trim_start') or 0)
            self.video_gap_s = float(meta.get('video_gap') or 0)
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
        if self.video_file is None:  # like the converter: the biggest video of the folder (a .bk2 can't be played)
            videos = [os.path.join(self.song_dir, f) for f in os.listdir(self.song_dir)
                      if f.lower().endswith(SupportedFormats.VIDEO_EXTENSIONS) and not f.lower().endswith('.bk2')
                      and not naming.is_generated_file(f, naming.all_name_ids(os.path.basename(self.song_dir)))]
            self.video_file = max(videos, key=os.path.getsize) if videos else None
        self.game_video_note = self.still_video_note()

        # voice analysis (cached next to the song) and the line report made from it
        self.voice_path = SyncModel.voice_cache_path(self.song_dir)
        self.voice = SyncModel.load_voice(self.voice_path, self.audio_file) if self.audio_file else None
        if self.voice is None and self.audio_is_converted:
            self.voice = self.voice_of_source()
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

        # undo history: every state of the edits (one per action; a drag is one step when the mouse is let go)
        self.history, self.future = [], []
        self.history_timer = QTimer(self)
        self.history_timer.setSingleShot(True)
        self.history_timer.timeout.connect(self.record_state)

        self.build_ui()
        self.load_media()
        self.refresh_labels()
        self.schedule_report()
        self.record_state()

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
        if not self.official:
            self.lane.setToolTip(tr("Click a note to select it. Drag it up/down to change its pitch (Shift+Up/Down), "
                                    "sideways to move it in time (Alt+Left/Right), its right edge to make it longer "
                                    "or shorter (Ctrl+Shift+Left/Right). Double click: fix its syllable. Drag an "
                                    "empty place or use the mouse wheel to move through the song. Save to keep it."))
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
        self.lbl_gap = QLabel()  # shown in the row under the buttons, it can be long
        self.lbl_gap.setStyleSheet("font-weight: bold; font-size: 15px; color: #d97706;")
        for icon, amount, key in (('chevron-right', 10, "Shift+Right"), ('chevron-right', 50, "Right"),
                                  ('chevrons-right', 250, "Ctrl+Right")):
            b = tool_button(icon, tr("Lyrics later"), lambda a=amount: self.adjust(a), self, (key,),
                            text=f"+{amount}", color=ORANGE)
            b.setLayoutDirection(Qt.RightToLeft)
            sync.addWidget(b)
            self.edit_buttons.append(b)
        sync.addWidget(separator())
        self.btn_cut = tool_button('scissors', tr("Cut start: a part starts at the line being played and gets "
                                                  "selected; the arrows move only that part"),
                                   self.cut_start, self, ("C",), text=tr("Start"), color=ORANGE)
        self.btn_cut_end = tool_button('separator-vertical', tr("Cut end: the selected part ends just before the "
                                                                "line being played, what comes after does not move"),
                                       self.cut_end, self, ("V",), text=tr("End"), color=ORANGE)
        self.btn_uncut = tool_button('arrow-merge-left', tr("Join the selected part to the one before it"),
                                     self.remove_cut, self, text=tr("Join"), color=GREY)
        self.btn_all = tool_button('arrows-horizontal', tr("Select all the lyrics (#GAP): moves every part"),
                                   lambda: self.select_part(0), self, ("G",), text=tr("All the lyrics"), color=BLUE)
        self.btn_all.setCheckable(True)
        QShortcut(QKeySequence("["), self, activated=lambda: self.step_part(-1))
        QShortcut(QKeySequence("]"), self, activated=lambda: self.step_part(1))
        self.btn_auto = tool_button('wand', tr("Move the line being played (and its part) to where the voice is"),
                                    self.auto_adjust, self, ("A",), text=tr("Fit to voice"), color='#7c3aed')
        self.btn_voice = tool_button('wave-sine', tr("Isolate the voice (about 2-3 minutes) to see where the singer "
                                                     "really is and which lines are out of time"),
                                     self.analyze_voice, self, text=tr("Analyze voice"), color=BLUE)
        for b in (self.btn_cut, self.btn_cut_end, self.btn_uncut, self.btn_all, self.btn_auto):
            sync.addWidget(b)
            self.edit_buttons.append(b)
        sync.addWidget(self.btn_voice)
        sync.addStretch(1)
        self.btn_undo = tool_button('arrow-back-up', tr("Undo the last change"), self.undo, self, ("Ctrl+Z",),
                                    text=tr("Undo"), color=GREY)
        self.btn_redo = tool_button('arrow-forward-up', tr("Redo the change undone"), self.redo, self,
                                    ("Ctrl+Y", "Ctrl+Shift+Z"), color=GREY)
        self.btn_reset = tool_button('arrow-back-up-double', tr("Undo all the changes (Ctrl+Z brings them back)"),
                                     self.ask_undo_all, self, color=GREY)
        for b in (self.btn_undo, self.btn_redo, self.btn_reset):
            sync.addWidget(b)
        self.btn_save = QPushButton(make_icon('device-floppy', '#ffffff', 20), " " + tr("Save"))
        self.btn_save.setFocusPolicy(Qt.NoFocus)
        self.btn_save.setToolTip(tr("Save sync changes") + "  [Ctrl+S]")
        self.btn_save.clicked.connect(self.save)
        self.btn_save.setStyleSheet("QPushButton { background-color: #16a34a; color: white; font-size: 15px; "
                                    "padding: 6px 18px; border-radius: 4px; } "
                                    "QPushButton:disabled { background-color: #555; color: #aaa; }")
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save)
        QShortcut(QKeySequence("Shift+Up"), self, activated=lambda: self.move_selected_note(1))
        QShortcut(QKeySequence("Shift+Down"), self, activated=lambda: self.move_selected_note(-1))
        QShortcut(QKeySequence("Alt+Left"), self, activated=lambda: self.nudge_selected(beats=-1))
        QShortcut(QKeySequence("Alt+Right"), self, activated=lambda: self.nudge_selected(beats=1))
        QShortcut(QKeySequence("Ctrl+Shift+Left"), self, activated=lambda: self.nudge_selected(longer=-1))
        QShortcut(QKeySequence("Ctrl+Shift+Right"), self, activated=lambda: self.nudge_selected(longer=1))
        QShortcut(QKeySequence("Ctrl+A"), self, activated=self.select_line)
        sync.addWidget(self.btn_save)
        layout.addLayout(sync)

        # --- lyrics: take out what is not sung, fix misspelt words
        words = QHBoxLayout()
        self.btn_del_syllable = tool_button('trash', tr("Delete the selected syllable with its notes (click a note "
                                                        "first)"), self.delete_selected, self, ("Delete",),
                                            text=tr("Delete syllable"), color=RED)
        self.btn_del_line = tool_button('row-remove', tr("Delete the line being played (or the selected note's line) "
                                                         "with all its notes"), self.delete_line, self,
                                        ("Ctrl+Delete",), text=tr("Delete line"), color=RED)
        self.btn_text = tool_button('cursor-text', tr("Fix the lyrics of the line being played (or the selected "
                                                      "note's line). Double click a note to fix only its syllable."),
                                    self.edit_line_text, self, ("T",), text=tr("Fix text"), color=BLUE)
        self.btn_split = tool_button('arrows-split', tr("Split the selected note in two, to add a syllable that is "
                                                        "missing (then write it). Fix text (T) also splits notes "
                                                        "when you write more pieces than notes."),
                                     self.split_selected, self, ("S",), text=tr("Split note"), color=BLUE)
        for b in (self.btn_del_syllable, self.btn_del_line, self.btn_text, self.btn_split):
            words.addWidget(b)
            self.edit_buttons.append(b)
        self.lbl_edits = QLabel()
        self.lbl_edits.setStyleSheet("color: #6b7280;")
        words.addWidget(self.lbl_edits, stretch=1)
        layout.addLayout(words)

        part_row = QHBoxLayout()
        part_row.addWidget(self.lbl_gap)
        self.lbl_part = QLabel()
        self.lbl_part.setStyleSheet("color: #6b7280;")
        self.lbl_part.setWordWrap(True)
        part_row.addWidget(self.lbl_part, stretch=1)
        layout.addLayout(part_row)

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

    def voice_of_source(self):
        """The voice analysis made from the song's original audio (SongMaker, sync_scan) moved to the time of the
        converted .ogg the editor plays (it gets the silence of a positive VIDEOGAP and loses the #START cut)."""
        try:
            source = os.path.join(self.song_dir, str(np.load(self.voice_path)['audio']))
        except (OSError, KeyError, ValueError):
            return None
        if not os.path.isfile(source) or os.path.abspath(source) == os.path.abspath(self.audio_file):
            return None
        voice = SyncModel.load_voice(self.voice_path, source)
        if voice is None:
            return None
        frames = int(round((self.video_gap_s - self.trim_start_s) / SyncModel.FRAME))
        for key, empty in (('energy', 0.0), ('pitch', np.nan), ('active', False)):
            values = voice[key]
            if frames > 0:
                voice[key] = np.concatenate([np.full(frames, empty, dtype=values.dtype), values])
            elif frames < 0:
                voice[key] = values[-frames:]
        return voice

    def still_video_note(self):
        """A warning when the video shown here is a still image but the game's .bk2 is a real video (it can't be
        played here)."""
        try:
            name_id = naming.construct_name_id_from_directory_name(os.path.basename(self.song_dir))
            with open(os.path.join(self.song_dir, name_id + naming.VXLA_META_SUFFIX), encoding='utf-8') as f:
                duration = float(json.load(f).get('duration') or 0)
            bk2 = os.path.join(self.song_dir, name_id + naming.VIDEO_BK2_SUFFIX)
            if not duration or not os.path.isfile(bk2):
                return None
            bk2_real = not ConvertFiles.is_still_bk2(Path(bk2), duration)
            if bk2_real and (self.video_file is None or looks_still(self.video_file, duration)):
                return tr("The game's video (.bk2) is a real music video, but the video file of this folder is a still "
                          "image (or missing) and this editor can't play .bk2 files: here you see the still image.")
        except (OSError, ValueError):
            pass
        return None

    def update_info(self):
        notes = []
        if self.game_video_note:
            notes.append(self.game_video_note)
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

    def part_of(self, line):
        """First line of the part a line belongs to: 0 (no cut before it) or the cut that starts its part."""
        cuts = [c for c in self.splits if c <= line]
        return max(cuts) if cuts else 0

    def part_end(self, part):
        """Last line of a part (the line before the next cut, or the last line)."""
        later = [c for c in self.splits if c > part]
        return (min(later) if later else len(self.song.lines)) - 1

    def recompute_extra(self):
        # every part keeps its own shift: moving one never drags the parts after it
        self.line_extra = [self.splits.get(self.part_of(i), 0.0) for i in range(len(self.song.lines))]

    # ------------------------------------------------------------------ editing
    def changed(self):
        return self.gap_ms != self.original_gap_ms or any(abs(d) > 1e-9 for d in self.splits.values()) \
            or bool(self.pitch_edits()) or bool(self.text_edits) or bool(self.deleted) or bool(self.time_edits()) \
            or (not self.official and bool(self.inserted_notes()))

    def pitch_edits(self):
        """{note index: new UltraStar pitch} of the notes moved up or down."""
        return {i: int(round(n.pitch)) - 60 for i, n in enumerate(self.all_notes[:self.file_notes])
                if n.sung and n.pitch != self.original_pitches[i] and i not in self.deleted}

    def time_edits(self):
        """{note index: (start beat, length in beats)} of the notes moved in time or made longer/shorter."""
        beat = self.beat_s()
        if not beat or self.official:
            return {}
        return {i: (int(round(n.t / beat)), max(1, int(round(n.d / beat))))
                for i, n in enumerate(self.all_notes[:self.file_notes]) if i not in self.deleted and (abs(n.t - self.original_times[i][0]) > 1e-6
                                              or abs(n.d - self.original_times[i][1]) > 1e-6)}

    def note_limits(self, note):
        """(first beat, last beat) a note can take without going over the notes before and after it."""
        beat = self.beat_s()
        pos = self.order.index(self.note_index[id(note)])
        before = next((self.all_notes[j] for j in reversed(self.order[:pos]) if j not in self.deleted), None)
        after = next((self.all_notes[j] for j in self.order[pos + 1:] if j not in self.deleted), None)
        lo = int(round((before.t + before.d) / beat)) if before else -10 ** 9
        hi = int(round(after.t / beat)) if after else 10 ** 9
        return lo, hi

    def set_note_time(self, note, start, end, keep_length=False):
        """Puts a note between start and end (seconds without the line shift), in whole beats of the song and
        never over its neighbours; keep_length: it is moved, not resized."""
        beat = self.beat_s()
        if self.official or not beat or note is None:
            return
        lo, hi = self.note_limits(note)
        if hi - lo < 1:
            return
        a, b = int(round(start / beat)), int(round(end / beat))
        if keep_length:
            length = min(max(1, int(round(note.d / beat))), hi - lo)
            a = max(lo, min(a, hi - length))
            b = a + length
        else:
            a, b = max(lo, a), min(hi, b)
            if b - a < 1:  # the edge being dragged stops one beat before the other
                if start != note.t:
                    a = b - 1
                else:
                    b = a + 1
        if (a * beat, (b - a) * beat) != (note.t, note.d):
            note.t, note.d = a * beat, (b - a) * beat
            self.rebuild_song()

    def nudge_selected(self, beats=0, longer=0):
        """Keyboard: moves the selected note by beats, or makes it longer/shorter."""
        note, beat = self.selected_note, self.beat_s()
        if note is None or not beat:
            return
        group = self.selection()
        if beats and len(group) > 1:
            lo, hi = self.group_range(group)
            k = max(lo, min(hi, beats))
            if k:
                self.shift_group([(n, n.t, n.d, n.pitch) for n in group], k * beat, (lo, hi))
            return
        if beats:
            self.set_note_time(note, note.t + beats * beat, note.t + note.d + beats * beat, keep_length=True)
        elif longer:
            self.set_note_time(note, note.t, note.t + note.d + longer * beat)

    # ------------------------------------------------------------------ several notes selected
    def selected_indices(self):
        """Indices of the selected notes (the clicked one and the ones added with Ctrl/Shift), in time order."""
        chosen = set(self.chosen)
        if self.selected_note is not None and id(self.selected_note) in self.note_index:
            chosen.add(self.note_index[id(self.selected_note)])
        return [i for i in self.order if i in chosen and i not in self.deleted]

    def selection(self):
        return [self.all_notes[i] for i in self.selected_indices()]

    def is_selected(self, note):
        return self.note_index.get(id(note)) in set(self.selected_indices())

    def clear_selection(self):
        self.chosen.clear()

    def toggle_selected(self, note):
        index = self.note_index[id(note)]
        chosen = set(self.selected_indices())
        if index in chosen:
            chosen.discard(index)
            rest = [i for i in self.order if i in chosen]
            self.selected_note = self.all_notes[rest[-1]] if rest else None
        else:
            chosen.add(index)
            self.selected_note = note
        self.chosen = chosen

    def select_range(self, note):
        """Every note from the selected one (or the first selected) to this one."""
        index = self.note_index[id(note)]
        chosen = self.selected_indices()
        if not chosen:
            self.selected_note, self.chosen = note, set()
            return
        live = [i for i in self.order if i not in self.deleted]
        anchor = self.note_index[id(self.selected_note)] if self.selected_note is not None else chosen[0]
        a, b = sorted((live.index(anchor), live.index(index)))
        self.chosen = set(live[a:b + 1])
        self.selected_note = note

    def select_time_range(self, t_a, t_b, keep=()):
        """Selects the notes that start between two lane times (Shift + drag on the empty lane)."""
        t_a, t_b = sorted((t_a, t_b))
        picked = [i for i in self.order if i not in self.deleted
                  and t_a <= self.note_time(self.all_notes[i]) <= t_b]
        self.chosen = set(keep) | set(picked)
        self.selected_note = self.all_notes[picked[-1]] if picked else \
            (self.selected_note if self.chosen else None)
        self.refresh_labels()

    def select_line(self):
        """Ctrl+A: every note of the selected note's line (or of the line being played)."""
        if self.official:
            return
        line = self.selected_note.line if self.selected_note is not None else self.current_line()
        notes = self.line_notes(line)
        if notes:
            self.chosen = set(notes)
            self.selected_note = self.all_notes[notes[0]]
            self.lane.update()
            self.refresh_labels()

    def group_range(self, notes):
        """(fewest, most) beats the notes can move together without going over the notes that are not moved."""
        beat = self.beat_s()
        group = {self.note_index[id(n)] for n in notes}
        live = [i for i in self.order if i not in self.deleted]
        where = {i: k for k, i in enumerate(live)}
        lo, hi = -10 ** 9, 10 ** 9
        for n in notes:
            k = where[self.note_index[id(n)]]
            start = int(round(n.t / beat))
            end = start + max(1, int(round(n.d / beat)))
            if k > 0 and live[k - 1] not in group:
                before = self.all_notes[live[k - 1]]
                lo = max(lo, int(round((before.t + before.d) / beat)) - start)
            if k + 1 < len(live) and live[k + 1] not in group:
                hi = min(hi, int(round(self.all_notes[live[k + 1]].t / beat)) - end)
        return min(lo, 0), max(hi, 0)

    def shift_group(self, group, seconds, limits):
        """Moves notes together in time from where they were ([(note, start, length, pitch)]), in whole beats and
        without going over the other notes."""
        beat = self.beat_s()
        if self.official or not beat:
            return
        k = max(limits[0], min(limits[1], int(round(seconds / beat))))
        changed = False
        for note, t, d, _ in group:
            new = (int(round(t / beat)) + k) * beat, max(1, int(round(d / beat))) * beat
            if (note.t, note.d) != new:
                note.t, note.d = new
                changed = True
        if changed:
            self.rebuild_song()

    def set_group_pitch(self, group, steps):
        """Pitch of notes dragged up/down together: each one steps semitones from where it was."""
        changed = False
        for note, _, _, pitch in group:
            if note.sung and note.pitch != max(0, min(127, pitch + steps)):
                note.pitch = max(0, min(127, pitch + steps))
                changed = True
        if changed:
            self.lane.update()
            self.refresh_labels()

    def note_text(self, note):
        """The syllable drawn under a note ('' for held notes and official files)."""
        if self.official:
            return ''
        index = self.note_index.get(id(note))
        text = self.text_of(index) if index is not None else ''
        return '' if text.strip() in ('', '~') else text.strip()

    # ------------------------------------------------------------------ lyrics editing (not for official files)
    def text_of(self, index):
        return self.text_edits.get(index, self.raw_texts[index])

    def rebuild_song(self):
        """self.song again from every note, without the deleted ones and with the fixed texts."""
        notes = [self.all_notes[i] for i in self.order]
        texts = [self.text_of(i) for i in self.order]
        deleted = {k for k, i in enumerate(self.order) if i in self.deleted}
        self.song = SyncModel.song_from_notes(notes, texts, self.line_count, self.song.bpm, deleted)
        if self.selected_note is not None and self.note_index[id(self.selected_note)] in self.deleted:
            self.selected_note = None
        self.chosen = {i for i in self.chosen if i < len(self.all_notes) and i not in self.deleted}
        self.lane.update()
        self.sync_map.update()
        self.refresh_labels()
        self.schedule_report()

    def set_text(self, index, text):
        text = text if text.strip() else '~'  # an empty piece holds the syllable before
        if text == self.raw_texts[index]:
            self.text_edits.pop(index, None)
        else:
            self.text_edits[index] = text

    def line_notes(self, line):
        return [i for i in self.order if self.all_notes[i].line == line and i not in self.deleted]

    def split_note(self, note):
        """Splits a note in two (first half: the note, second half: a new held note "~" with the same pitch).
        Returns the new note, or None when it lasts less than 2 beats."""
        beat = self.beat_s()
        if self.official or not beat or note is None:
            return None
        length = int(round(note.d / beat))
        if length < 2:
            return None
        first = (length + 1) // 2
        new = SyncModel.Note(note.t + first * beat, (length - first) * beat, note.pitch, note.kind, note.line)
        note.d = first * beat
        k = len(self.all_notes)
        self.all_notes.append(new)
        self.raw_texts.append('~')
        self.original_pitches.append(new.pitch)
        self.original_times.append((new.t, new.d))
        self.note_index[id(new)] = k
        self.order.insert(self.order.index(self.note_index[id(note)]) + 1, k)
        return new

    def split_selected(self):
        """Button: splits the selected note in two, to give a missing syllable its own note."""
        note = self.selected_note
        if self.official or note is None:
            return
        new = self.split_note(note)
        if new is None:
            self.lbl_part.setText(tr("This note is too short to split (it needs 2 beats or more): make it longer "
                                     "first."))
            return
        self.selected_note = new
        self.rebuild_song()
        self.edit_note_text(new)

    def inserted_notes(self):
        """{index of the file note they follow: [(kind, start beat, length, UltraStar pitch, text)]} of the notes
        added in the editor."""
        beat, out, anchor = self.beat_s(), {}, None
        for i in self.order:
            if i < self.file_notes:
                anchor = i
            elif i not in self.deleted and anchor is not None:
                n = self.all_notes[i]
                out.setdefault(anchor, []).append((n.kind, int(round(n.t / beat)), max(1, int(round(n.d / beat))),
                                                   int(round(n.pitch)) - 60, self.text_of(i)))
        return out

    def edit_note_text(self, note):
        """Fixes the text of one note (a misspelt syllable)."""
        if self.official or note is None:
            return
        index = self.note_index[id(note)]
        text, ok = QInputDialog.getText(
            self, tr("Fix syllable"),
            tr("Text of this note. A space at the end ends the word; ~ holds the syllable before."),
            text=self.text_of(index))
        if ok:
            self.set_text(index, text)
            self.rebuild_song()

    def edit_line_text(self):
        """Fixes the text of the line being played (or of the selected note's line), one piece per note."""
        if self.official:
            return
        line = self.selected_note.line if self.selected_note is not None else self.current_line()
        indices = self.line_notes(line)
        if not indices:
            return
        current = '|'.join(self.text_of(i) for i in indices)
        text, ok = QInputDialog.getText(
            self, tr("Fix the lyrics of line {n}").format(n=line + 1),
            tr("One piece per note, separated by |. A space at the end of a piece ends the word; ~ holds the "
               "syllable before. This line has {n} notes; write more pieces to add syllables (the note before "
               "them is split).").format(n=len(indices)),
            text=current)
        if not ok or text == current:
            return
        pieces = text.split('|')
        plan = self.pieces_per_note(indices, pieces)
        short = [i for i, got in plan.items() if len(got) > max(1, int(round(self.all_notes[i].d / self.beat_s())))]
        if short:
            QMessageBox.warning(self, tr("Fix the lyrics of line {n}").format(n=line + 1),
                                tr("There is no room for the syllables added after \"{text}\": its note is too short "
                                   "to split. Make it longer first (drag its right edge).").format(
                                    text=self.text_of(short[0]).strip()))
            return
        for i in indices:
            got = plan[i]
            group = [self.all_notes[i]]
            while len(group) < len(got):  # syllables added here: the note is split, the longest part each time
                longest = max(group, key=lambda n: n.d)
                group.insert(group.index(longest) + 1, self.split_note(longest))
            for note, piece in zip(group, got or ['~']):  # a syllable taken out: its note holds the one before
                self.set_text(self.note_index[id(note)], piece)
        self.rebuild_song()

    def pieces_per_note(self, indices, pieces):
        """{note index: [pieces]} for the fixed text of a line: the pieces are matched with the notes' texts as they
        were, so a syllable added between two others goes to the note before it (split later), a changed one to its
        own note and one taken out leaves its note empty."""
        import difflib
        old = [self.text_of(i).strip().lower() for i in indices]
        new = [p.strip().lower() for p in pieces]
        plan = {i: [] for i in indices}
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
            notes, got = indices[i1:i2], pieces[j1:j2]
            if tag == 'insert':
                if i1 > 0:
                    plan[indices[i1 - 1]] += got
                else:
                    plan[indices[0]] = got + plan[indices[0]]
                continue
            for k, i in enumerate(notes):  # one piece per note, what is left goes to the last one
                plan[i] += got[k:k + 1] if k < len(notes) - 1 else got[k:]
        return plan

    def delete_selected(self):
        """Takes out the selected syllables with their notes (their held "~" notes too): lyrics where nothing is
        sung."""
        notes = self.selection()
        if self.official or not notes:
            return
        for note in notes:
            if self.note_index[id(note)] not in self.deleted:
                self.delete_note(note)
        self.selected_note = None
        self.chosen.clear()
        self.rebuild_song()

    def delete_note(self, note):
        first = self.note_index[id(note)]
        pos = self.order.index(first)
        indices = [first]
        if self.text_of(first).strip() not in ('~', ''):
            for j in self.order[pos + 1:]:
                if self.all_notes[j].line != note.line or \
                        (j not in self.deleted and self.text_of(j).strip() not in ('~', '')):
                    break
                if j not in self.deleted:
                    indices.append(j)
        ended_word = self.text_of(first).endswith(' ') or self.text_of(indices[-1]).endswith(' ')
        before = [i for i in self.line_notes(note.line) if self.order.index(i) < pos]
        if ended_word and before and not self.text_of(before[-1]).endswith(' '):
            self.set_text(before[-1], self.text_of(before[-1]) + ' ')  # the word before still ends there
        self.deleted.update(indices)

    def delete_line(self):
        """Takes out the line being played (or the selected note's line) with all its notes."""
        if self.official:
            return
        line = self.selected_note.line if self.selected_note is not None else self.current_line()
        indices = self.line_notes(line)
        if not indices:
            return
        words = ''.join(self.text_of(i).replace('~', '') for i in indices).strip()
        reply = QMessageBox.question(self, tr("Delete line"),
                                     tr("Delete line {n} \"{text}\" and its {count} notes?").format(
                                         n=line + 1, text=words, count=len(indices)))
        if reply != QMessageBox.Yes:
            return
        self.deleted.update(indices)
        self.selected_note = None
        self.rebuild_song()

    def move_selected_note(self, semitones):
        """Moves the selected note up or down (pitch editing; not for official lyrics files)."""
        if self.official:
            return
        changed = False
        for note in self.selection():
            if note.sung:
                note.pitch = max(0, min(127, note.pitch + semitones))
                changed = True
        if changed:
            self.lane.update()
            self.refresh_labels()

    def beat_s(self):
        return 60.0 / self.song.bpm / 4 if self.song.bpm else 0.0

    def adjust(self, amount_ms):
        """Moves the selected part (or all the lyrics when no part is selected), wherever the playback is."""
        if self.official:
            return
        if self.selected == 0:
            self.gap_ms += amount_ms
        else:
            self.splits[self.selected] += amount_ms / 1000.0
            self.recompute_extra()
        self.refresh_labels()
        self.schedule_report()

    def add_cut(self, line):
        """A part starts at line; it keeps the shift it had, so cutting never moves anything."""
        if line > 0 and line not in self.splits:
            self.splits[line] = self.line_extra[line]
            self.recompute_extra()

    def cut_start(self):
        """Cut at the start of the line being played and select the part that starts there."""
        if self.official:
            return
        line = self.current_line()
        if line == 0:
            self.select_part(0)
            self.lbl_part.setText(tr("The first line already moves with the whole lyrics (#GAP)."))
            return
        self.add_cut(line)
        self.select_part(line)

    def cut_end(self):
        """Cut at the start of the line being played: the selected part ends just before it, the rest stays."""
        if self.official:
            return
        line = self.current_line()
        if line == 0:
            return
        self.add_cut(line)
        self.refresh_labels()

    def select_part(self, part):
        self.selected = part if part == 0 or part in self.splits else self.part_of(part)
        self.refresh_labels()

    def select_part_at(self, seconds):
        """Selects the part playing at that time (click on the map)."""
        line = 0
        for i in range(len(self.song.lines)):
            if self.line_time(i) <= seconds + 0.05:
                line = i
        self.select_part(self.part_of(line))

    def step_part(self, step):
        parts = [0] + sorted(self.splits)
        i = parts.index(self.selected) if self.selected in parts else 0
        self.select_part(parts[min(max(i + step, 0), len(parts) - 1)])

    def remove_cut(self):
        """Joins the selected part to the one before it (its lines take that part's shift)."""
        part = self.selected
        if part in self.splits:
            del self.splits[part]
            self.recompute_extra()
            self.select_part(self.part_of(part))
            self.schedule_report()

    # ------------------------------------------------------------------ undo / redo
    def state(self):
        """Everything the edits change: (key to compare, data to restore)."""
        added = tuple(self.all_notes[self.file_notes:])
        values = tuple((n.t, n.d, n.pitch) for n in self.all_notes)
        key = (self.gap_ms, tuple(sorted(self.splits.items())), values, tuple(id(n) for n in added),
               tuple(sorted(self.text_edits.items())), frozenset(self.deleted), tuple(self.order))
        data = {'gap': self.gap_ms, 'splits': dict(self.splits), 'values': values, 'added': added,
                'added_info': (list(self.raw_texts[self.file_notes:]), list(self.original_pitches[self.file_notes:]),
                               list(self.original_times[self.file_notes:])),
                'texts': dict(self.text_edits), 'deleted': set(self.deleted), 'order': list(self.order),
                'selected': self.selected}
        return key, data

    def dragging(self):
        lane = getattr(self, 'lane', None)
        return lane is not None and getattr(lane, '_drag', None) is not None and lane._drag['zone'] != 'pan'

    def record_state(self):
        """Adds the current edits to the undo history when they changed (not in the middle of a drag)."""
        if self.dragging():
            return
        key, data = self.state()
        if self.history and self.history[-1][0] == key:
            return
        self.history.append((key, data))
        del self.history[:-500]
        self.future.clear()
        self.update_undo_buttons()

    def restore_state(self, data):
        self.gap_ms = data['gap']
        self.splits = dict(data['splits'])
        del self.all_notes[self.file_notes:]
        self.all_notes.extend(data['added'])
        raw, pitches, times = data['added_info']
        for target, extra in ((self.raw_texts, raw), (self.original_pitches, pitches), (self.original_times, times)):
            del target[self.file_notes:]
            target.extend(extra)
        for note, (t, d, pitch) in zip(self.all_notes, data['values']):
            note.t, note.d, note.pitch = t, d, pitch
        self.note_index = {id(n): i for i, n in enumerate(self.all_notes)}
        self.text_edits = dict(data['texts'])
        self.deleted = set(data['deleted'])
        self.order = list(data['order'])
        if self.selected_note is not None and id(self.selected_note) not in self.note_index:
            self.selected_note = None
        self.chosen = {i for i in self.chosen if i < len(self.all_notes)}
        self.recompute_extra()
        self.selected = data['selected'] if data['selected'] == 0 or data['selected'] in self.splits else 0
        if not self.official:
            self.rebuild_song()
        self.lane.update()
        self.sync_map.update()
        self.refresh_labels()
        self.schedule_report()

    def undo(self):
        """Ctrl+Z: back to the state before the last change."""
        if self.dragging():
            return
        self.history_timer.stop()
        self.record_state()  # a change not recorded yet
        if len(self.history) < 2:
            self.lbl_part.setText(tr("Nothing to undo."))
            return
        self.future.append(self.history.pop())
        self.restore_state(self.history[-1][1])
        self.update_undo_buttons()

    def redo(self):
        if self.dragging() or not self.future:
            return
        self.history_timer.stop()
        self.history.append(self.future.pop())
        future = self.future
        self.restore_state(self.history[-1][1])
        self.future = future
        self.update_undo_buttons()

    def update_undo_buttons(self):
        if hasattr(self, 'btn_undo'):
            self.btn_undo.setEnabled(len(self.history) > 1)
            self.btn_redo.setEnabled(bool(self.future))

    def ask_undo_all(self):
        if not self.changed():
            return
        if QMessageBox.question(self, tr("Undo all the changes"),
                                tr("Undo every change made since the editor was opened? (Ctrl+Z brings them back)"),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.undo_all()

    def undo_all(self):
        for note, pitch, (t, d) in zip(self.all_notes, self.original_pitches, self.original_times):
            note.pitch, note.t, note.d = pitch, t, d
        if not self.official:  # notes added in the editor go
            for added in (self.all_notes, self.raw_texts, self.original_pitches, self.original_times):
                del added[self.file_notes:]
            self.order = list(range(self.file_notes))
            self.note_index = {id(n): i for i, n in enumerate(self.all_notes)}
        self.selected_note = None
        self.text_edits.clear()
        self.deleted.clear()
        if not self.official:
            self.rebuild_song()
        self.gap_ms = self.original_gap_ms
        self.splits.clear()
        self.selected = 0
        self.recompute_extra()
        self.refresh_labels()
        self.schedule_report()

    def auto_adjust(self):
        """Moves the line being played, and its part up to the next cut, to where the voice analysis found it."""
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
        if line != 0:
            self.add_cut(line)
        self.select_part(self.part_of(line))
        self.adjust(extra * 1000)

    def overlapping_line(self):
        """First line that starts before the previous one ends (it cannot be saved like that), or None."""
        for i in range(1, len(self.song.lines)):
            if self.line_extra[i] != self.line_extra[i - 1] and self.line_time(i) < self.line_end(i - 1) - 1e-6:
                return i
        return None

    def refresh_labels(self):
        part = self.selected
        if part == 0 and not self.splits:
            self.lbl_gap.setText(tr("All the lyrics: GAP {gap} ms").format(gap=int(round(self.gap_ms))) +
                                 (f"  ({self.gap_ms - self.original_gap_ms:+.0f})"
                                  if self.gap_ms != self.original_gap_ms else ""))
        elif part == 0:
            self.lbl_gap.setText(tr("All the lyrics (GAP {gap} ms): every part moves").format(
                gap=int(round(self.gap_ms))))
        else:
            last = self.part_end(part)
            self.lbl_gap.setText(tr("Lines {a}-{b} ({t1} - {t2}): {ms:+.0f} ms").format(
                a=part + 1, b=last + 1, t1=fmt_time(self.line_time(part)), t2=fmt_time(self.line_end(last)),
                ms=self.splits[part] * 1000))
        hint = ""
        if self.splits:
            hint += tr("{n} parts. The arrows move the selected part (click another one on the map, or [ ]). ").format(
                n=len(self.splits) + 1)
            if self.beat_s():
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
        if hasattr(self, 'lbl_edits'):
            parts = []
            count = len(self.selected_indices())
            if count > 1 and not self.official:
                parts.append(tr("{n} notes selected (drag one or Alt+arrows: they move together; Esc: none)")
                             .format(n=count))
            elif self.selected_note is not None and not self.official:
                parts.append(tr("Selected: \"{text}\"").format(
                    text=self.text_of(self.note_index[id(self.selected_note)])))
            if self.deleted:
                parts.append(tr("{n} notes deleted").format(n=len(self.deleted)))
            if self.text_edits:
                parts.append(tr("{n} texts fixed").format(n=len(self.text_edits)))
            timed = self.time_edits()
            if timed:
                parts.append(tr("{n} notes moved or resized").format(n=len(timed)))
            added = sum(len(v) for v in self.inserted_notes().values()) if not self.official else 0
            if added:
                parts.append(tr("{n} notes added").format(n=added))
            if self.deleted or self.text_edits or timed or added:
                parts.append(tr("save to keep it"))
            self.lbl_edits.setText(" · ".join(parts))
        self.btn_uncut.setEnabled(part != 0 and not self.official)
        self.btn_all.setChecked(part == 0)
        self.update_info()
        if hasattr(self, 'history_timer'):
            self.history_timer.start(0)

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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and (self.selected_note is not None or self.chosen):
            self.selected_note = None
            self.chosen.clear()
            self.lane.update()
            self.refresh_labels()
            return
        super().keyPressEvent(event)

    def reject(self):
        """Esc (or closing): unsaved changes are not lost without asking."""
        if self.changed():
            reply = QMessageBox.question(self, tr('Unsaved changes'), tr('Save the sync changes before closing?'),
                                         QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Yes)
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.Yes:
                self.save()  # closes the editor when it worked
                return
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
                                          expected_notes=self.file_notes, note_pitches=self.pitch_edits(),
                                          note_texts={i: t for i, t in self.text_edits.items() if i < self.file_notes},
                                          deleted_notes={i for i in self.deleted if i < self.file_notes},
                                          note_times=self.time_edits(), inserted_notes=self.inserted_notes())
            if not os.path.exists(self.txt_path + '.bak'):
                # the first time a song is re-synced its original txt is kept, it can always be restored
                with open(self.txt_path + '.bak', 'wb') as f:
                    f.write(raw)
            tmp_path = self.txt_path + '.tmp'
            with open(tmp_path, 'w', encoding=encoding, newline='') as f:
                f.write(newline.join(lines) + (newline if text.endswith(('\n', '\r')) else ''))
            os.replace(tmp_path, self.txt_path)

            self.original_gap_ms = self.gap_ms  # Prevent unsaved changes prompt on app exit
            self.original_pitches = [n.pitch for n in self.all_notes]
            self.original_times = [(n.t, n.d) for n in self.all_notes]
            self.text_edits.clear()
            self.deleted.clear()
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
