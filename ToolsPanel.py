"""Library maintenance tools of the advanced options: runs the scripts of tools/ in a separate process, one at a time.

Every tool runs as its own process (the window never freezes and, if a tool runs out of memory, only that tool
dies). On Linux the heavy ones run under systemd-run with a memory limit. The tools only list by default; they
change the song folders only when "Apply the changes" is checked. Converted videos (.bk2) are never touched.
"""
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from typing import List, Tuple

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
                               QWidget)

import GuiElement
from ConfigLoader import bundle_dir
from i18n import tr

Icon = GuiElement.Icon
MAX_LOG_LINES = 20000
HEAVY_MEMORY = '6G'  # Demucs needs ~3 GB per song; the limit keeps the rest of the PC alive
HEAVY_MIN_FREE_GB = 4


@dataclass
class Option:
    flag: str
    label: str
    default: bool = False
    tooltip: str = ''


@dataclass
class Task:
    key: str
    label: str
    description: str
    duration: str
    target: str = 'songs'                # 'songs' (input folder) or 'patch' (output/<DLC id>)
    options: List[Option] = field(default_factory=list)
    needs_extracted: str = ''            # '' | 'optional' | 'required'
    heavy: bool = False
    needs: Tuple[str, ...] = ()          # programs that must exist (e.g. kioclient)
    changes_songs: bool = False          # rescan the song table when it ends


APPLY = Option('--apply', "Apply the changes (unchecked: only lists what would change)",
               tooltip="A .bak of every txt is kept before it is changed.")

TASKS = [
    Task('validate_patch', "Check the patch before copying it to the console",
         "Checks every song of the converted patch: audio, preview, cover, video (.bk2) and lyrics present, IDs "
         "unique, values the game knows. Only reads.",
         "About a minute.", target='patch'),
    Task('switch_update', "Update the patch on the Switch (MTP, DBI)",
         "Copies to the Switch only the files that changed, over MTP (DBI's MTP responder must be open). Every file "
         "replaced on the Switch is saved first to switch_backup_<date> next to the output folder. The song list "
         "(songs_xx.json) is copied last, so if the cable comes out the console keeps the previous complete patch; "
         "run it again to continue. The patch is checked first.",
         "Seconds for a few songs; hours if the whole patch changed (~30 GB at 3-10 MB/s).", target='patch',
         options=[APPLY, Option('--prune', "Remove from the Switch the files of songs no longer in the patch",
                                tooltip="Only after everything was copied; they are saved to the backup first.")],
         needs=('kioclient',)),
    Task('sync_scan', "Check the timing of every song against the voice",
         "Separates the voice of every song (Demucs) and compares it with the lyrics line by line. Writes "
         "informe_sincronia.csv next to the songs folder and fills the Sync column (ok / partial / desync / "
         "doubtful). The voice of each song is kept, so a second run only takes minutes and stopping it loses "
         "nothing. Songs with an official vxla are not checked (their timing is the game's).",
         "Hours: 3-4 minutes per song not yet analyzed. Uses a lot of memory: do not convert at the same time.",
         options=[Option('--only-analyzed', "Only songs already analyzed (minutes)")], heavy=True,
         changes_songs=True),
    Task('usdb_sources', "List USDB songs whose audio comes from another video",
         "The USDB syncer sometimes downloads another upload of the song when it cannot get the one the lyrics were "
         "timed with: the lyrics then come early or late. Lists them with both links. Only reads.",
         "Seconds."),
    Task('fix_covers', "Fix shared or bad covers (internet)",
         "Gives its own cover to songs that share the same image with others: the USDB cover, the official cover "
         "of the extracted games or the single/album cover of the iTunes store (never compilations). The old image "
         "is kept.", "Minutes (one store search every few seconds).",
         options=[APPLY, Option('--frames', "Also replace covers taken from a video frame"),
                  Option('--blank', "Also replace plain covers (one colour)")],
         needs_extracted='optional', changes_songs=True),
    Task('fix_years', "Fix placeholder years (2020) of songs rebuilt from DLCs (internet)",
         "Looks for the real year in the official data of the extracted games, then MusicBrainz and the iTunes "
         "store (only when title and artist match).", "Minutes.", options=[APPLY], needs_extracted='required',
         changes_songs=True),
    Task('fix_genres', "Add the genre to songs without #GENRE (internet)",
         "Without #GENRE every song is Pop in the game. Takes the genre of the iTunes store when artist and title "
         "match exactly; songs that already have #GENRE are never changed.",
         "About 3 seconds per song without genre.", options=[APPLY], changes_songs=True),
    Task('usdb_restore_names', "Give USDB songs back the file names of usdb_syncer",
         "Older scripts renamed the audio, video and cover of USDB songs to generic names (audio.ogg, video.mp4, "
         "cover.png): usdb_syncer then thinks its files are missing and could write its video over one cut by hand. "
         "Renames them back to \"Artist - Title\" names, points the txt to them and updates the .usdb file. Only "
         "renames: nothing is converted again.", "Seconds.", options=[APPLY], changes_songs=True),
    Task('clean_song_folders', "Remove leftovers from the song folders",
         "Deletes ffmpeg logs, voice separation leftovers, half-written files, the .avi intermediate of finished "
         "videos, covers and audio the txt no longer uses and .bk2 files that are an identical copy of the song's "
         ".bk2. Never touches the txt, the .usdb, the files the txt uses (your videos included) nor the song's .bk2.",
         "Seconds.", options=[APPLY, Option('--bak', "Also delete the .bak copies of the txt files")],
         changes_songs=True),
    Task('artist_genders', "Find whether each singer is a man or a woman (internet)",
         "Asks MusicBrainz for every artist and writes _artist_genders.json in the songs folder, used by the "
         "singer filter of Let's Sing 2026. Groups and anything not certain stay Both. Already known artists are "
         "not asked again.", "About 1-2 seconds per new artist.", changes_songs=True),
]


