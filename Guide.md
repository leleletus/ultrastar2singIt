## Let's Sing UltraStar Converter
<p>This tool helps you add custom songs to an installed DLC for Let's Sing (tested on 2022 and 2025, might not work on earlier versions). It converts UltraStar karaoke files (found on a well-known Spanish UltraStar site) to the Let's Sing DLC format.</p>

### How to use
<ol>
<li>Install Let's Sing on your console and install one DLC song pack.</li> 
<li>Download a FFmpeg release to your PC. I used gyan's release from <a href="https://www.gyan.dev/ffmpeg/builds/">https://www.gyan.dev/ffmpeg/builds/</a>.</li>
<li>Install RAD Video Tools from <a href="https://www.radgametools.com/bnkdown.htm">https://www.radgametools.com/bnkdown.htm</a> (needed for Let's Sing 2024 and onward, skip for earlier versions).</li>
<li>Create a folder (e.g., "My Songs") containing all the UltraStar song folders you want to convert. This is what your "My Songs" folder should look like:

```
My Songs/
├── Oasis - Wonderwall/
│   ├── Oasis - Wonderwall.aac
│   ├── Oasis - Wonderwall.png
│   ├── Oasis - Wonderwall.txt
│   └── Oasis - Wonderwall.webm
├── R.E.M. - Man on the Moon/
│   ├── R.E.M. - Man on the Moon.jpeg
│   ├── R.E.M. - Man on the Moon.mkv
│   ├── R.E.M. - Man on the Moon.ogg
│   └── R.E.M. - Man on the Moon.txt
└── Scatman John - Scatman (Ski-Ba-Bop-Ba-Dop-Bop)/
    ├── Scatman John - Scatman (Ski-Ba-Bop-Ba-Dop-Bop).jpg
    ├── Scatman John - Scatman (Ski-Ba-Bop-Ba-Dop-Bop).mp3
    ├── Scatman John - Scatman (Ski-Ba-Bop-Ba-Dop-Bop).mp4
    └── Scatman John - Scatman (Ski-Ba-Bop-Ba-Dop-Bop).txt
```
</li>
<li>Run the 'Let's Sing UltraStar Converter' and fill in your game and dlc versions.<br>If your game/DLC versions aren't listed, choose 'other' and manually fill out the fields.
 If your base game is 2024 or newer, you will need to fill the 'DLC JSON Name' field as well. This name can be found in the name.txt file located in [DLC TITLEID]/romfs/name.txt,
 use DBI to browse the installed game folders.</li>
<li>If FFmpeg or RAD Video Tools fields are empty, point them to the executables for FFmpeg and RAD Video Tools, respectively</li>
<li>Point the Input folder to your "My Songs" folder.</li>
<li>Check the preview on the right to make sure your Input folder is loaded correctly. Green ticks will be displayed for each existing UltraStar file type (or a red X if it is missing).
 If you've run the converter before with your input folder, a blue checked-file icon may also appear next to the first icon.
 This icon means that a cached version of this file type is already present in the input song's folder (you can delete these by using the Clear cache button).</li>
<li>Select an output folder for the converted songs. <b>WARNING</b> - The selected folder will be purged before starting the conversion, make sure you're not selecting an important folder!
 There are some guardrails put in place to prevent deleting something important, the contents of the selected folder are checked upon selection.
 The selected folder will be allowed only if it is empty or if it contains only folders named as Title IDs (i.e., from a previous conversion), but still be careful.</li>
<li>Start the conversion and track the progress in the preview table above.</li>
<li>When the conversion is done, copy the contents of the output folder to your SD card sd:/atmosphere/contents.</li>
<li>Launch the game and Sing!</li>
</ol>

### Tweaks
<ul>
<li><i>Include songs from the DLC</i> - By default, the songs from the DLC are ignored and won't be visible in the game.
 If you want to include them, check this box and point to the required files from the installed CORE/DLC.</li>
