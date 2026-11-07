"""Report of the songs made by SongMaker: how well their notes fit the singer's voice and what to fix by hand
(changes nothing). For each song and each kept version of its txt (e.g. the first one made, the previous one, the
current one) it measures:

    coincidencia  how much of the note time has voice under it, counting double when the pitch is right (the sync
                  editor's line score)
    voz           part of the note time with voice under it
    tono          part of the sung note time (where the voice has a clear pitch) within 1 semitone (any octave)
    desfase       lines whose voice is 0.3 s or more away (they would move in the sync editor's "Fit to voice"),
                  and the song's verdict (ok / desfase / parcial / otra_version / dudosa)
    inicio / fin  first note against the first voice, last note against the end of the audio
    estilo        notes shorter than 0.12 s, jumps of 5+ semitones, zigzag, range (tools/note_style.py)

and, for the current version, how each line's syllables were placed (speech model or voice onsets) and the lines
to check: out of time, little voice under the notes (maybe not sung), syllables placed with little confidence, rap.

Usage:
    python tools/songmaker_report.py <songs folder> --md informe.md [--version "original=<folder>" ...] [--calibrate]

--version: a folder with an old txt of each song (<folder>/<song folder>/<txt>, as tools/remake_notes.py keeps
them), shown next to the current one; the first one given is compared with the current one in the summary.
"""
import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import SongMaker  # noqa: E402
import SyncModel  # noqa: E402
import UltrastarToSingit  # noqa: E402
import VoiceAlign  # noqa: E402
import naming  # noqa: E402
from align_voices import audio_of  # noqa: E402
from note_style import stats, txt_notes  # noqa: E402

FRAME = SyncModel.FRAME
OUT_S = 0.3        # a line whose voice is this far away "would move"; alone it is noise: official songs get 16 %
QUIET = 0.15       # a line with less than this of its notes on the voice (official songs: 9 % of their lines)
MODEL_SHARE = 0.75  # under this share of lines recognised by the speech model the whole song is flagged
UNSURE = -6.0      # model confidence (mean log-probability of the letters) under which a line is checked: on the
                   # official songs 35 % of the syllables of those lines are 0.3 s off, 3 % of the others


