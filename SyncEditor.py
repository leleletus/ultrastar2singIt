import sys
import os
from html import escape
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, 
                               QPushButton, QLabel, QSlider, QWidget, QTextBrowser, QMessageBox)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

import UltrastarToSingit
import naming
from i18n import tr

class SyncEditorDialog(QDialog):
    def __init__(self, txt_path, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import Qt
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.txt_path = txt_path
        self.setWindowTitle(f"Sync Editor - {os.path.basename(txt_path)}")
        self.resize(800, 600)
        
        self.saved = False
        self.us_data = UltrastarToSingit.parse_file(txt_path)
        self.bpm = float(self.us_data["BPM"].replace(',', '.'))
        self.gap_ms = float(self.us_data.get("GAP", "0").replace(',', '.') or 0)
        try:
            self.video_gap_s = float(self.us_data.get("VIDEOGAP", "0").replace(',', '.') or 0)
        except ValueError:
            self.video_gap_s = 0.0

        self.audio_file = None
        self.video_file = None

        self.original_gap_ms = self.gap_ms
        self.build_lines()

        song_dir = os.path.dirname(txt_path)
        folder_name = os.path.basename(song_dir).rstrip('.')
        converted_ogg = os.path.join(song_dir, naming.construct_name_id_from_directory_name(folder_name) + naming.AUDIO_SUFFIX)
        # The converted .ogg is what the game plays: VIDEOGAP is already applied to it, so the lyrics
        # (and not the video) are shifted by VIDEOGAP. With the original audio it is the other way round.
        self.audio_is_converted = os.path.isfile(converted_ogg)
        # #START handling of the converter: how much the lyrics were moved, and the audio cut
        self.lyrics_offset_s, self.trim_start_s = 0.0, 0.0
        meta_path = os.path.join(song_dir, naming.construct_name_id_from_directory_name(folder_name) + naming.AUDIO_META_SUFFIX)
        try:
            import json
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            self.lyrics_offset_s = float(meta.get('lyrics_offset') or 0)
            self.trim_start_s = float(meta.get('trim_start') or 0)
        except (OSError, ValueError):
            pass
        if self.audio_is_converted:
            self.audio_file = converted_ogg
        else:
            for tag in ("AUDIO", "MP3"):
                if self.us_data.get(tag) and os.path.isfile(os.path.join(song_dir, self.us_data[tag])):
                    self.audio_file = os.path.join(song_dir, self.us_data[tag])
                    break

        if self.us_data.get("VIDEO") and os.path.isfile(os.path.join(song_dir, self.us_data["VIDEO"])):
            self.video_file = os.path.join(song_dir, self.us_data["VIDEO"])
            
        # UI Setup
        layout = QVBoxLayout(self)
        
        self.video_widget = QVideoWidget()
        layout.addWidget(self.video_widget, stretch=1)
        
        self.lyrics_display = QLabel(tr("Lyrics will appear here..."))
        self.lyrics_display.setAlignment(Qt.AlignCenter)
        self.lyrics_display.setStyleSheet("font-size: 24px; font-weight: bold; color: yellow; background-color: black; padding: 10px;")
        layout.addWidget(self.lyrics_display)
        
        self.video_player = QMediaPlayer(self)
        self.video_player.setVideoOutput(self.video_widget)
        
        self.audio_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(1.0)
        self.audio_player.setAudioOutput(self.audio_output)
        
        # Load media
        if self.video_file and os.path.exists(self.video_file):
            self.video_player.setSource(QUrl.fromLocalFile(self.video_file))
        if self.audio_file and os.path.exists(self.audio_file):
            self.audio_player.setSource(QUrl.fromLocalFile(self.audio_file))
            
        # Controls
        controls_layout = QHBoxLayout()
        self.btn_play = QPushButton(tr("Play/Pause"))
        self.btn_play.clicked.connect(self.toggle_play)
        controls_layout.addWidget(self.btn_play)
        
        self.slider = QSlider(Qt.Horizontal)
        self.slider.sliderMoved.connect(self.seek)
        controls_layout.addWidget(self.slider)
        
        layout.addLayout(controls_layout)
        
        # Gap Adjustments (Visual Slider and Buttons)
        gap_layout = QVBoxLayout()
        gap_controls_layout = QHBoxLayout()
        
        self.btn_minus_gap_big = QPushButton(tr("<<< -250 ms"))
        self.btn_minus_gap_big.clicked.connect(lambda: self.adjust_gap(-250))
        self.btn_minus_gap = QPushButton(tr("<< Lyrics earlier (-50 ms)"))
        self.btn_minus_gap.clicked.connect(lambda: self.adjust_gap(-50))
        self.btn_minus_gap_fine = QPushButton(tr("< -10 ms"))
        self.btn_minus_gap_fine.clicked.connect(lambda: self.adjust_gap(-10))

        self.lbl_gap = QLabel(self.gap_text())
        self.lbl_gap.setAlignment(Qt.AlignCenter)
        self.lbl_gap.setStyleSheet("font-weight: bold; font-size: 16px;")
        
        self.btn_plus_gap_fine = QPushButton(tr("+10 ms >"))
        self.btn_plus_gap_fine.clicked.connect(lambda: self.adjust_gap(10))
        self.btn_plus_gap = QPushButton(tr("Lyrics later (+50 ms) >>"))
        self.btn_plus_gap.clicked.connect(lambda: self.adjust_gap(50))
        self.btn_plus_gap_big = QPushButton(tr("+250 ms >>>"))
        self.btn_plus_gap_big.clicked.connect(lambda: self.adjust_gap(250))

        for w in (self.btn_minus_gap_big, self.btn_minus_gap, self.btn_minus_gap_fine, self.lbl_gap,
                  self.btn_plus_gap_fine, self.btn_plus_gap, self.btn_plus_gap_big):
            gap_controls_layout.addWidget(w)
        
        # Visual Lyrics Track Slider
        self.gap_slider = QSlider(Qt.Horizontal)
        self.gap_slider.setMinimum(int(min(-10000, self.gap_ms - 10000)))
        self.gap_slider.setMaximum(int(max(10000, self.gap_ms + 10000)))
        self.gap_slider.setValue(int(self.gap_ms))
        self.gap_slider.sliderMoved.connect(self.slider_adjust_gap)
        self.gap_slider.setStyleSheet("QSlider::handle:horizontal { background: #ffaa00; width: 15px; }")
        
        slider_label = QLabel(tr("Move the whole lyrics track (left / right):"))
        
        gap_layout.addWidget(slider_label)
        gap_layout.addWidget(self.gap_slider)
        gap_layout.addLayout(gap_controls_layout)
        
        self.btn_save = QPushButton(tr("Save sync changes"))
        self.btn_save.clicked.connect(self.save_gap)
        self.btn_save.setStyleSheet("background-color: green; color: white; font-size: 16px; padding: 10px;")
        gap_layout.addWidget(self.btn_save)
        
        layout.addLayout(gap_layout)
        
        # Timers
        self.audio_player.positionChanged.connect(self.update_slider)
        self.audio_player.durationChanged.connect(self.slider.setMaximum)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_lyrics)
        self.timer.start(50)
        

    def build_lines(self):
        self.lines = []
        current_line = []
        for note in self.us_data["notes"]:
            if note[0] in [':', '*', 'F', 'R', 'G']:
                current_line.append(note)
            elif note[0] == '-':
                if current_line:
                    self.lines.append(current_line)
                    current_line = []
        if current_line:
            self.lines.append(current_line)

    def stop_players(self):
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

    def toggle_play(self):
        if self.audio_player.playbackState() == QMediaPlayer.PlayingState:
            self.audio_player.pause()
            self.video_player.pause()
        else:
            self.video_player.setPosition(max(0, self.audio_player.position() + self.video_offset_ms()))
            self.audio_player.play()
            self.video_player.play()
            
    def video_offset_ms(self):
        return 0 if self.audio_is_converted else int(self.video_gap_s * 1000)

    def lyrics_offset_s(self):
        if self.audio_is_converted:
            return self.gap_ms / 1000.0 + self.video_gap_s - self.lyrics_offset_s
        # original audio: only moved when it is a shorter version that already starts at #START
        return self.gap_ms / 1000.0 - (self.lyrics_offset_s - self.trim_start_s)

    def gap_text(self):
        return tr("Offset (GAP): {gap} ms").format(gap=int(self.gap_ms))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.toggle_play()
        elif event.key() == Qt.Key_Left:
            self.adjust_gap(-50 if not event.modifiers() & Qt.ShiftModifier else -10)
        elif event.key() == Qt.Key_Right:
            self.adjust_gap(50 if not event.modifiers() & Qt.ShiftModifier else 10)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def seek(self, position):
        self.audio_player.setPosition(position)
        self.video_player.setPosition(max(0, position + self.video_offset_ms()))
        
    def update_slider(self, position):
        if not self.slider.isSliderDown():
            self.slider.setValue(position)
            
    def adjust_gap(self, amount):
        self.gap_ms += amount
        self.lbl_gap.setText(self.gap_text())
        self.gap_slider.blockSignals(True)
        self.gap_slider.setValue(int(self.gap_ms))
        self.gap_slider.blockSignals(False)
        
    def slider_adjust_gap(self, value):
        self.gap_ms = float(value)
        self.lbl_gap.setText(self.gap_text())
        


    def update_lyrics(self):
        pos_s = self.audio_player.position() / 1000.0
        gap_s = self.lyrics_offset_s()
        
        active_index = -1
        for i, line in enumerate(self.lines):
            if not line: continue
            end_s = (float(line[-1][1]) + float(line[-1][2])) * 60 / self.bpm / 4 + gap_s
            
            # Consider active if we haven't passed the end of the line by more than 0.5s
            if pos_s <= end_s + 0.5:
                active_index = i
                break
                
        if active_index != -1:
            display_html = ""
            
            # Previous Line
            if active_index > 0:
                prev_line = self.lines[active_index - 1]
                prev_text = "".join(escape(note[4].replace('~', '')) for note in prev_line)
                display_html += f"<span style='color: #aaaaaa; font-size: 18px;'>{prev_text}</span><br>"
            else:
                display_html += "<span style='font-size: 18px;'>&nbsp;</span><br>"
                
            # Current Line
            curr_line = self.lines[active_index]
            curr_text = ""
            for note in curr_line:
                n_start = float(note[1]) * 60 / self.bpm / 4 + gap_s
                lyric = escape(note[4].replace('~', ''))
                if pos_s >= n_start:
                    curr_text += f"<span style='color: #00ff00; font-size: 26px; font-weight: bold;'>{lyric}</span>"
                else:
                    curr_text += f"<span style='color: #ffffff; font-size: 26px; font-weight: bold;'>{lyric}</span>"
            display_html += f"{curr_text}<br>"
            
            # Next Line
            if active_index < len(self.lines) - 1:
                next_line = self.lines[active_index + 1]
                next_text = "".join(escape(note[4].replace('~', '')) for note in next_line)
                display_html += f"<span style='color: #aaaaaa; font-size: 18px;'>{next_text}</span>"
            else:
                display_html += "<span style='font-size: 18px;'>&nbsp;</span>"
                
            self.lyrics_display.setText(f"<div align='center'>{display_html}</div>")
        else:
            self.lyrics_display.setText("")

    def save_gap(self):
        """Writes #GAP back keeping the file's encoding and line endings (and adds it if missing)."""
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
