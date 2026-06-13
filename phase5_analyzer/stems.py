"""Per-stem audio analysis using librosa.

Analyzes separated stems to extract musically meaningful features:
- Drums: onset grid, transient density, pattern detection
- Bass: pitch tracking, root notes
- Other (chords/synths): chromagram, chord estimation
- Vocals: presence detection, active regions
- All stems: energy curves at bar resolution
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

import librosa
import numpy as np


@dataclass
class StemAnalysis:
    """Analysis results for a single stem."""
    name: str
    duration_secs: float
    energy_per_bar: list[float] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "duration_secs": round(self.duration_secs, 2),
            "energy_per_bar": [round(v, 4) for v in self.energy_per_bar],
            **self.extra,
        }


@dataclass
class FullAnalysis:
    """Combined analysis of all stems + global features."""
    duration_secs: float
    tempo_bpm: float
    tempo_confidence: float
    key_root: str
    key_mode: str
    key_confidence: float
    time_signature: int
    stems: dict[str, StemAnalysis] = field(default_factory=dict)
    density_per_bar: list[float] = field(default_factory=list)
    energy_per_bar: list[float] = field(default_factory=list)
    segment_boundaries: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_secs": round(self.duration_secs, 2),
            "tempo": {
                "bpm": round(self.tempo_bpm, 1),
                "confidence": round(self.tempo_confidence, 3),
            },
            "key": {
                "root": self.key_root,
                "mode": self.key_mode,
                "confidence": round(self.key_confidence, 3),
            },
            "time_signature": self.time_signature,
            "stems": {k: v.to_dict() for k, v in self.stems.items()},
            "arrangement": {
                "energy_per_bar": [round(v, 4) for v in self.energy_per_bar],
                "density_per_bar": [round(v, 4) for v in self.density_per_bar],
                "segment_boundaries_bars": [
                    round(v, 1) for v in self.segment_boundaries
                ],
            },
        }


# -- Key name mapping --------------------------------------------------------

_KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_MODE_NAMES = {0: "minor", 1: "major"}

# Standard major and minor profiles (Krumhansl-Schmuckler)
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                           2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                           2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def _estimate_key(y: np.ndarray, sr: int) -> tuple[str, str, float]:
    """Estimate key using chromagram correlation with key profiles."""
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_avg = np.mean(chroma, axis=1)

    best_corr = -1.0
    best_key = 0
    best_mode = 1

    for shift in range(12):
        rolled = np.roll(chroma_avg, -shift)
        for mode, profile in [(1, _MAJOR_PROFILE), (0, _MINOR_PROFILE)]:
            corr = float(np.corrcoef(rolled, profile)[0, 1])
            if corr > best_corr:
                best_corr = corr
                best_key = shift
                best_mode = mode

    return _KEY_NAMES[best_key], _MODE_NAMES[best_mode], max(0.0, best_corr)


def _rms_per_bar(y: np.ndarray, sr: int, bpm: float, n_bars: int) -> list[float]:
    """Compute RMS energy averaged per bar."""
    bar_duration = 4 * 60.0 / bpm  # 4 beats per bar
    bar_samples = int(bar_duration * sr)
    result = []
    for i in range(n_bars):
        start = i * bar_samples
        end = min(start + bar_samples, len(y))
        if start >= len(y):
            result.append(0.0)
        else:
            segment = y[start:end]
            rms = float(np.sqrt(np.mean(segment ** 2)))
            result.append(rms)
    return result


def _estimate_tempo(y: np.ndarray, sr: int) -> tuple[float, float]:
    """Estimate tempo with confidence."""
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo_arr = librosa.feature.tempo(
        onset_envelope=onset_env, sr=sr, aggregate=None,
    )
    if len(tempo_arr) == 0:
        return 120.0, 0.0

    # Use the most common tempo estimate
    tempo = float(np.median(tempo_arr))
    # Confidence from autocorrelation peak
    ac = librosa.autocorrelate(onset_env, max_size=len(onset_env))
    if len(ac) > 1:
        confidence = float(np.max(ac[1:]) / (ac[0] + 1e-6))
    else:
        confidence = 0.0

    return tempo, min(confidence, 1.0)


# -- Drum stem analysis ------------------------------------------------------

def _analyze_drums(path: str, sr: int, bpm: float, n_bars: int) -> StemAnalysis:
    """Analyze drum stem for onset patterns and density."""
    y, sr = librosa.load(path, sr=sr, mono=True)
    duration = float(len(y) / sr)

    energy = _rms_per_bar(y, sr, bpm, n_bars)

    # Onset detection
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units="frames")
    onset_times = librosa.frames_to_time(onset_frames, sr=sr).tolist()

    # Density: onsets per bar
    bar_duration = 4 * 60.0 / bpm
    density = [0.0] * n_bars
    for t in onset_times:
        bar_idx = int(t / bar_duration)
        if bar_idx < n_bars:
            density[bar_idx] += 1

    # Spectral centroid (brightness over time)
    cent = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    avg_brightness = float(np.mean(cent))

    return StemAnalysis(
        name="drums",
        duration_secs=duration,
        energy_per_bar=energy,
        extra={
            "onset_count": len(onset_times),
            "onsets_per_bar": [round(d, 1) for d in density],
            "avg_brightness_hz": round(avg_brightness, 1),
        },
    )


# -- Bass stem analysis ------------------------------------------------------

def _analyze_bass(path: str, sr: int, bpm: float, n_bars: int) -> StemAnalysis:
    """Analyze bass stem for pitch and root notes."""
    y, sr = librosa.load(path, sr=sr, mono=True)
    duration = float(len(y) / sr)

    energy = _rms_per_bar(y, sr, bpm, n_bars)

    # Pitch tracking with pyin
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f0, voiced_flag, _ = librosa.pyin(
            y, fmin=30, fmax=500, sr=sr,
        )

    # Find root notes from pitched frames
    root_notes: list[str] = []
    if f0 is not None:
        valid_f0 = f0[~np.isnan(f0)]
        if len(valid_f0) > 0:
            # Convert to MIDI note numbers, then to note names
            midi_notes = librosa.hz_to_midi(valid_f0)
            # Get pitch classes (0-11)
            pitch_classes = np.round(midi_notes) % 12
            # Most common pitch classes
            counts = np.bincount(pitch_classes.astype(int), minlength=12)
            top_indices = np.argsort(counts)[::-1]
            for idx in top_indices[:4]:
                if counts[idx] > 0:
                    root_notes.append(_KEY_NAMES[idx])

    return StemAnalysis(
        name="bass",
        duration_secs=duration,
        energy_per_bar=energy,
        extra={
            "root_notes": root_notes,
        },
    )


# -- Other/chords stem analysis ----------------------------------------------

def _analyze_other(path: str, sr: int, bpm: float, n_bars: int) -> StemAnalysis:
    """Analyze 'other' stem (chords, synths, pads) for harmonic content."""
    y, sr = librosa.load(path, sr=sr, mono=True)
    duration = float(len(y) / sr)

    energy = _rms_per_bar(y, sr, bpm, n_bars)

    # Chromagram per bar
    bar_duration = 4 * 60.0 / bpm
    chroma_per_bar: list[list[float]] = []

    for i in range(n_bars):
        start_sample = int(i * bar_duration * sr)
        end_sample = int(min((i + 1) * bar_duration * sr, len(y)))
        if start_sample >= len(y):
            chroma_per_bar.append([0.0] * 12)
            continue
        segment = y[start_sample:end_sample]
        if len(segment) < 2048:
            chroma_per_bar.append([0.0] * 12)
            continue
        chroma = librosa.feature.chroma_cqt(y=segment, sr=sr)
        bar_chroma = np.mean(chroma, axis=1).tolist()
        chroma_per_bar.append([round(v, 3) for v in bar_chroma])

    # Simple chord estimation per bar from chromagram
    chord_names = _chroma_to_chords(chroma_per_bar)

    return StemAnalysis(
        name="other",
        duration_secs=duration,
        energy_per_bar=energy,
        extra={
            "chords_per_bar": chord_names,
            "chroma_per_bar": chroma_per_bar,
        },
    )


_CHORD_TEMPLATES = {
    "maj": [1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0],
    "min": [1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0],
    "7":   [1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0],
    "m7":  [1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0],
    "maj7":[1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1],
}


def _chroma_to_chords(chroma_per_bar: list[list[float]]) -> list[str]:
    """Estimate chord name per bar from chromagram using template matching."""
    chords = []
    templates = np.array(list(_CHORD_TEMPLATES.values()), dtype=float)
    template_names = list(_CHORD_TEMPLATES.keys())

    for bar_chroma in chroma_per_bar:
        c = np.array(bar_chroma)
        if np.sum(c) < 0.01:
            chords.append("N/C")
            continue

        best_corr = -1.0
        best_chord = "N/C"

        for root in range(12):
            rolled = np.roll(c, -root)
            for ti, tmpl in enumerate(templates):
                corr = float(np.corrcoef(rolled, tmpl)[0, 1])
                if corr > best_corr:
                    best_corr = corr
                    suffix = template_names[ti]
                    if suffix == "maj":
                        suffix = ""
                    best_chord = f"{_KEY_NAMES[root]}{suffix}"

        chords.append(best_chord)

    return chords


# -- Vocals stem analysis ----------------------------------------------------

def _analyze_vocals(path: str, sr: int, bpm: float, n_bars: int) -> StemAnalysis:
    """Analyze vocal stem for presence and active regions."""
    y, sr = librosa.load(path, sr=sr, mono=True)
    duration = float(len(y) / sr)

    energy = _rms_per_bar(y, sr, bpm, n_bars)

    # Detect active vocal regions (bars where energy exceeds threshold)
    threshold = np.mean(energy) * 0.3 if energy else 0.0
    active_bars = [i for i, e in enumerate(energy) if e > threshold]

    # Group consecutive bars into regions
    regions: list[tuple[int, int]] = []
    if active_bars:
        start = active_bars[0]
        prev = start
        for b in active_bars[1:]:
            if b > prev + 1:
                regions.append((start, prev))
                start = b
            prev = b
        regions.append((start, prev))

    has_vocals = len(active_bars) > max(2, n_bars * 0.05)

    return StemAnalysis(
        name="vocals",
        duration_secs=duration,
        energy_per_bar=energy,
        extra={
            "present": has_vocals,
            "active_bar_regions": regions,
            "active_bar_count": len(active_bars),
        },
    )


# -- Arrangement analysis ----------------------------------------------------

def _detect_segments(
    energy_curves: dict[str, list[float]],
    n_bars: int,
) -> list[float]:
    """Detect arrangement segment boundaries from combined energy curves.

    Uses changes in the combined density/energy profile to find section
    transitions. Returns bar numbers where significant changes occur.
    """
    if n_bars < 4:
        return []

    # Combine all stem energies into a single feature vector per bar
    combined = np.zeros(n_bars)
    for curve in energy_curves.values():
        arr = np.array(curve[:n_bars])
        if len(arr) < n_bars:
            arr = np.pad(arr, (0, n_bars - len(arr)))
        # Normalize each stem's energy
        mx = np.max(arr)
        if mx > 0:
            arr = arr / mx
        combined += arr

    # Smooth with a 4-bar window
    kernel = np.ones(4) / 4
    smoothed = np.convolve(combined, kernel, mode="same")

    # Find significant changes (derivative peaks)
    diff = np.abs(np.diff(smoothed))
    threshold = np.mean(diff) + np.std(diff)

    boundaries = [0.0]
    for i, d in enumerate(diff):
        if d > threshold:
            bar = float(i + 1)
            # Don't add boundaries too close together (min 4 bars apart)
            if bar - boundaries[-1] >= 4:
                boundaries.append(bar)

    return boundaries


# -- Main analysis entry point -----------------------------------------------

def analyze_stems(
    stem_paths: dict[str, str],
    source_path: str | None = None,
    sr: int = 22050,
) -> FullAnalysis:
    """Run full analysis on separated stems.

    Args:
        stem_paths: Dict mapping stem name to file path.
                    Expected keys: drums, bass, vocals, other.
        source_path: Path to original mixed file (for global tempo/key).
        sr: Sample rate for analysis.

    Returns:
        FullAnalysis with per-stem and global features.
    """
    # Use the 'other' stem + bass for key estimation (cleaner than vocals)
    # Use drums for tempo estimation (clearest transients)
    drums_path = stem_paths.get("drums", "")
    bass_path = stem_paths.get("bass", "")
    other_path = stem_paths.get("other", "")
    vocals_path = stem_paths.get("vocals", "")

    # Load drums for tempo
    y_drums, _ = librosa.load(drums_path, sr=sr, mono=True)
    duration = float(len(y_drums) / sr)

    # Estimate tempo from drum stem
    bpm, tempo_conf = _estimate_tempo(y_drums, sr)

    # Round to nearest whole BPM for electronic music
    bpm_rounded = round(bpm)

    # Calculate number of bars
    bar_duration = 4 * 60.0 / bpm_rounded
    n_bars = max(1, int(duration / bar_duration))

    # Key estimation from bass + other combined
    y_bass, _ = librosa.load(bass_path, sr=sr, mono=True)
    y_other, _ = librosa.load(other_path, sr=sr, mono=True)
    # Mix bass and other for key detection
    min_len = min(len(y_bass), len(y_other))
    y_harmonic = y_bass[:min_len] + y_other[:min_len]
    key_root, key_mode, key_conf = _estimate_key(y_harmonic, sr)

    # Analyze each stem
    stems: dict[str, StemAnalysis] = {}
    stems["drums"] = _analyze_drums(drums_path, sr, bpm_rounded, n_bars)
    stems["bass"] = _analyze_bass(bass_path, sr, bpm_rounded, n_bars)
    stems["other"] = _analyze_other(other_path, sr, bpm_rounded, n_bars)
    stems["vocals"] = _analyze_vocals(vocals_path, sr, bpm_rounded, n_bars)

    # Combined energy and density
    energy_curves = {k: v.energy_per_bar for k, v in stems.items()}

    combined_energy = [0.0] * n_bars
    density = [0.0] * n_bars
    for curve in energy_curves.values():
        for i, e in enumerate(curve[:n_bars]):
            combined_energy[i] += e
            if e > 0.001:
                density[i] += 1.0

    # Normalize density to 0-1 range (4 stems max)
    density = [d / 4.0 for d in density]

    # Segment boundaries
    boundaries = _detect_segments(energy_curves, n_bars)

    return FullAnalysis(
        duration_secs=duration,
        tempo_bpm=float(bpm_rounded),
        tempo_confidence=tempo_conf,
        key_root=key_root,
        key_mode=key_mode,
        key_confidence=key_conf,
        time_signature=4,
        stems=stems,
        density_per_bar=density,
        energy_per_bar=combined_energy,
        segment_boundaries=boundaries,
    )
