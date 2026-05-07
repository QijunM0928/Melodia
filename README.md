# Melodia

Personal AI music agent that understands *why* you like a song.

## Setup

```bash
cd ~/Projects/Melodia
uv sync
```

## Configuration

Edit `~/.melodia/config.yaml`:

```yaml
netease:
  base_url: "http://localhost:3000"
  cookie: ""  # MUSIC_U cookie

llm:
  model: "claude-sonnet-4-20250514"  # or gpt-4o, ollama/llama3
  api_key: ""  # or set OPENAI_API_KEY / ANTHROPIC_API_KEY env var
```

## Usage

```bash
# Import QQ Music playlist
melodia import-playlist --source qqmusic --file playlist.json

# Import CSV playlists from a directory without Netease matching
melodia import-playlist --source csv --file /path/to/songlist --skip-match

# Build vector index
melodia index

# Expand the recommendation pool with iTunes candidates
melodia discover --query "dream pop, quiet late night" --limit 30

# Start web UI
cd frontend && npm run build && cd ..
melodia serve
```

`melodia discover` uses the public iTunes Search API, so no API key is required.
It saves external candidates into the local library with `iTunes` tags so chat
recommendations can mix familiar local matches with new songs outside your CSVs.

The web UI opens as a discovery workspace with three recommendation lanes:
familiar local matches, iTunes fresh finds, and riskier adjacent picks. The
direction input at the top refreshes the whole workspace instead of acting like
a one-off chatbot prompt.
