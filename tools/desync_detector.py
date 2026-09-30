import os
import re
import yaml
import tempfile
import subprocess
import crepe
from scipy.io import wavfile

# Load config
try:
    with open("config.yml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        input_folder = config.get("folders", {}).get("input", "")
except:
    input_folder = ""

if not input_folder or not os.path.isdir(input_folder):
    print("❌ Directorio Input no encontrado. Ejecuta la herramienta desde el directorio principal o verifica config.yml.")
    exit(1)

print(f"🔍 Iniciando Detector de Desync IA en: {input_folder}")

def parse_txt(txt_path):
    bpm = None
    gap = 0.0
    first_note_start = None
    mp3_file = None
    
    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#MP3:"):
                mp3_file = line.split(":", 1)[1].strip()
            elif line.startswith("#BPM:"):
                bpm = float(line.split(":", 1)[1].strip().replace(',', '.'))
            elif line.startswith("#GAP:"):
                gap = float(line.split(":", 1)[1].strip().replace(',', '.')) / 1000.0
            elif line.startswith(":") or line.startswith("*") or line.startswith("F"):
                if first_note_start is None:
                    # e.g., : 116 2 24  ma
                    parts = line.split()
                    if len(parts) >= 2:
                        first_note_start = float(parts[1])
    
    return mp3_file, bpm, gap, first_note_start

# Iterate over all folders in input
report_lines = ["# 🎤 Reporte Automático de Desincronización (IA)", ""]
desync_count = 0
total_processed = 0

for root, _, files in os.walk(input_folder):
    for file in files:
        if file.lower().endswith(".txt"):
            txt_path = os.path.join(root, file)
            mp3_file, bpm, gap, first_note_start = parse_txt(txt_path)
            
            if mp3_file is None or bpm is None or first_note_start is None:
                continue
                
            audio_path = os.path.join(root, mp3_file)
            if not os.path.exists(audio_path):
                continue
            
            total_processed += 1
            print(f"\n🎧 Analizando: {file}")
            
            # 1. Theoretical Start (UltraStar)
            theoretical_start = (first_note_start * 60) / (bpm * 4) + gap
            
            # 2. Extract Vocals using Demucs
            with tempfile.TemporaryDirectory() as tmpdir:
                print("   Separando voz con Demucs...")
                # We use -n htdemucs --two-stems vocals to be fast
                subprocess.run([
                    "python", "-m", "demucs", "-n", "htdemucs", 
                    "--two-stems", "vocals", "-o", tmpdir, audio_path
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                vocals_path = os.path.join(tmpdir, "htdemucs", os.path.splitext(mp3_file)[0], "vocals.wav")
                if not os.path.exists(vocals_path):
                    print("   ⚠️ Error al aislar voz. Saltando...")
                    continue
                
                # 3. Analyze Pitch with CREPE to find first confident vocal frame
                print("   Buscando el primer instante cantado con CREPE...")
                sr, audio = wavfile.read(vocals_path)
                # Ensure mono
                if len(audio.shape) > 1:
                    audio = audio.mean(axis=1)
                
                # We only need the first 60 seconds at most to find the first note
                max_samples = sr * 60
                if len(audio) > max_samples:
                    audio = audio[:max_samples]
                    
                time, frequency, confidence, activation = crepe.predict(audio, sr, viterbi=False, step_size=10, model_capacity="tiny")
                
                # Find first frame where confidence is > 0.6
                actual_start = None
                for i, conf in enumerate(confidence):
                    if conf > 0.6:
                        actual_start = time[i]
                        break
                
                if actual_start is None:
                    print("   ⚠️ No se detectó voz clara en los primeros 60s.")
                    continue
                    
                # 4. Compare
                diff = actual_start - theoretical_start
                diff_ms = int(diff * 1000)
                
                print(f"   Teórico: {theoretical_start:.3f}s | Real: {actual_start:.3f}s | Desfase: {diff_ms}ms")
                
                # Flag if diff > 300ms
                if abs(diff_ms) > 300:
                    status = "🔴 DESFASADA"
                    desync_count += 1
                    report_lines.append(f"- **{file}**")
                    report_lines.append(f"  - **Teórico (TXT):** {theoretical_start:.3f}s")
                    report_lines.append(f"  - **Voz Real (IA):** {actual_start:.3f}s")
                    report_lines.append(f"  - **Diferencia:** `{diff_ms}ms` ({'Atrasada' if diff_ms > 0 else 'Adelantada'})")
                else:
                    status = "🟢 OK"
                
                print(f"   Estado: {status}")

report_lines.insert(2, f"**Resumen:** Se analizaron {total_processed} canciones. Se encontraron {desync_count} canciones con más de 300ms de desfase.\n")

with open("reporte_desync.md", "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))

print(f"\n✅ Análisis completado. Reporte guardado en reporte_desync.md")
