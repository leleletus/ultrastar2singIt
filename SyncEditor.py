import sys
import os
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, 
                               QPushButton, QLabel, QSlider, QWidget, QTextBrowser, QMessageBox)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

import UltrastarToSingit

class SyncEditorDialog(QDialog):
    def __init__(self, txt_path, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import Qt
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.txt_path = txt_path
        self.setWindowTitle(f"Sync Editor - {os.path.basename(txt_path)}")
        self.resize(800, 600)
        
        self.us_data = UltrastarToSingit.parse_file(txt_path)
        self.bpm = float(self.us_data["BPM"].replace(',', '.'))
        self.gap_ms = float(self.us_data.get("GAP", "0").replace(',', '.'))
        self.video_gap_s = float(self.us_data.get("VIDEOGAP", "0").replace(',', '.'))
        

        self.audio_file = None
        self.video_file = None
        
        self.original_gap_ms = self.gap_ms
        self.build_lines()

        
        song_dir = os.path.dirname(txt_path)
        
        import glob
        ogg_files = glob.glob(os.path.join(song_dir, "*.ogg"))
        if ogg_files:
            # Siempre preferir el .ogg convertido porque es el que leerá la Switch
            self.audio_file = ogg_files[0]
        elif "MP3" in self.us_data and self.us_data["MP3"]:
            self.audio_file = os.path.join(song_dir, self.us_data["MP3"])
        
        if "VIDEO" in self.us_data and self.us_data["VIDEO"]:
            self.video_file = os.path.join(song_dir, self.us_data["VIDEO"])
            
        # UI Setup
        layout = QVBoxLayout(self)
        
        self.video_widget = QVideoWidget()
        layout.addWidget(self.video_widget, stretch=1)
        
        self.lyrics_display = QLabel("Lyrics will appear here...")
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
        self.btn_play = QPushButton("Play/Pause")
        self.btn_play.clicked.connect(self.toggle_play)
        controls_layout.addWidget(self.btn_play)
        
        self.slider = QSlider(Qt.Horizontal)
        self.slider.sliderMoved.connect(self.seek)
        controls_layout.addWidget(self.slider)
        
        layout.addLayout(controls_layout)
        
        # Gap Adjustments (Visual Slider and Buttons)
        gap_layout = QVBoxLayout()
        gap_controls_layout = QHBoxLayout()
        
        self.btn_minus_gap = QPushButton("<<< Letras salen antes (-50ms)")
        self.btn_minus_gap.clicked.connect(lambda: self.adjust_gap(-50))
        
        self.lbl_gap = QLabel(f"Desfase (GAP): {self.gap_ms} ms")
        self.lbl_gap.setAlignment(Qt.AlignCenter)
        self.lbl_gap.setStyleSheet("font-weight: bold; font-size: 16px;")
        
        self.btn_plus_gap = QPushButton("Letras salen despues (+50ms) >>>")
        self.btn_plus_gap.clicked.connect(lambda: self.adjust_gap(50))
        
        gap_controls_layout.addWidget(self.btn_minus_gap)
        gap_controls_layout.addWidget(self.lbl_gap)
        gap_controls_layout.addWidget(self.btn_plus_gap)
        
        # Visual Lyrics Track Slider
        self.gap_slider = QSlider(Qt.Horizontal)
        self.gap_slider.setMinimum(-10000) # -10 seconds max shift
        self.gap_slider.setMaximum(10000)  # +10 seconds max shift
        self.gap_slider.setValue(int(self.gap_ms))
        self.gap_slider.sliderMoved.connect(self.slider_adjust_gap)
        self.gap_slider.setStyleSheet("QSlider::handle:horizontal { background: #ffaa00; width: 15px; }")
        
        slider_label = QLabel("Mover toda la pista de Letras (Izquierda/Derecha):")
        
        gap_layout.addWidget(slider_label)
        gap_layout.addWidget(self.gap_slider)
        gap_layout.addLayout(gap_controls_layout)
        
        self.btn_save = QPushButton("Guardar Cambios de Sincronización")
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
            reply = QMessageBox.question(self, 'Cambios sin guardar',
                                        '¿Deseas guardar los cambios de sincronización antes de salir?',
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
            self.audio_player.play()
            self.video_player.play()
            
    def seek(self, position):
        self.audio_player.setPosition(position)
        # Ultrastar videos usually have a VIDEOGAP offset, but we can just sync them 1:1 for the editor
        self.video_player.setPosition(position)
        
    def update_slider(self, position):
        if not self.slider.isSliderDown():
            self.slider.setValue(position)
            
    def adjust_gap(self, amount):
        self.gap_ms += amount
        self.lbl_gap.setText(f"Desfase (GAP): {self.gap_ms} ms")
        self.gap_slider.blockSignals(True)
        self.gap_slider.setValue(int(self.gap_ms))
        self.gap_slider.blockSignals(False)
        
    def slider_adjust_gap(self, value):
        self.gap_ms = float(value)
        self.lbl_gap.setText(f"Desfase (GAP): {self.gap_ms} ms")
        


    def update_lyrics(self):
        pos_s = self.audio_player.position() / 1000.0
        gap_s = self.gap_ms / 1000.0
        
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
                prev_text = "".join(note[4].replace('~', '') for note in prev_line)
                display_html += f"<span style='color: #aaaaaa; font-size: 18px;'>{prev_text}</span><br>"
            else:
                display_html += "<span style='font-size: 18px;'>&nbsp;</span><br>"
                
            # Current Line
            curr_line = self.lines[active_index]
            curr_text = ""
            for note in curr_line:
                n_start = float(note[1]) * 60 / self.bpm / 4 + gap_s
                lyric = note[4].replace('~', '')
                if pos_s >= n_start:
                    curr_text += f"<span style='color: #00ff00; font-size: 26px; font-weight: bold;'>{lyric}</span>"
                else:
                    curr_text += f"<span style='color: #ffffff; font-size: 26px; font-weight: bold;'>{lyric}</span>"
            display_html += f"{curr_text}<br>"
            
            # Next Line
            if active_index < len(self.lines) - 1:
                next_line = self.lines[active_index + 1]
                next_text = "".join(note[4].replace('~', '') for note in next_line)
                display_html += f"<span style='color: #aaaaaa; font-size: 18px;'>{next_text}</span>"
            else:
                display_html += "<span style='font-size: 18px;'>&nbsp;</span>"
                
            self.lyrics_display.setText(f"<div align='center'>{display_html}</div>")
        else:
            self.lyrics_display.setText("")

    def save_gap(self):
        try:
            with open(self.txt_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            with open(self.txt_path, 'w', encoding='utf-8') as f:
                gap_found = False
                for line in lines:
                    if line.startswith("#GAP:"):
                        f.write(f"#GAP:{int(self.gap_ms)}\n")
                        gap_found = True
                    else:
                        f.write(line)
                
                if not gap_found:
                    pass
                    
            print(f"Saved new GAP: {self.gap_ms}")
            self.original_gap_ms = self.gap_ms  # Prevent unsaved changes prompt on app exit
            self.accept()
        except Exception as e:
            print(f"Error saving: {e}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    if len(sys.argv) > 1:
        dialog = SyncEditorDialog(sys.argv[1])
        dialog.exec()
