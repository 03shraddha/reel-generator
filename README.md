# Verticals - AI YouTube Shorts on Autopilot

One command. One topic. One ready-to-upload Short.

```bash
python -m verticals run --news "Apple CEO Tim Cook steps down" --niche tech
```

That's it. The pipeline does everything else automatically.

---

## What It Does

| Stage | What Happens | Who Does It |
|-------|-------------|-------------|
| Script | LLM writes a 60-90s hook-driven voiceover script | Claude / OpenAI / Gemini / Ollama |
| B-roll | Generates AI images for each scene | GPT-Image-2 -> GPT-Image-1 -> solid color |
| Voiceover | Converts script to speech | Sarvam -> ElevenLabs -> Edge TTS -> say |
| Captions | Whisper burns animated subtitles into video | OpenAI Whisper |
| Music | Picks a mood-matched track and auto-ducks under voice | Local tracks |
| Assembly | FFmpeg combines everything with Ken Burns zoom/pan effects | FFmpeg |
| Upload | Posts to YouTube (private by default) | YouTube Data API v3 |

Every stage has a fallback. If one provider fails, the next one kicks in automatically.

---

## Getting Started

**Step 1 - Install**

```bash
git clone https://github.com/03shraddha/reel-generator.git
cd reel-generator
pip install -r requirements.txt
```

You also need ffmpeg on your PATH. Download it from [ffmpeg.org](https://ffmpeg.org/download.html).

**Step 2 - Add API Keys**

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=           # required - images + script + captions
ANTHROPIC_API_KEY=        # optional - better scripts with Claude
ELEVENLABS_API_KEY=       # optional - premium voice
SARVAM_API_KEY=           # optional - Indian language voices
EXA_API_KEY=              # optional - trending topic discovery
```

The pipeline auto-loads `.env` at startup. No extra setup needed.

> Never commit your `.env` file. It is already in `.gitignore`.

**Step 3 - Make a Video**

```bash
# Full pipeline: script + video + upload
python -m verticals run --news "your topic here" --niche tech

# Just write the script (dry run, no video)
python -m verticals draft --news "your topic here" --niche tech

# Produce video from a saved draft
python -m verticals produce --draft ~/.verticals/drafts/<id>.json

# Upload a produced video
python -m verticals upload --draft ~/.verticals/drafts/<id>.json
```

---

## API Keys

| Key | Used For | Free Tier |
|-----|---------|-----------|
| `OPENAI_API_KEY` | Images (GPT-Image-2) + script + Whisper captions | No - around $0.04/video |
| `ANTHROPIC_API_KEY` | Better quality scripts via Claude | No - around $0.02/video |
| `ELEVENLABS_API_KEY` | Premium human-sounding voice | Optional |
| `SARVAM_API_KEY` | Indian language voices (Hindi etc.) | Free tier available |
| `EXA_API_KEY` | Web search for trending topics | Free tier available |

**Run it for free** using Gemini + Edge TTS (no images but zero cost):

```bash
python -m verticals run --news "your topic" --niche general --provider gemini --voice edge
```

---

## Cost Per Video

| Setup | Cost |
|-------|------|
| Claude + GPT-Image-2 + Edge TTS | ~$0.06 |
| OpenAI only | ~$0.04 |
| Gemini + Edge TTS | $0.00 |
| Ollama (local) + Edge TTS | $0.00 |

---

## Niche Profiles

Niches shape the tone, visuals, music, and script pacing for every video. Pick one or build your own.

| Niche | Best For |
|-------|---------|
| `tech` | Product launches, AI news, startup stories |
| `finance` | Markets, crypto, personal finance tips |
| `science` | Space, biology, discovery news |
| `fitness` | Workout tips, health studies |
| `gaming` | Game releases, esports |
| `true_crime` | Crime stories, investigations |
| `politics` | Policy news, elections |
| `motivation` | Quotes, mindset, success stories |
| `travel` | Destination highlights, tips |
| `general` | Anything else |

```bash
# See all available niches
python -m verticals niches
```

To create a custom niche, drop a `.yaml` file in the `niches/` folder. See `niches/tech.yaml` for the format.

---

## CLI Flags

| Flag | What It Does |
|------|-------------|
| `--news "headline"` | Topic or news headline to make a video about |
| `--niche NAME` | Content niche (default: general) |
| `--provider NAME` | LLM for script: claude, gemini, openai, ollama |
| `--voice NAME` | TTS engine: sarvam, elevenlabs, edge, say |
| `--lang CODE` | Language: en, hi, es, pt, de, fr, ja, ko |
| `--dry-run` | Write the script only, skip video production |
| `--force` | Redo all stages even if already done |
| `--discover` | Auto-search for trending topics instead of giving one |
| `--auto-pick` | Let the LLM pick the best trending topic for you |

---

## Trending Topics (Auto-Discovery)

No topic idea? Let the pipeline find one:

```bash
# Shows top 5 trending topics and lets you pick
python -m verticals run --niche tech --discover

# LLM picks the best one automatically
python -m verticals run --niche tech --discover --auto-pick

# Just browse topics without making a video
python -m verticals topics --niche tech --limit 10
```

---

## How It Saves Progress

Each pipeline run saves a draft file in `~/.verticals/drafts/<id>.json`. If a stage fails (say, the upload errors out), you can resume from exactly where it stopped without paying for the earlier stages again.

```bash
# Resume a failed run from where it left off
python -m verticals produce --draft ~/.verticals/drafts/1234567890.json
python -m verticals upload --draft ~/.verticals/drafts/1234567890.json
```

---

## Requirements

- Python 3.10+
- ffmpeg on your PATH
- At least one LLM API key (or Ollama running locally)

---

## Credits

Inspired by [youtube-shorts-pipeline](https://github.com/rushindrasinha/youtube-shorts-pipeline) by @rushindrasinha.

---

MIT License
