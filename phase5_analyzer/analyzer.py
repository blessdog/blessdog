"""Orchestrator — runs the full analysis pipeline.

1. (Optional) Metadata lookup
2. Demucs stem separation
3. Per-stem librosa analysis
4. Structured output for LLM consumption
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from .separator import StemPaths, separate, is_available as demucs_available
from .stems import FullAnalysis, analyze_stems


@dataclass
class TrackAnalysis:
    """Complete analysis result for a reference track."""
    file_path: str
    file_name: str
    analysis: FullAnalysis | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    stem_paths: StemPaths | None = None
    error: str | None = None
    elapsed_secs: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "file": self.file_name,
            "file_path": self.file_path,
        }
        if self.metadata:
            result["metadata"] = self.metadata
        if self.analysis:
            result["analysis"] = self.analysis.to_dict()
        if self.stem_paths:
            result["stems_dir"] = os.path.dirname(self.stem_paths.drums)
        if self.error:
            result["error"] = self.error
        result["elapsed_secs"] = round(self.elapsed_secs, 1)
        return result

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def summary(self) -> str:
        """Generate a concise text summary for LLM context."""
        if self.error:
            return f"Analysis failed for {self.file_name}: {self.error}"

        if not self.analysis:
            return f"No analysis data for {self.file_name}"

        a = self.analysis
        lines = [
            f"## Reference Track: {self.file_name}",
            "",
            f"**Tempo:** {a.tempo_bpm} BPM | "
            f"**Key:** {a.key_root}{a.key_mode[0]} | "
            f"**Duration:** {a.duration_secs:.0f}s "
            f"({int(a.duration_secs / (4 * 60 / a.tempo_bpm))} bars)",
            "",
        ]

        # Stems summary
        for name, stem in a.stems.items():
            avg_energy = sum(stem.energy_per_bar) / max(len(stem.energy_per_bar), 1)
            lines.append(f"**{name.title()}:** avg energy {avg_energy:.4f}")
            if "root_notes" in stem.extra and stem.extra["root_notes"]:
                lines.append(f"  Root notes: {', '.join(stem.extra['root_notes'])}")
            if "present" in stem.extra:
                lines.append(f"  Vocals present: {stem.extra['present']}")
            if "onset_count" in stem.extra:
                lines.append(f"  Onsets: {stem.extra['onset_count']}")

        # Chord progression (deduplicated sequence)
        if "other" in a.stems and "chords_per_bar" in a.stems["other"].extra:
            chords = a.stems["other"].extra["chords_per_bar"]
            # Deduplicate consecutive
            deduped = []
            for c in chords:
                if not deduped or c != deduped[-1]:
                    deduped.append(c)
            lines.append(f"\n**Chord sequence:** {' → '.join(deduped[:16])}")
            if len(deduped) > 16:
                lines.append(f"  ... ({len(deduped)} total changes)")

        # Arrangement
        if a.segment_boundaries:
            lines.append(f"\n**Section boundaries (bars):** "
                         f"{', '.join(str(int(b)) for b in a.segment_boundaries)}")

        # Density narrative
        n = len(a.density_per_bar)
        if n >= 4:
            quarter = n // 4
            q1 = sum(a.density_per_bar[:quarter]) / quarter
            q2 = sum(a.density_per_bar[quarter:2*quarter]) / quarter
            q3 = sum(a.density_per_bar[2*quarter:3*quarter]) / quarter
            q4 = sum(a.density_per_bar[3*quarter:]) / max(n - 3*quarter, 1)
            lines.append(f"\n**Density arc:** "
                         f"Q1={q1:.2f} → Q2={q2:.2f} → Q3={q3:.2f} → Q4={q4:.2f}")

        return "\n".join(lines)


def analyze_track(
    audio_path: str,
    metadata: dict[str, Any] | None = None,
    output_dir: str | None = None,
    model: str = "htdemucs",
) -> TrackAnalysis:
    """Full analysis pipeline for a reference track.

    Args:
        audio_path: Path to audio file (WAV, MP3, FLAC, etc.).
        metadata: Optional pre-supplied metadata (title, artist, bpm, key).
        output_dir: Directory for stem output. Defaults to temp.
        model: Demucs model name.

    Returns:
        TrackAnalysis with all results.
    """
    start = time.time()
    file_name = os.path.basename(audio_path)

    result = TrackAnalysis(
        file_path=os.path.abspath(audio_path),
        file_name=file_name,
        metadata=metadata or {},
    )

    if not os.path.isfile(audio_path):
        result.error = f"File not found: {audio_path}"
        result.elapsed_secs = time.time() - start
        return result

    if not demucs_available():
        result.error = (
            "Demucs is not installed. Install with: "
            "pip install demucs"
        )
        result.elapsed_secs = time.time() - start
        return result

    try:
        # Step 1: Stem separation
        stems = separate(audio_path, output_dir=output_dir, model=model)
        result.stem_paths = stems

        # Step 2: Per-stem analysis
        analysis = analyze_stems(stems.all(), source_path=audio_path)
        result.analysis = analysis

    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"

    result.elapsed_secs = time.time() - start
    return result
