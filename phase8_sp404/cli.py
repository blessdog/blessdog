"""CLI for the SP-404MK2 sample lane.

    python -m phase8_sp404 cards
    python -m phase8_sp404 add <file|url> [--kind loop] [--bank rave] [--name X]
    python -m phase8_sp404 stems <file> [--bank rave]
    python -m phase8_sp404 list [--kind stem] [--bank rave]
    python -m phase8_sp404 push [--kind loop] [--bank rave] [--card /Volumes/SP]

Nonzero exit means the verb failed. Nothing is ever written to a card unless
an IMPORT folder was actually found on it.
"""

from __future__ import annotations

import argparse
import os
import sys

from .build import push_to_card, stage_file, stage_stems
from .card import CardError, detect_cards, find_import_folder, free_bytes
from .convert import is_available as ffmpeg_available
from .ledger import KINDS, Ledger


def _is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _resolve_target(card_arg: str | None):
    """Pick a card, refusing to guess when the choice is ambiguous."""
    if card_arg:
        return find_import_folder(card_arg)

    found = detect_cards()
    if not found:
        raise CardError(
            "no SP-404MK2 card detected under /Volumes. Insert the card, or "
            "pass --card <path>. If it is mounted but unrecognised, format it "
            "in the device first (UTILITY -> SD CARD -> FORMAT)."
        )
    if len(found) > 1:
        roots = ", ".join(target.card_root for target in found)
        raise CardError(f"multiple candidate cards ({roots}) — pass --card to choose")
    return found[0]


def cmd_cards(args) -> int:
    found = detect_cards()
    if not found:
        print("no SP-404MK2 card detected under /Volumes")
        return 1
    for target in found:
        free_mb = free_bytes(target.card_root) / (1024 * 1024)
        print(f"{target.card_root}\n  import: {target.import_dir}\n  free:   {free_mb:,.0f} MB")
    return 0


def cmd_add(args) -> int:
    ledger = Ledger()
    source = args.source
    source_url = ""
    title = args.name or ""
    artist = ""

    if _is_url(source):
        try:
            from phase5_analyzer.download import download
        except ImportError:
            print("URL sources need phase5_analyzer (yt-dlp). Install it, or "
                  "download the file yourself and pass the path.", file=sys.stderr)
            return 2
        print(f"downloading {source} ...")
        got = download(source, wav=True)
        if not got.success:
            print(f"download failed: {got.error}", file=sys.stderr)
            return 1
        source_url = source
        title = title or got.title
        artist = got.artist
        source = got.file_path

    outcome = stage_file(
        source,
        kind=args.kind,
        name=args.name,
        bank=args.bank,
        ledger=ledger,
        source_url=source_url,
        title=title,
        artist=artist,
        normalize=args.normalize,
        mono=args.mono,
    )
    if not outcome.success:
        print(f"failed: {outcome.error}", file=sys.stderr)
        return 1
    if outcome.skipped_duplicate and outcome.entry:
        print(f"already in library as {outcome.entry.name} "
              f"({outcome.entry.kind}) — nothing to do")
        return 0
    if outcome.entry:
        print(f"staged {outcome.entry.name} [{outcome.entry.kind}] "
              f"{outcome.entry.duration_secs:.1f}s -> {outcome.entry.local_path}")
    return 0


def cmd_stems(args) -> int:
    try:
        from phase5_analyzer.separator import is_available as demucs_available
        from phase5_analyzer.separator import separate
    except ImportError:
        print("stem separation needs phase5_analyzer (demucs).", file=sys.stderr)
        return 2
    if not demucs_available():
        print("demucs is not installed: pip install demucs", file=sys.stderr)
        return 2

    print(f"separating {args.source} (this takes a few minutes) ...")
    stems = separate(args.source)
    title = args.name or os.path.splitext(os.path.basename(args.source))[0]
    batch = stage_stems(stems.all(), bank=args.bank, title=title)
    print(batch.summary())
    for entry in batch.staged:
        print(f"  {entry.name} <- {entry.derived_from}")
    return 1 if batch.failed else 0