def frozen():
    return getattr(sys, 'frozen', False)


def tool_command(key, args):
    """Program and arguments that run tools/<key>.py."""
    if frozen():
        return sys.executable, ['--tool', key, *args]
    return sys.executable, ['-u', str(bundle_dir() / 'tools' / f'{key}.py'), *args]


def available_memory_gb():
    try:
        with open('/proc/meminfo', encoding='ascii') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) / 1024 / 1024
    except (OSError, ValueError):
        pass
    return None


def demucs_installed():
    import importlib.util
    return not frozen() and importlib.util.find_spec('demucs') is not None


class ToolRunWindow(QDialog):
    """Live output of the tools started from the panel (it can be closed and opened again while they run)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.resize(900, 560)
        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(MAX_LOG_LINES)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.text)
        buttons = QHBoxLayout()
        self.stop_button = QPushButton(Icon.STOP.get_icon(), tr("Stop"))
        buttons.addWidget(self.stop_button)
        buttons.addStretch()
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.hide)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def append(self, text):
        self.text.appendPlainText(text)


class ToolsPanel(QGroupBox):
    """"5. Advanced options: library tools" of the left panel."""

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.process = None
        self.steps: List[Tuple[str, list, bool]] = []
        self.current = None
        self.unit = None
        self.started = 0.0
        self.stopped = False
        self._partial = ''
        self.window = ToolRunWindow(main)
        self.window.stop_button.clicked.connect(self.stop)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_status)

        main.t(self.setTitle, "5. Advanced options: library tools")
        main.t(self.setToolTip, "Long maintenance tasks (minutes to hours). They run in the background, one at a "
                                "time; the song folders change only when \"Apply the changes\" is checked.")
        layout = QVBoxLayout()
        self.combo = QComboBox()
        for task in TASKS:
            self.combo.addItem(tr(task.label), task.key)
        main._texts.append((lambda _t: [self.combo.setItemText(i, tr(t.label)) for i, t in enumerate(TASKS)], ''))
        self.combo.currentIndexChanged.connect(self.show_task)
        layout.addWidget(self.combo)
        self.description = QLabel()
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        self.duration = QLabel()
        self.duration.setWordWrap(True)
        layout.addWidget(self.duration)
        self.options_box = QVBoxLayout()
        layout.addLayout(self.options_box)
        self.option_checks: List[Tuple[Option, QCheckBox]] = []

        extracted = QGridLayout()
        self.extracted_label = QLabel()
        main.t(self.extracted_label.setText, "Extracted games:")
        extracted.addWidget(self.extracted_label, 0, 0)
        self.extracted_path = QLineEdit(str(main.settings.value("tools/extracted", "") or ""))
        main.t(self.extracted_path.setToolTip, "Folder with the games and DLCs extracted with LetSing_ExtractorPro "
                                               "(official covers and years).")
        self.extracted_path.editingFinished.connect(
            lambda: main.settings.setValue("tools/extracted", self.extracted_path.text().strip()))
        extracted.addWidget(self.extracted_path, 0, 1)
        browse = QPushButton("...")
        browse.setMaximumWidth(40)
        browse.clicked.connect(self.browse_extracted)
        extracted.addWidget(browse, 0, 2)
        extracted.setColumnStretch(1, 1)
        self.extracted_widget = QWidget()
        self.extracted_widget.setLayout(extracted)
        extracted.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.extracted_widget)

        run_layout = QHBoxLayout()
        self.run_button = QPushButton(Icon.START.get_icon(), "")
        main.t(self.run_button.setText, "Run")
        self.run_button.clicked.connect(self.run_selected)
        run_layout.addWidget(self.run_button)
        self.show_button = QPushButton()
        main.t(self.show_button.setText, "Show progress")
        self.show_button.clicked.connect(self.show_window)
        run_layout.addWidget(self.show_button)
        run_layout.addStretch()
        layout.addLayout(run_layout)
        self.state_label = QLabel()
        self.state_label.setWordWrap(True)
        layout.addWidget(self.state_label)
        self.setLayout(layout)
        main._texts.append((lambda _t: self.show_task(), ''))
        self.show_task()

    # ------------------------------------------------------------------ panel
    def task(self) -> Task:
        return TASKS[max(0, self.combo.currentIndex())]

    def show_task(self, *_):
        task = self.task()
        self.description.setText(tr(task.description))
        self.duration.setText(tr("Time: {duration}").format(duration=tr(task.duration)))
        while self.options_box.count():
            w = self.options_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.option_checks = []
        for option in task.options:
            check = QCheckBox(tr(option.label))
            check.setChecked(option.default)
            if option.tooltip:
                check.setToolTip(tr(option.tooltip))
            self.options_box.addWidget(check)
            self.option_checks.append((option, check))
        self.extracted_widget.setVisible(bool(task.needs_extracted))
        problem = self.unavailable(task)
        self.run_button.setToolTip(problem or "")
        self.update_buttons()

    def unavailable(self, task):
        for program in task.needs:
            if not shutil.which(program):
                return tr("Needs {program} (KDE, Linux).").format(program=program)
        if task.key == 'sync_scan' and not demucs_installed():
            return tr("Needs the program running from its source folder with Demucs installed "
                      "(pip install demucs).")
        return ''

    def running(self):
        return self.process is not None

    def update_buttons(self):
        busy = self.running() or self.main.conversion_running
        self.run_button.setEnabled(not busy and not self.unavailable(self.task()))
        self.show_button.setEnabled(self.running() or bool(self.window.text.toPlainText()))

    def browse_extracted(self):
        folder = QFileDialog.getExistingDirectory(self, tr("Select folder"), self.extracted_path.text().strip())
        if folder:
            self.extracted_path.setText(os.path.normpath(folder))
            self.main.settings.setValue("tools/extracted", self.extracted_path.text())

    def show_window(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    # ------------------------------------------------------------------ run
    def target_path(self, task):
        songs = os.path.normpath(self.main.input_path.text().strip() or '.')
        if task.target == 'songs':
            return songs if songs != '.' and os.path.isdir(songs) else None
        output = self.main.output_path.text().strip()
        dlc_id = self.main.dlc_id_input.text().strip()
        patch = os.path.join(output, dlc_id) if output and dlc_id else ''
        return patch if os.path.isdir(os.path.join(patch, 'romfs')) else None

    def run_selected(self):
        task = self.task()
        if self.running() or self.main.conversion_running:
            return
        target = self.target_path(task)
        if not target:
            QMessageBox.warning(self, tr(task.label),
                                tr("Choose the input folder with your songs first.") if task.target == 'songs' else
                                tr("There is no converted patch for this DLC in the output folder. Convert first."))
            return
        args = [target]
        options = [o.flag for o, check in self.option_checks if check.isChecked()]
        extracted = self.extracted_path.text().strip()
        if task.needs_extracted:
            if extracted and not os.path.isdir(extracted):
                QMessageBox.warning(self, tr(task.label), tr("The extracted games folder does not exist."))
                return
            if task.needs_extracted == 'required' and not extracted:
                QMessageBox.warning(self, tr(task.label), tr("Choose the extracted games folder first."))
                return
            if extracted:
                args += ['--extracted', extracted]
        if task.key == 'sync_scan':
            args += ['--report', os.path.join(os.path.dirname(target), 'informe_sincronia.csv'), '--jobs', '1']
        args += options

        warnings = []
        if task.heavy:
            free = available_memory_gb()
            if free is not None and free < HEAVY_MIN_FREE_GB:
                warnings.append(tr("Only {free:.1f} GB of memory are free; close other programs first or the analysis "
                                   "may stop.").format(free=free))
        if '--apply' in options or task.heavy or task.key == 'artist_genders':
            warnings.append(tr("Time: {duration}").format(duration=tr(task.duration)))
        if task.key == 'switch_update' and '--apply' in options:
            warnings.append(tr("Keep the Switch connected with DBI's MTP responder open and do not let the PC sleep. "
                               "If it disconnects, run it again: it continues where it stopped."))
        if warnings:
            answer = QMessageBox.question(self, tr(task.label), "\n\n".join(warnings + [tr("Start now?")]),
                                          QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if answer != QMessageBox.Yes:
                return

        self.steps = []
        if task.key == 'switch_update' and '--apply' in options:
            self.steps.append(('validate_patch', [target], False))
        self.steps.append((task.key, args, task.heavy))
        self.current = task
        self.stopped = False
        self.window.text.clear()
        self.window.setWindowTitle(tr(task.label))
        self.started = time.monotonic()
        self.timer.start()
        self.show_window()
        self.next_step()
        self.main.on_tool_state_changed()

    def run_tool(self, key, args, title, changes_songs=True):
        """Runs one tool that is not in the list (e.g. align_video from the song table) with the same window."""
        if self.running() or self.main.conversion_running:
            return False
        self.steps = [(key, list(args), False)]
        self.current = Task(key, title, '', '', changes_songs=changes_songs)
        self.stopped = False
        self.window.text.clear()
        self.window.setWindowTitle(tr(title))
        self.started = time.monotonic()
        self.timer.start()
        self.show_window()
        self.next_step()
        self.main.on_tool_state_changed()
        return True

    def next_step(self):
        key, args, heavy = self.steps.pop(0)
        program, arguments = tool_command(key, args)
        self.unit = None
        if heavy and sys.platform.startswith('linux') and shutil.which('systemd-run'):
            self.unit = f"letssing-tool-{os.getpid()}-{int(time.time())}"
            arguments = ['--user', '--scope', '--quiet', f'--unit={self.unit}', '-p', f'MemoryMax={HEAVY_MEMORY}',
                         program, *arguments]
            program = 'systemd-run'
        process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert('PYTHONUNBUFFERED', '1')
        env.insert('PYTHONIOENCODING', 'utf-8')
        process.setProcessEnvironment(env)
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.setWorkingDirectory(str(bundle_dir()))
        process.readyReadStandardOutput.connect(self.read_output)
        process.finished.connect(self.step_finished)
        process.errorOccurred.connect(self.step_error)
        self.process = process
        self.window.append(f"$ {key} {' '.join(args)}")
        process.start(program, arguments)

    def read_output(self):
        if not self.process:
            return
        data = self._partial + bytes(self.process.readAllStandardOutput()).decode('utf-8', 'replace')
        lines = data.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        self._partial = lines.pop()
        for line in lines:
            self.window.append(line)

    def step_error(self, error):
        if error == QProcess.FailedToStart:
            self.window.append(tr("Could not start the tool: {error}").format(error=self.process.errorString()))
            self.step_finished(-1, QProcess.CrashExit)

    def step_finished(self, code, _status=None):
        if self.process is None:
            return
        self.read_output()
        if self._partial:
            self.window.append(self._partial)
            self._partial = ''
        self.process.deleteLater()
        self.process = None
        if code == 0 and self.steps and not self.stopped:
            self.next_step()
            return
        self.steps = []
        self.timer.stop()
        elapsed = self.elapsed()
        if self.stopped:
            message = tr("Stopped after {elapsed}. Running it again continues where it stopped.").format(elapsed=elapsed)
        elif code == 0:
            message = tr("Finished in {elapsed}.").format(elapsed=elapsed)
        else:
            message = tr("Ended with errors (code {code}) after {elapsed}. See the messages above.").format(
                code=code, elapsed=elapsed)
        self.window.append("\n=== " + message)
        self.window.status.setText(message)
        self.state_label.setText(f"{tr(self.current.label)}: {message}")
        if self.current.changes_songs:
            self.main.scan_input_folder()
        self.main.on_tool_state_changed()

    def stop(self):
        if not self.process:
            return
        self.stopped = True
        self.steps = []
        if self.unit:  # the scope also holds the Demucs processes the tool started
            QProcess.execute('systemctl', ['--user', 'kill', '--signal=SIGTERM', f'{self.unit}.scope'])
        self.process.terminate()
        if not self.process.waitForFinished(5000):
            self.process.kill()

    def elapsed(self):
        seconds = int(time.monotonic() - self.started)
        return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"

    def update_status(self):
        text = tr("{task} running for {elapsed}...").format(task=tr(self.current.label), elapsed=self.elapsed())
        self.window.status.setText(text)
        self.state_label.setText(text)