def mmss(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def current_txt(folder):
    txts = sorted(p for p in folder.glob('*.txt'))
    named = folder / f"{folder.name}.txt"
    return named if named.exists() else (txts[0] if txts else None)


def load(txt, folder):
    """(song, seconds added to its notes) as they play over the song's own audio file (no #START in SongMaker)."""
    data = UltrastarToSingit.parse_file(txt)
    song = SyncModel.load_txt(data)
    gap = float(data.get('GAP', '0').replace(',', '.') or 0) / 1000
    meta = {}
    nid = naming.construct_name_id_from_directory_name(folder.name.rstrip('.'))
    try:
        meta = json.loads((folder / (nid + naming.AUDIO_META_SUFFIX)).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    return song, gap - (float(meta.get('lyrics_offset') or 0) - float(meta.get('trim_start') or 0))


def line_text(song, i):
    return ''.join(song.syllables[k][2] for k in song.lines[i]).replace('~', '').strip()


def measure(txt, folder, voice, duration):
    song, shift = load(txt, folder)
    if not song.notes:
        return None
    active, pitch = voice['active'], voice['pitch']
    frames = len(active)
    on = time_total = 0.0
    right = pitched = 0
    for n in song.notes:
        a = int(round((n.t + shift) / FRAME))
        b = max(a + 1, int(round((n.t + n.d + shift) / FRAME)))
        idx = np.arange(max(0, a), min(frames, b))
        time_total += b - a
        if not len(idx):
            continue
        on += active[idx].sum()
        if n.sung:
            p = pitch[idx][active[idx] & ~np.isnan(pitch[idx])]
            pitched += len(p)
            right += int((np.abs(((p - n.pitch + 6) % 12) - 6) <= 1).sum())
    report = SyncModel.line_report(song, voice, lambda i: shift)
    starts = [s + shift for s in song.line_starts]
    lyrics_end = song.line_ends[-1] + shift if song.line_ends else 0.0
    verdict, detail = SyncModel.song_verdict(report, starts, duration, lyrics_end)
    scores = [r[0] for r in report if r[0] is not None]
    voiced = np.flatnonzero(active)
    first_voice = voiced[0] * FRAME if len(voiced) else 0.0
    style = stats(txt_notes(txt)) or {}
    rows, out = [], []
    for i, (now, extra, best) in enumerate(report):
        if now is None:
            continue
        rows.append((starts[i], now, extra, best - now, line_text(song, i)))
        if abs(extra) >= OUT_S:
            out.append(i)
    runs = SyncModel.runs_out_of_time(report, starts)
    return {
        'match': statistics.mean(scores) if scores else 0.0,
        'voice': on / max(1.0, time_total),
        'pitch': right / pitched if pitched else float('nan'),
        'out': out, 'rows': rows, 'runs': runs, 'verdict': verdict, 'detail': detail,
        'first_note': song.notes[0].t + shift, 'first_voice': first_voice,
        'end': lyrics_end, 'duration': duration,
        'short': style.get('short<0.12', float('nan')), 'jump5': style.get('jump>=5', float('nan')),
        'zigzag': style.get('zigzag', float('nan')), 'range': style.get('range', float('nan')),
        'notes': len(song.notes), 'lines': sum(1 for r in report if r[0] is not None),
        'rap': sum(1 for n in song.notes if not n.sung) / len(song.notes),
    }


def language_of(txt):
    for row in txt.read_text(encoding='utf-8', errors='replace').splitlines():
        if row.startswith('#LANGUAGE:'):
            return row.split(':', 1)[1].strip()
    return 'Spanish'


def placement(folder):
    """How the current notes placed each line (made again in memory, nothing written), or None."""
    meta = json.loads((folder / 'songmaker.json').read_text(encoding='utf-8'))
    if meta.get('lyrics'):  # whole lyrics placed by the speech model (Genius, or LRCLIB's text without its times)
        timed = json.loads((folder / SongMaker.LYRICS_FILE).read_text(encoding='utf-8'))['lines']
        lines, offset = [(t, text) for t, text, _ in timed], 0.0
    else:
        versions = {v[0]: v for v in SongMaker.lrclib_versions(None, None, folder)}
        if meta.get('lrclib_id') not in versions:
            return None
        lines, offset = versions[meta['lrclib_id']][2], meta['offset']
    voice = np.load(SyncModel.voice_cache_path(str(folder)))
    language = language_of(current_txt(folder))
    ctc = VoiceAlign.load_emissions(VoiceAlign.paths(str(folder))[1])
    info = []
    SongMaker.make_notes(lines, offset, voice['energy'].astype(np.float32),
                         voice['pitch'].astype(np.float32), language, ctc=ctc, report=info)
    return info, meta, ctc is not None


def pct(x):
    return '—' if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:.0f} %"


def arrow(values):
    return ' → '.join(pct(v) for v in values)


def song_section(name, rows, place, edited, checked=None):
    cur = rows[-1][1]
    out = [f"### {name}" + (" ✅" if checked else ''), ""]
    out.append("| versión | coincidencia | voz bajo las notas | tono ±1 | bloques desfasados | veredicto | notas cortas | "
               "saltos 5+ | rango |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    for label, m in rows:
        if m is None:
            continue
        out.append(f"| {label} | {pct(m['match'])} | {pct(m['voice'])} | {pct(m['pitch'])} | {len(m['runs'])} | "
                   f"{m['verdict']} {m['detail']} | {pct(m['short'])} | {pct(m['jump5'])} | {m['range']:.0f} |")
    out.append("")
    notes = []
    if checked:
        notes.append(f"**✅ revisada a oído por ti ({checked}): lista**")
    if edited:
        notes.append("corregida a mano en el editor (tiene `.bak`): no se rehizo")
    start_gap = cur['first_note'] - cur['first_voice']
    if abs(start_gap) > 1.5:
        notes.append(f"inicio: la primera nota está en {mmss(cur['first_note'])} y la voz empieza en "
                     f"{mmss(cur['first_voice'])} ({start_gap:+.1f} s; puede ser una intro hablada o coros)")
    if cur['end'] > cur['duration'] + 0.2:
        notes.append(f"fin: la letra termina {cur['end'] - cur['duration']:.1f} s después del audio")
    if cur['rap']:
        notes.append(f"rap: {pct(cur['rap'])} de las notas (comprobar que esas partes se rapean)")
    if place:
        info, meta, has_model = place
        by_model = sum(1 for x in info if x['placed'] == 'model')
        if info and by_model / len(info) < MODEL_SHARE:
            notes.append(f"**el modelo de habla solo reconoce {by_model / len(info):.0%} de las líneas** (en las oficiales, "
                         "98 %): rap muy rápido, mucho autotune o una letra de LRCLIB de otra versión del audio; "
                         "escucharla entera en el editor")
        notes.append(f"sílabas colocadas por el modelo de habla en {by_model} de {len(info)} líneas"
                     + ("" if has_model else " (sin modelo para esta canción)")
                     + ("; letra completa de Genius colocada por el modelo en toda la canción"
                        if meta.get('lyrics') == 'genius' else
                        "; letra de LRCLIB colocada por el modelo en toda la canción (sin sus tiempos)"
                        if meta.get('lyrics') else
                        f"; LRCLIB #{meta.get('lrclib_id')}, desfase {meta.get('offset', 0):+.2f} s".replace('.', ',')))
    for n in notes:
        out.append(f"- {n}")
    todo = [] if checked else to_check(cur, place)
    for level, title in ((1, "Revisar primero (casi seguro que hay algo mal):"),
                         (2, "Si al cantarla suena raro (el modelo no pudo colocar bien las sílabas; las del método "
                             "anterior fallan ~1 de cada 3):")):
        rows = [row for t, lv, row in sorted(todo) if lv == level]
        if rows:
            out += ["", title, ""] + rows
    out.append("")
    return out


def to_check(m, place):
    """[(time, level, markdown row)] of what to check (level 1: something is most likely wrong; 2: doubtful) by hand in a song, from the signals that hold on the official songs:
    a block of lines out of time, lines whose syllables the model could not place surely (with what the voice says
    of them: little voice under the notes = maybe not sung; their voice elsewhere = out of time)."""
    todo = []
    for t, shift, count in m['runs']:
        todo.append((t, 1, f"- [ ] **{mmss(t)}** {count} líneas seguidas desfasadas {shift * 1000:+.0f} ms → editor: "
                        f"«Inicio» (C) en la primera, flechas o «Ajustar a la voz» (A)"))
    if not place:
        return todo
    rows = m['rows']
    for x in place[0]:
        unsure = x['placed'] != 'model' or (x['sure'] is not None and x['sure'] < UNSURE)
        if not unsure or not rows:
            continue
        t, now, extra, gain, text = min(rows, key=lambda r: abs(r[0] - x['t']))
        level = 1
        if x['placed'] == 'even':
            why, fix = "no se encontró voz", "¿se canta? si no, Ctrl+Supr"
        elif now < QUIET:
            why, fix = f"casi sin voz bajo las notas ({pct(now)})", "¿se canta? si no, Ctrl+Supr; si sí, revisar sílabas"
        elif abs(extra) >= OUT_S and gain >= 0.25:
            why, fix = f"su voz está {extra:+.1f} s más allá".replace('.', ','), "«Ajustar a la voz» (A) o mover"
        else:
            level = 2
            why = "el modelo no la reconoció" if x['sure'] is None else "el modelo no está seguro de sus sílabas"
            fix = "escuchar; mover o corregir sílabas si hace falta"
        todo.append((t, level, f"- [ ] **{mmss(t)}** {why}: «{x['text']}» → {fix}"))
    return todo


def priority(m, place):
    todo = to_check(m, place)
    return (len(m['runs']) * 10 + (10 if m['verdict'] != 'ok' else 0) + 3 * sum(1 for x in todo if x[1] == 1)
            + sum(1 for x in todo if x[1] == 2))


def calibration(songs):
    """The note maker with and without the speech model on the official songs (tools/note_calibrate.py)."""
    import contextlib
    import io
    import note_calibrate
    out = {}
    for label, align in (('sin modelo (v4)', False), ('con modelo (actual)', 'only')):
        with contextlib.redirect_stdout(io.StringIO()):
            out[label] = note_calibrate.run(str(songs), SongMaker.make_notes, False, align)
    if not all(out.values()):
        return []

    def med(rows, part, key):
        values = [r[part][key] for r in rows if r[part] and not np.isnan(r[part][key])]
        return statistics.median(values) if values else float('nan')
    first = next(iter(out.values()))
    rows = [("sílabas a más de 0,3 s de su sitio", 1, 'off>0.3', pct), ("error típico del inicio de sílaba", 1,
             'onset_err', lambda v: f"{v:.2f} s".replace('.', ',')), ("tono exacto", 1, 'pitch_exact', pct), ("tono ±1 semitono", 1,
             'pitch±1', pct), ("notas cortas (<0,12 s)", 2, 'short<0.12', pct), ("saltos de 5+ semitonos", 2,
             'jump>=5', pct), ("notas por sílaba", 2, 'notes/syl', lambda v: f"{v:.2f}".replace('.', ','))]
    lines = ["## La prueba de verdad: contra las canciones oficiales", "",
             f"El generador recibe solo las líneas de la letra oficial y la voz de {len(first)} canciones oficiales, y sus "
             "notas se comparan con las oficiales (`tools/note_calibrate.py`).", "",
             "| | " + " | ".join(out) + " | oficial |", "|---|" + "---|" * (len(out) + 1)]
    for label, part, key, fmt in rows:
        official = fmt(med(first, 3, key)) if part == 2 else '—'
        lines.append(f"| {label} | " + " | ".join(fmt(med(r, part, key)) for r in out.values()) + f" | {official} |")
    return lines + [""]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('--md', required=True)
    parser.add_argument('--version', action='append', default=[], help='label=folder with old txt')
    parser.add_argument('--calibrate', action='store_true', help='add the test against the official songs')
    args = parser.parse_args()
    songs = Path(args.songs)
    versions = [v.split('=', 1) for v in args.version]
    results = []
    for d in sorted(os.listdir(songs)):
        folder = songs / d
        if not (folder / 'songmaker.json').exists():
            continue
        audio = audio_of(folder)
        voice = SyncModel.load_voice(SyncModel.voice_cache_path(str(folder)), str(audio)) if audio else None
        txt = current_txt(folder)
        if voice is None or txt is None:
            results.append((d, None, None, False, []))
            continue
        duration = len(voice['active']) * FRAME
        rows = []
        for label, path in versions:
            old = Path(os.path.expanduser(path)) / d / txt.name
            rows.append((label, measure(old, folder, voice, duration) if old.exists() else None))
        rows.append(('actual', measure(txt, folder, voice, duration)))
        edited = Path(str(txt) + '.bak').exists()
        try:
            place = None if edited else placement(folder)
        except Exception as e:
            print(f"{d}: placement not measured ({e})", flush=True)
            place = None
        meta = json.loads((folder / 'songmaker.json').read_text(encoding='utf-8'))
        results.append((d, rows, place, edited, meta))
        print(f"{d}: {arrow([m['match'] if m else None for _, m in rows])}", flush=True)

    done = [r for r in results if r[1]]
    first = versions[0][0] if versions else None
    lines = [f"# Canciones hechas con SongMaker ({len(results)})", "",
             f"Generado el {time.strftime('%Y-%m-%d %H:%M')} con `tools/songmaker_report.py` (no cambia nada). "
             "Cada canción se mide contra su propia voz separada (Demucs).", "",
             "- **Coincidencia**: cuánto de las notas tiene voz debajo, contando doble si el tono es el correcto "
             "(la medida del editor de sincronía; las oficiales dan ~40–75 %).",
             "- **Voz bajo las notas**: parte del tiempo de las notas en que se canta.",
             "- **Tono ±1**: parte de las notas cantadas a 1 semitono o menos de la voz (cualquier octava, como el "
             "juego).",
             "- **Líneas desfasadas**: su voz está a 0,3 s o más (el editor las movería con «Ajustar a la voz»).",
             "- **Notas cortas / saltos 5+**: estilo; las oficiales tienen ~1 % y ~8 %.",
             "- **Revisar**: *primero* = casi seguro que algo está mal (un bloque desfasado, una línea sin voz debajo "
             "= quizá no se canta, o con su voz en otro sitio); *si suena raro* = líneas cuyas sílabas el modelo no "
             "pudo colocar con seguridad. Marca `[x]` al corregirlas en el editor (los atajos: README, «Sync editor: "
             "buttons and shortcuts»).", ""]
    if done:
        cur = [r[1][-1][1] for r in done]
        lines.append("## Resumen")
        lines.append("")
        lines.append("| | " + (f"{first} | " if first else '') + " | ".join(v[0] for v in versions[1:]) +
                     (" | " if len(versions) > 1 else '') + "actual |")
        lines.append("|---|" + "---|" * (len(versions) + 1))
        for key, label in (('match', 'coincidencia (mediana)'), ('voice', 'voz bajo las notas'),
                           ('pitch', 'tono ±1'), ('short', 'notas cortas'), ('jump5', 'saltos 5+')):
            cells = []
            for k in range(len(versions) + 1):
                vals = [r[1][k][1][key] for r in done if r[1][k][1] is not None and not np.isnan(r[1][k][1][key])]
                cells.append(pct(statistics.median(vals)) if vals else '—')
            lines.append(f"| {label} | " + " | ".join(cells) + " |")
        for key, label in (('runs', 'bloques desfasados (varias líneas seguidas)'),
                           ('out', 'líneas sueltas que encajarían en otro sitio*')):
            cells = []
            for k in range(len(versions) + 1):
                ms = [r[1][k][1] for r in done if r[1][k][1] is not None]
                total = sum(m['lines'] for m in ms)
                count = sum(len(m[key]) for m in ms)
                cells.append(f"{count} en {sum(1 for m in ms if m[key])} canciones"
                             + (f" ({count / max(1, total):.0%})" if key == 'out' else ''))
            lines.append(f"| {label} | " + " | ".join(cells) + " |")
        lines += ["", "\\* Ruido de la medida, no errores: con las notas oficiales (correctas) de 20 canciones sale "
                  "un 16 % de líneas así (frases repetidas que también encajan en otro sitio). La coincidencia "
                  "tampoco es la verdad: las oficiales dan 53 % y la versión original, cortada pegada a la voz, "
                  "sale alta aunque sus sílabas estén mal puestas. Lo que manda es la comparación con las oficiales "
                  "de abajo."]
        ok = sum(1 for m in cur if m['verdict'] == 'ok')
        lines += ["", f"Veredicto actual: {ok} de {len(cur)} «ok»; el resto se lista abajo.", ""]
        lines += ["## Todas las canciones (las que más revisar, primero)", "",
                  "| | canción | idioma | coincidencia" + (f" ({first} → actual)" if first else '') +
                  " | tono ±1 | líneas reconocidas por el modelo | bloques desfasados | veredicto | "
                  "revisar: primero / si suena raro |",
                  "|---|---|---|---|---|---|---|---|---|"]
        # the ones the user checked by ear go last: they are done
        ordered = sorted(done, key=lambda r: (bool(r[4].get('user_checked')), -priority(r[1][-1][1], r[2])))
        checked = [r[0] for r in done if r[4].get('user_checked')]
        lines += [f"**Revisadas a oído por ti: {len(checked)} de {len(done)}** "
                  f"({', '.join(checked) if checked else 'ninguna todavía'}). Faltan {len(done) - len(checked)}.", ""]
        for i, (d, rows, place, edited, meta) in enumerate(ordered, 1):
            m = rows[-1][1]
            old = rows[0][1] if first else None
            language = language_of(current_txt(songs / d))
            share = '—'
            if place and place[0]:
                rate = sum(1 for x in place[0] if x['placed'] == 'model') / len(place[0])
                share = pct(rate) + (' ⚠' if rate < MODEL_SHARE else '')
            todo = to_check(m, place)
            todo = "✅ revisada" if meta.get('user_checked') else \
                f"{sum(1 for x in todo if x[1] == 1)} / {sum(1 for x in todo if x[1] == 2)}"
            anchor = d.lower().replace(' ', '-')
            lines.append(f"| {i} | [{d}](#{''.join(c for c in anchor if c.isalnum() or c == '-')}) | {language} | "
                         + (arrow([old['match'] if old else None, m['match']]) if first else pct(m['match']))
                         + f" | {pct(m['pitch'])} | {share} | {len(m['runs'])} | {m['verdict']} | {todo}"
                         + (" (editada)" if edited else '') + " |")
        lines += ["", "## Detalle por canción", ""]
        for d, rows, place, edited, meta in ordered:
            lines += song_section(d, rows, place, edited, meta.get('user_checked'))
    if args.calibrate:
        lines += calibration(songs)
    missing = [r[0] for r in results if not r[1]]
    if missing:
        lines += ["## Sin medir (falta la voz analizada o el txt)", ""] + [f"- {d}" for d in missing] + [""]
    Path(args.md).write_text('\n'.join(lines), encoding='utf-8')
    print(f"######## {args.md}: {len(done)} songs", flush=True)


if __name__ == '__main__':
    main()
