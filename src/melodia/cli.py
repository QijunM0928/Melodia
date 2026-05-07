"""Melodia CLI — command-line interface."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .config import load_config, MelodiaConfig
from .models.store import Store
from .models.song import Song
from .pipeline.qq_importer import import_qq_playlist
from .pipeline.csv_importer import import_csv_playlists
from .pipeline.netease_matcher import NeteaseMatcher
from .pipeline.external_discovery import ITunesDiscovery
from .pipeline.audio_features import extract_for_song
from .engine.vector_store import VectorStore
from .engine.taste_profile import generate_taste_profile
from .agent.tools import ToolExecutor
from .agent.agent import Agent

console = Console()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def main(verbose: bool):
    """Melodia — Personal AI music agent."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)


@main.command()
@click.option("--source", type=click.Choice(["qqmusic", "csv"]), required=True, help="Import source")
@click.option("--file", "filepath", type=click.Path(exists=True), required=True, help="Playlist file or directory")
@click.option("--skip-match", is_flag=True, help="Import as local-only songs without Netease matching")
def import_playlist(source: str, filepath: str, skip_match: bool):
    """Import a playlist from external source."""
    config = load_config()
    store = Store()

    if source == "qqmusic":
        console.print("[bold blue]Importing QQ Music playlist...[/]")
        songs = import_qq_playlist(filepath)
    else:
        console.print("[bold blue]Importing CSV playlist(s)...[/]")
        songs = import_csv_playlists(filepath)

    console.print(f"Found {len(songs)} unique songs")

    if skip_match:
        for song in songs:
            if not song.netease_id:
                song.netease_id = _local_song_id(song)
            store.upsert_song(song)
        console.print(f"[green]Saved {len(songs)} songs as local-only library[/]")
        return

    # Match to Netease
    console.print("[bold blue]Matching to Netease Cloud Music...[/]")
    matcher = NeteaseMatcher(config, store)
    matched = asyncio.run(matcher.match_all(songs))
    matched_count = sum(1 for s in matched if s.netease_id)
    console.print(f"[green]Matched {matched_count}/{len(songs)} songs to Netease[/]")


@main.command()
@click.option("--with-features", is_flag=True, help="Also extract audio features (slow)")
def index(with_features: bool):
    """Build vector index and taste profile."""
    config = load_config()
    store = Store()
    songs = store.get_all_songs()

    if not songs:
        console.print("[red]No songs in database. Import a playlist first.[/]")
        return

    console.print(f"[bold blue]Indexing {len(songs)} songs...[/]")

    # Audio features
    if with_features:
        console.print("[bold blue]Extracting audio features (this may take a while)...[/]")
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

        with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn()) as progress:
            task = progress.add_task("Extracting features...", total=len(songs))
            for song in songs:
                if not song.has_audio_features and song.netease_id:
                    song = asyncio.run(extract_for_song(song, config.netease))
                    store.upsert_song(song)
                progress.advance(task)

    # Build vector index
    console.print("[bold blue]Building vector index...[/]")
    vector_store = VectorStore()
    vector_store.index_all(store)
    console.print("[green]Vector index built[/]")

    # Generate taste profile
    console.print("[bold blue]Generating taste profile...[/]")
    profile = generate_taste_profile(
        songs, store, vector_store,
        llm_model=config.llm.model, api_base=config.llm.api_base, api_key=config.llm.api_key,
    )
    console.print("[green]Taste profile generated[/]")
    console.print(f"\n[bold]Taste Narrative:[/]")
    console.print(profile.narrative[:500])


@main.command()
@click.option("--host", default="127.0.0.1", help="Server host")
@click.option("--port", default=8765, help="Server port")
def serve(host: str, port: int):
    """Start the web UI server."""
    console.print(f"[bold blue]Starting Melodia server at http://{host}:{port}[/]")
    from .api.server import create_app
    import uvicorn
    app = create_app()
    uvicorn.run(app, host=host, port=port)


@main.command()
@click.argument("message", nargs=-1, required=True)
def chat(message: tuple[str, ...]):
    """Chat with Melodia in the terminal."""
    config = load_config()
    store = Store()
    vector_store = VectorStore()
    tool_executor = ToolExecutor(
        store, vector_store, config.netease,
        llm_model=config.llm.model, api_base=config.llm.api_base, api_key=config.llm.api_key,
    )
    agent = Agent(config, store, tool_executor)

    user_msg = " ".join(message)
    console.print(f"[bold]You:[/] {user_msg}")

    response = asyncio.run(agent.chat(user_msg))
    console.print(f"[bold cyan]Melodia:[/] {response}")


@main.command()
@click.option("--query", "-q", default="", help="Optional vibe/search text to seed discovery")
@click.option("--limit", default=20, show_default=True, help="Max external tracks to save")
def discover(query: str, limit: int):
    """Discover new candidate songs from external providers."""
    store = Store()

    if not store.get_all_songs():
        console.print("[red]No local songs found. Import and index your library first.[/]")
        return

    async def run() -> list[Song]:
        discovery = ITunesDiscovery(store)
        try:
            return await discovery.discover(query or "music", limit=limit)
        finally:
            await discovery.close()

    songs = asyncio.run(run())
    if not songs:
        console.print("[yellow]No external candidates found.[/]")
        return

    for song in songs:
        store.upsert_song(song)

    vector_store = VectorStore()
    for song in songs:
        vector_store.index_song(song)

    table = Table(title=f"Saved {len(songs)} external candidates")
    table.add_column("Title", style="bold")
    table.add_column("Artist")
    table.add_column("Source")
    for song in songs[:limit]:
        table.add_row(song.title, song.artist, ", ".join(song.tags[:2]))
    console.print(table)


@main.command()
def status():
    """Show current database status."""
    store = Store()
    songs = store.get_all_songs()
    profile = store.load_taste_profile()

    table = Table(title="Melodia Status")
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    table.add_row("Total songs", str(len(songs)))
    table.add_row("Songs with Netease ID", str(sum(1 for s in songs if s.netease_id > 0)))
    table.add_row(
        "External candidates",
        str(sum(1 for s in songs if s.netease_id < 0 and "iTunes" in s.tags)),
    )
    table.add_row("Songs with audio features", str(sum(1 for s in songs if s.has_audio_features)))
    table.add_row("Songs with lyrics", str(sum(1 for s in songs if s.lyrics)))
    table.add_row("Favorites", str(sum(1 for s in songs if s.is_favorite)))
    table.add_row("Feedback entries", str(store.feedback_count()))
    table.add_row("Taste profile", "Generated" if profile else "Not generated")

    if profile:
        table.add_row("Top genres", ", ".join(profile.top_genres[:5]))
        table.add_row("Top artists", ", ".join(profile.top_artists[:5]))
        table.add_row("Anti-patterns", str(len(profile.anti_patterns)))

    console.print(table)


def _local_song_id(song: Song) -> int:
    """Stable negative ID for local-only songs that are not matched to Netease yet."""
    key = f"{song.title}\0{song.artist}".casefold().encode("utf-8")
    value = int(hashlib.sha1(key).hexdigest()[:12], 16)
    return -(value % 2_000_000_000 + 1)


if __name__ == "__main__":
    main()
