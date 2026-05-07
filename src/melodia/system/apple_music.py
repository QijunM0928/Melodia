"""Apple Music control through macOS AppleScript."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from ..models.song import Song


def applescript_string(value: str) -> str:
    """Quote a Python string for AppleScript source."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


@dataclass
class AppleMusicResult:
    ok: bool
    code: str
    message: str
    title: str = ""
    artist: str = ""
    album: str = ""


class AppleMusicController:
    """Small Music.app controller.

    This controls the local macOS Music app. It can reliably play tracks that
    are in the user's Music library. AppleScript does not provide a stable,
    headless way to search the full Apple Music streaming catalog.
    """

    def _run(self, script: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["osascript", "-e", script],
                text=True,
                capture_output=True,
                timeout=12,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                ["osascript", "-e", script],
                returncode=124,
                stdout="",
                stderr="Apple Music automation timed out. Grant automation permission or open Music.app once.",
            )

    def play_song(self, song: Song) -> AppleMusicResult:
        query = " ".join(part for part in [song.title, song.artist] if part).strip()
        if not query:
            return AppleMusicResult(False, "missing_query", "Song title or artist is missing.")

        script = f"""
tell application "Music"
    launch
    set searchQuery to {applescript_string(query)}
    set titleQuery to {applescript_string(song.title)}
    set foundTracks to (search library playlist 1 for searchQuery only songs)
    if (count of foundTracks) is 0 then
        set foundTracks to (search library playlist 1 for titleQuery only songs)
    end if
    if (count of foundTracks) is 0 then
        return "NOT_FOUND"
    end if
    set selectedTrack to item 1 of foundTracks
    play selectedTrack
    set trackName to name of selectedTrack
    set trackArtist to artist of selectedTrack
    set trackAlbum to album of selectedTrack
    return trackName & linefeed & trackArtist & linefeed & trackAlbum
end tell
""".strip()

        result = self._run(script)
        if result.returncode != 0:
            error = (result.stderr or result.stdout).strip()
            return AppleMusicResult(
                False,
                "automation_failed",
                error or "Apple Music automation failed.",
            )

        output = result.stdout.strip()
        if output == "NOT_FOUND":
            return AppleMusicResult(
                False,
                "not_in_library",
                "Apple Music library did not contain a matching track.",
            )

        lines = output.splitlines()
        return AppleMusicResult(
            True,
            "playing",
            "Apple Music started playback.",
            title=lines[0] if len(lines) > 0 else song.title,
            artist=lines[1] if len(lines) > 1 else song.artist,
            album=lines[2] if len(lines) > 2 else song.album,
        )

    def current_track(self) -> AppleMusicResult:
        script = """
tell application "Music"
    if player state is stopped then
        return "STOPPED"
    end if
    set selectedTrack to current track
    return (name of selectedTrack) & linefeed & (artist of selectedTrack) & linefeed & (album of selectedTrack)
end tell
""".strip()
        result = self._run(script)
        if result.returncode != 0:
            return AppleMusicResult(False, "automation_failed", (result.stderr or "").strip())
        output = result.stdout.strip()
        if output == "STOPPED":
            return AppleMusicResult(False, "stopped", "Apple Music is stopped.")
        lines = output.splitlines()
        return AppleMusicResult(
            True,
            "playing",
            "Apple Music is playing.",
            title=lines[0] if len(lines) > 0 else "",
            artist=lines[1] if len(lines) > 1 else "",
            album=lines[2] if len(lines) > 2 else "",
        )