<li><i>Analyze song vocals for pitch correction</i> - Let's Sing recognizes vocal pitches in the 43-81 range.
 Most UltraStar files use relative pitch ranges and have values in the low 10s or even negative, so some form of pitch correction is required for them.
 By default, simple calculations are used to raise the pitch to the correct range.
 Check this box to use the <a href="https://github.com/marl/crepe">CREPE module</a> for a potentially more accurate pitch correction (takes around 10 seconds longer per song).
 Note: this option requires you to unpack the numpy, librosa and crepe modules into the plugins folder.</li>
<li><i>Use cover image instead of video</i> - Check this box to skip the lengthy encoding of videos, the cover image will be used to create a static video instead.
 This will dramatically speed up the conversion and reduce the final size of the patch.</li>
<li><i>Ignore the UltraStar medley tags for finding chorus sections</i> - Chorus sections of a song will award more points, but finding the choruses can be tricky.
 The UltraStar txt files sometimes contain medley tags which point to a single chorus section. If the tags are present, they will be used to find all the choruses.
 If the tags are missing, the chorus data will be scraped from genius.com, and failing this, a manual chorus lookup method will be used.
 The medley tags offer the simplest way of finding the chorus sections, but they are sometimes incorrect. Check this box if you want to use the other methods instead.</li>
</ul>
### Advanced options: library tools
Section 5 of the left panel runs long maintenance tasks in the background, one at a time (no conversion while one runs).
Pick a task, read its description and estimated time, then press <i>Run</i>; <i>Show progress</i> opens its live output.
Tools that change your song folders only list what they would do until <i>Apply the changes</i> is checked (a .bak of
every txt is kept). Converted .bk2 videos are never touched. Stopping a task loses nothing: running it again continues.
<ul>
<li><i>Check the patch</i> - checks every song of the converted patch before you copy it (seconds).</li>
<li><i>Update the patch on the Switch</i> - copies only the changed files over MTP (Linux with KDE, DBI's MTP responder open).
 Files replaced on the Switch are backed up first; the song list is copied last, so a disconnection never leaves a broken patch.</li>
<li><i>Check the timing of every song against the voice</i> - separates the voice (Demucs) and compares it with the lyrics;
 fills the Sync column and writes informe_sincronia.csv. Hours the first time (3-4 min per song), minutes afterwards.
 Needs a lot of memory: on Linux it runs with a 6 GB limit so the rest of the PC keeps working.</li>
<li><i>List USDB songs whose audio comes from another video</i>, <i>Fix covers</i>, <i>Fix years</i>, <i>Add genres</i>,
 <i>Find singers' gender</i> - metadata fixes from the extracted games, USDB, MusicBrainz and the iTunes store (internet).</li>
</ul>

### Songs downloaded with usdb_syncer
Point usdb_syncer's song folder and this program's input folder to the same folder. Downloaded songs are recognized as they are
("Artist - Title" folders with their .txt, audio, video, [CO] cover and .usdb file). Downloading a song again in usdb_syncer
rewrites its txt (fixes made here or in the Sync Editor are lost for that song) and may rename its folder; the converted .bk2 is
reused after such a rename.

### A song shows its cover instead of its video
Songs converted before they had a video got the still cover as their .bk2 (an orange triangle in the Video column; they are
listed with <i>Only problems</i>). Put the song's video in its folder, named like the folder (e.g. "Artist - Title.mp4"), and
convert the song: when the converted .bk2 is the still cover and the folder has a real video, the old .bk2 is moved (never
deleted) to _replaced_videos next to the songs folder and the video is encoded. Any other converted .bk2 is never encoded again.
Right click > <i>Encode the video again from its source</i> forces it for one song.
Right click > <i>Add a video (file or link)</i> takes a YouTube link or a video file, compares its sound with the song, cuts it at the
right second and saves it as "Artist - Title.mp4" in the song folder (nothing is saved if it is another version of the song or a still image).
