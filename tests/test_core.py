from pathlib import Path

from melodia.agent.tools import ToolExecutor
from melodia.config import NeteaseConfig
from melodia.models.song import Recommendation, Song
from melodia.models.store import Store
from melodia.pipeline.external_discovery import ITunesDiscovery, external_song_id
from melodia.pipeline.csv_importer import import_csv_playlists
from melodia.pipeline.qq_music import qq_music_search_url
from melodia.pipeline.qq_importer import import_qq_playlist, parse_qq_playlist


def test_parse_qq_playlist_deduplicates_tracks():
    songs = parse_qq_playlist(
        [
            {"title": "晴天", "singer": "周杰伦", "album": "叶惠美", "duration": 269},
            {"title": "晴天", "singer": "周杰伦", "album": "叶惠美", "duration": 269},
            {"song_name": "红豆", "singer": [{"name": "王菲"}], "album_name": "唱游"},
        ]
    )

    assert [s.title for s in songs] == ["晴天", "红豆"]
    assert songs[0].duration_ms == 269_000
    assert songs[1].artist == "王菲"


def test_import_qq_playlist_fixture():
    songs = import_qq_playlist(Path(__file__).parent / "test_playlist.json")

    assert len(songs) == 30
    assert songs[0].title == "晴天"
    assert songs[0].artist == "周杰伦"


def test_import_csv_directory_merges_duplicate_playlist_tags(tmp_path):
    (tmp_path / "Pure.csv").write_text(
        "Title,Artist,Album\nThe Song,The Artist,First Album\n",
        encoding="utf-8",
    )
    (tmp_path / "Silence.csv").write_text(
        "Title,Artist,Album\nThe Song,The Artist,\nAnother Song,Another Artist,Second Album\n",
        encoding="utf-8",
    )

    songs = import_csv_playlists(tmp_path)
    by_title = {song.title: song for song in songs}

    assert len(songs) == 2
    assert by_title["The Song"].album == "First Album"
    assert by_title["The Song"].tags == ["Pure", "Silence"]
    assert by_title["Another Song"].artist == "Another Artist"


def test_store_song_and_feedback_roundtrip(tmp_path):
    store = Store(tmp_path / "songs.db")
    song = Song(
        title="Wish You Were Here",
        artist="Pink Floyd",
        album="Wish You Were Here",
        netease_id=123,
        genres=["rock"],
        tags=["classic rock"],
    )

    store.upsert_song(song)
    loaded = store.get_song(123)

    assert loaded is not None
    assert loaded.title == song.title
    assert loaded.genres == ["rock"]
    assert store.song_count() == 1


def test_recommendation_card_matches_frontend_shape(tmp_path):
    executor = ToolExecutor(Store(tmp_path / "songs.db"), object(), NeteaseConfig())
    rec = Recommendation(
        song=Song(
            title="Creep",
            artist="Radiohead",
            album="Pablo Honey",
            netease_id=456,
            duration_ms=238_000,
        ),
        reason="Matches the requested mood.",
        confidence=0.8,
        matched_dimensions=["Emotion"],
    )

    card = executor._recommendation_card(rec)

    assert card["song"]["id"] == 456
    assert card["song"]["title"] == "Creep"
    assert card["reason"] == "Matches the requested mood."
    assert card["confidence"] == 0.8
    assert card["is_exploratory"] is False
    assert card["matched_dimensions"] == ["Emotion"]


def test_external_song_id_is_stable_and_negative():
    first = external_song_id("itunes", "Everything In Its Right Place", "Radiohead")
    second = external_song_id("itunes", "everything in its right place", "radiohead")

    assert first == second
    assert first < 0


def test_itunes_discovery_track_mapping(tmp_path):
    discovery = ITunesDiscovery(Store(tmp_path / "songs.db"))

    song = discovery._song_from_result(
        {
            "trackName": "Svefn-g-englar",
            "artistName": "Sigur Rós",
            "collectionName": "Ágætis byrjun",
            "primaryGenreName": "Alternative",
            "trackTimeMillis": 600000,
            "trackViewUrl": "https://music.apple.com/us/album/svefn-g-englar/1440763786",
            "previewUrl": "https://audio-ssl.itunes.apple.com/preview.m4a",
        }
    )

    assert song.title == "Svefn-g-englar"
    assert song.artist == "Sigur Rós"
    assert song.album == "Ágætis byrjun"
    assert song.netease_id < 0
    assert song.genres == ["Alternative"]
    assert song.tags == ["iTunes", "外部发现", "试听"]
    assert song.duration_ms == 600000


def test_qq_music_search_url_uses_title_and_artist():
    song = Song(title="晴天", artist="周杰伦")

    url = qq_music_search_url(song)

    assert url.startswith("https://y.qq.com/n/ryqq/search?w=")
    assert "%E6%99%B4%E5%A4%A9" in url
    assert "%E5%91%A8%E6%9D%B0%E4%BC%A6" in url