def cmd_list(args) -> int:
    ledger = Ledger()
    entries = ledger.entries
    if args.kind:
        entries = [entry for entry in entries if entry.kind == args.kind]
    if args.bank:
        entries = [entry for entry in entries if entry.bank == args.bank]

    if not entries:
        print("library is empty (or nothing matched)")
        return 0

    print(f"{len(entries)} sample(s) in {ledger.path}\n")
    for entry in entries:
        oncard = "  [on card]" if entry.card_path else ""
        bpm = f" {entry.bpm:.0f}bpm" if entry.bpm else ""
        key = f" {entry.key}" if entry.key else ""
        bank = f" ({entry.bank})" if entry.bank else ""
        print(f"  {entry.name:<34} {entry.kind:<8} "
              f"{entry.duration_secs:>7.1f}s{bpm}{key}{bank}{oncard}")
    return 0


def cmd_push(args) -> int:
    ledger = Ledger()
    entries = ledger.entries
    if args.kind:
        entries = [entry for entry in entries if entry.kind == args.kind]
    if args.bank:
        entries = [entry for entry in entries if entry.bank == args.bank]
    if not args.all:
        entries = [entry for entry in entries if not entry.card_path]

    if not entries:
        print("nothing to push (use --all to re-push samples already on a card)")
        return 0

    try:
        target = _resolve_target(args.card)
    except CardError as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1

    print(f"pushing {len(entries)} sample(s) -> {target.import_dir}")
    batch = push_to_card(entries, target, ledger=ledger, overwrite=args.overwrite)
    print(batch.summary())
    print("\nNow import them on the device: SD card in, then the SP's "
          "IMPORT function assigns them to pads.")
    return 1 if batch.failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phase8_sp404",
        description="Build an SP-404MK2 sample library and file it to the card.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("cards", help="list detected SP-404MK2 cards").set_defaults(
        func=cmd_cards
    )

    add = sub.add_parser("add", help="stage a local file or URL into the library")
    add.add_argument("source", help="audio file path or URL")
    add.add_argument("--kind", choices=KINDS, default="oneshot")
    add.add_argument("--bank", default="", help="organisational label, e.g. 'rave'")
    add.add_argument("--name", default=None, help="override the sample name")
    add.add_argument("--normalize", action="store_true",
                     help="EBU R128 loudness normalise (off by default — it "
                          "flattens one-shot transients)")
    add.add_argument("--mono", action="store_true", help="downmix to mono")
    add.set_defaults(func=cmd_add)

    stems = sub.add_parser("stems", help="Demucs-separate a file and stage its stems")
    stems.add_argument("source", help="audio file path")
    stems.add_argument("--bank", default="")
    stems.add_argument("--name", default=None)
    stems.set_defaults(func=cmd_stems)

    listing = sub.add_parser("list", help="show the library ledger")
    listing.add_argument("--kind", choices=KINDS, default=None)
    listing.add_argument("--bank", default=None)
    listing.set_defaults(func=cmd_list)

    push = sub.add_parser("push", help="copy staged samples onto the card")
    push.add_argument("--kind", choices=KINDS, default=None)
    push.add_argument("--bank", default=None)
    push.add_argument("--card", default=None, help="card root, e.g. /Volumes/SP404")
    push.add_argument("--all", action="store_true",
                      help="include samples already marked as on a card")
    push.add_argument("--overwrite", action="store_true")
    push.set_defaults(func=cmd_push)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command in {"add", "stems"} and not ffmpeg_available():
        print("ffmpeg and ffprobe are required and were not found on PATH",
              file=sys.stderr)
        return 2

    try:
        return args.func(args)
    except (CardError, RuntimeError, ValueError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
