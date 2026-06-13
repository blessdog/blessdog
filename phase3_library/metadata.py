"""Per-format metadata extractors — wav, aif, adg, adv, nksf."""

from __future__ import annotations

import gzip
import struct
import wave
import xml.etree.ElementTree as ET
from typing import Any


def extract_wav_metadata(path: str) -> dict[str, Any]:
    """Extract audio metadata from a WAV file using stdlib wave module."""
    with wave.open(path, "rb") as w:
        frames = w.getnframes()
        rate = w.getframerate()
        return {
            "sample_rate": rate,
            "channels": w.getnchannels(),
            "bit_depth": w.getsampwidth() * 8,
            "duration_secs": round(frames / rate, 3) if rate else 0.0,
        }


def extract_aif_metadata(path: str) -> dict[str, Any]:
    """Extract audio metadata from an AIF/AIFF file.

    Uses manual AIFF COMM chunk parsing instead of the deprecated aifc module.
    """
    with open(path, "rb") as f:
        header = f.read(12)
        if len(header) < 12:
            return {}
        form_id = header[:4]
        aiff_id = header[8:12]
        if form_id != b"FORM" or aiff_id not in (b"AIFF", b"AIFC"):
            return {}

        # Walk chunks looking for COMM
        while True:
            chunk_header = f.read(8)
            if len(chunk_header) < 8:
                break
            chunk_id = chunk_header[:4]
            chunk_size = struct.unpack(">I", chunk_header[4:8])[0]

            if chunk_id == b"COMM":
                comm_data = f.read(min(chunk_size, 26))
                if len(comm_data) < 18:
                    break
                channels = struct.unpack(">h", comm_data[0:2])[0]
                num_frames = struct.unpack(">I", comm_data[2:6])[0]
                bit_depth = struct.unpack(">h", comm_data[6:8])[0]
                # 80-bit extended float for sample rate
                sample_rate = _parse_ieee_extended(comm_data[8:18])
                duration = round(num_frames / sample_rate, 3) if sample_rate else 0.0
                return {
                    "sample_rate": int(sample_rate),
                    "channels": channels,
                    "bit_depth": bit_depth,
                    "duration_secs": duration,
                }
            else:
                # Skip this chunk (pad to even boundary)
                skip = chunk_size + (chunk_size % 2)
                f.seek(skip, 1)

    return {}


def _parse_ieee_extended(data: bytes) -> float:
    """Parse an 80-bit IEEE 754 extended precision float (big-endian)."""
    # Used by AIFF for sample rate
    if len(data) < 10:
        return 0.0
    exponent = ((data[0] & 0x7F) << 8) | data[1]
    mantissa = int.from_bytes(data[2:10], "big")
    sign = -1.0 if data[0] & 0x80 else 1.0

    if exponent == 0 and mantissa == 0:
        return 0.0
    elif exponent == 0x7FFF:
        return float("inf") * sign

    f = mantissa / (1 << 63)
    f *= 2.0 ** (exponent - 16383)
    return sign * f


def extract_adg_metadata(path: str) -> dict[str, Any]:
    """Extract metadata from an Ableton .adg (device group) file.

    .adg files are gzip-compressed XML.
    """
    try:
        with gzip.open(path, "rb") as f:
            tree = ET.parse(f)
    except Exception:
        return {}

    root = tree.getroot()

    # The root element is <Ableton>, first child is the device group
    result: dict[str, Any] = {}

    # Extract Ableton version from root attributes
    creator = root.get("Creator", "")
    if creator:
        result["ableton_version"] = creator

    # First child element name is the device class
    for child in root:
        result["device_class"] = child.tag
        break

    return result


def extract_adv_metadata(path: str) -> dict[str, Any]:
    """Extract metadata from an Ableton .adv (device preset) file.

    Newer .adv files are gzip-compressed XML; older ones have a binary header.
    """
    # Try gzip first (newer format)
    try:
        with gzip.open(path, "rb") as f:
            tree = ET.parse(f)
        root = tree.getroot()
        result: dict[str, Any] = {}
        for child in root:
            result["device_class"] = child.tag
            break
        return result
    except Exception:
        pass

    # Binary header fallback — look for XML-like device class name
    try:
        with open(path, "rb") as f:
            header = f.read(4096)
        # Look for common Ableton device names in binary data
        text = header.decode("latin-1", errors="ignore")
        for tag in [
            "Drift", "Wavetable", "Operator", "Simpler", "Sampler",
            "Analog", "Tension", "Collision", "Electric",
            "AutoFilter", "Reverb", "Delay", "Compressor",
            "Eq8", "Saturator", "Redux", "Corpus",
        ]:
            if tag in text:
                return {"device_class": tag}
    except Exception:
        pass

    return {}


def extract_nksf_metadata(path: str) -> dict[str, Any]:
    """Extract metadata from an NI .nksf preset file.

    NKSF is a RIFF container. We look for the NISI chunk which contains
    MessagePack-encoded metadata: name, author, vendor, bankchain, types, etc.
    """
    try:
        import msgpack
    except ImportError:
        return {"_error": "msgpack not installed"}

    try:
        with open(path, "rb") as f:
            # RIFF header
            riff = f.read(4)
            if riff != b"RIFF":
                # Try NIKS magic
                if riff == b"NIKS":
                    f.seek(0)
                else:
                    return {}

            file_size = struct.unpack("<I", f.read(4))[0]
            container_type = f.read(4)  # e.g. b"NIKS"

            # Walk RIFF chunks
            while f.tell() < file_size + 8:
                chunk_id = f.read(4)
                if len(chunk_id) < 4:
                    break
                chunk_size = struct.unpack("<I", f.read(4))[0]

                if chunk_id == b"NISI":
                    data = f.read(chunk_size)
                    meta = msgpack.unpackb(data, raw=False)
                    result: dict[str, Any] = {}
                    if "author" in meta:
                        result["nksf_author"] = meta["author"]
                    if "vendor" in meta:
                        result["nksf_vendor"] = meta["vendor"]
                    if "bankchain" in meta:
                        result["nksf_bankchain"] = meta["bankchain"]
                    if "types" in meta:
                        result["nksf_types"] = meta["types"]
                    if "modes" in meta:
                        result["nksf_characters"] = meta["modes"]
                    return result
                else:
                    # Skip chunk (pad to even)
                    skip = chunk_size + (chunk_size % 2)
                    f.seek(skip, 1)
    except Exception:
        pass

    return {}


def extract_metadata(path: str, extension: str) -> dict[str, Any]:
    """Dispatch to the appropriate extractor. Returns {} on any error."""
    try:
        if extension in (".wav",):
            return extract_wav_metadata(path)
        elif extension in (".aif", ".aiff"):
            return extract_aif_metadata(path)
        elif extension == ".adg":
            return extract_adg_metadata(path)
        elif extension == ".adv":
            return extract_adv_metadata(path)
        elif extension == ".nksf":
            return extract_nksf_metadata(path)
    except Exception:
        pass
    return {}
