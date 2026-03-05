"""Interactive REPL for BlessDog OSC bridge."""

from __future__ import annotations

import cmd
import logging
import sys
from dataclasses import asdict

from .connection import AbletonOSCConnection
from .devices import Devices
from .discovery import Discovery
from .errors import BlessDogError
from .scenes import Scenes
from .tracks import Tracks
from .transport import Transport


class BlessDogCLI(cmd.Cmd):
    intro = (
        "BlessDog OSC Bridge — Interactive REPL\n"
        "Type 'connect' to connect to Ableton Live.\n"
        "Type 'help' for available commands.\n"
        "Any input starting with '/' is sent as a raw OSC query.\n"
    )
    prompt = "blessdog> "

    def __init__(self):
        super().__init__()
        self.conn = AbletonOSCConnection()
        self.transport = Transport(self.conn)
        self.tracks = Tracks(self.conn)
        self.devices = Devices(self.conn)
        self.scenes = Scenes(self.conn)
        self.discovery = Discovery(self.conn)

    def _require_connection(self) -> bool:
        if not self.conn.connected:
            print("Not connected. Run 'connect' first.")
            return False
        return True

    # --- Connection ---

    def do_connect(self, _arg: str) -> None:
        """Connect to Ableton Live."""
        try:
            self.conn.connect()
            print("Connected to Ableton Live.")
        except BlessDogError as e:
            print(f"Error: {e}")

    def do_disconnect(self, _arg: str) -> None:
        """Disconnect from Ableton Live."""
        self.conn.disconnect()
        print("Disconnected.")

    def do_status(self, _arg: str) -> None:
        """Show transport state."""
        if not self._require_connection():
            return
        try:
            state = self.transport.get_state()
            for k, v in asdict(state).items():
                print(f"  {k}: {v}")
        except BlessDogError as e:
            print(f"Error: {e}")

    # --- Transport ---

    def do_play(self, _arg: str) -> None:
        """Start playback."""
        if not self._require_connection():
            return
        self.transport.play()
        print("Playing.")

    def do_stop(self, _arg: str) -> None:
        """Stop playback."""
        if not self._require_connection():
            return
        self.transport.stop()
        print("Stopped.")

    def do_tempo(self, arg: str) -> None:
        """Get or set tempo. Usage: tempo [bpm]"""
        if not self._require_connection():
            return
        try:
            if arg.strip():
                bpm = float(arg)
                self.transport.set_tempo(bpm)
                print(f"Tempo set to {bpm} BPM.")
            else:
                bpm = self.transport.get_tempo()
                print(f"Tempo: {bpm} BPM")
        except BlessDogError as e:
            print(f"Error: {e}")

    def do_undo(self, _arg: str) -> None:
        """Undo last action."""
        if not self._require_connection():
            return
        self.transport.undo()
        print("Undo.")

    def do_redo(self, _arg: str) -> None:
        """Redo last undone action."""
        if not self._require_connection():
            return
        self.transport.redo()
        print("Redo.")

    # --- Tracks ---

    def do_tracks(self, _arg: str) -> None:
        """List all tracks."""
        if not self._require_connection():
            return
        try:
            names = self.tracks.get_names()
            for i, name in enumerate(names):
                print(f"  [{i}] {name}")
        except BlessDogError as e:
            print(f"Error: {e}")

    def do_track(self, arg: str) -> None:
        """Show track details. Usage: track <index>"""
        if not self._require_connection():
            return
        try:
            index = int(arg.strip())
            info = self.tracks.get_info(index)
            for k, v in asdict(info).items():
                if k not in ("clips", "devices", "sends"):
                    print(f"  {k}: {v}")
        except (ValueError, BlessDogError) as e:
            print(f"Error: {e}")

    # --- Devices ---

    def do_devices(self, arg: str) -> None:
        """List devices on a track. Usage: devices <track_index>"""
        if not self._require_connection():
            return
        try:
            track = int(arg.strip())
            names = self.devices.get_names(track)
            for i, name in enumerate(names):
                print(f"  [{i}] {name}")
        except (ValueError, BlessDogError) as e:
            print(f"Error: {e}")

    def do_params(self, arg: str) -> None:
        """Show device parameters. Usage: params <track> <device>"""
        if not self._require_connection():
            return
        try:
            parts = arg.strip().split()
            track, device = int(parts[0]), int(parts[1])
            params = self.devices.get_parameters(track, device)
            for p in params:
                print(f"  [{p.index}] {p.name}: {p.value}")
        except (ValueError, IndexError, BlessDogError) as e:
            print(f"Error: {e}")

    # --- Scenes ---

    def do_scenes(self, _arg: str) -> None:
        """List all scenes."""
        if not self._require_connection():
            return
        try:
            names = self.scenes.get_names()
            for i, name in enumerate(names):
                label = name if name else "(unnamed)"
                print(f"  [{i}] {label}")
        except BlessDogError as e:
            print(f"Error: {e}")

    # --- Discovery ---

    def do_structure(self, _arg: str) -> None:
        """Show full session structure."""
        if not self._require_connection():
            return
        try:
            s = self.discovery.get_session_structure()
            print(f"  Tempo: {s.tempo} BPM")
            print(f"  Time Sig: {s.time_signature_num}/{s.time_signature_den}")
            print(f"  Tracks: {s.track_count}")
            print(f"  Scenes: {s.scene_count}")
            print()
            for t in s.tracks:
                print(f"  [{t.index}] {t.name}")
        except BlessDogError as e:
            print(f"Error: {e}")

    # --- Raw OSC ---

    def default(self, line: str) -> None:
        """Send raw OSC queries (lines starting with '/')."""
        if not line.startswith("/"):
            print(f"Unknown command: {line}")
            return
        if not self._require_connection():
            return

        parts = line.split()
        address = parts[0]
        args = []
        for a in parts[1:]:
            try:
                args.append(int(a))
            except ValueError:
                try:
                    args.append(float(a))
                except ValueError:
                    args.append(a)

        try:
            result = self.conn.query(address, *args)
            print(f"  → {result}")
        except BlessDogError as e:
            print(f"Error: {e}")

    # --- Meta ---

    def do_quit(self, _arg: str) -> bool:
        """Exit the REPL."""
        self.conn.disconnect()
        print("Bye.")
        return True

    do_exit = do_quit
    do_EOF = do_quit


def main():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    if "--debug" in sys.argv:
        logging.getLogger("phase1_osc").setLevel(logging.DEBUG)

    try:
        BlessDogCLI().cmdloop()
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()
