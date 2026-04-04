# automated youtube shorts video generator

give it a topic. it writes the script, generates images, records the voiceover, syncs captions, and produces a ready-to-upload short — automatically.

topic discovery can also run on autopilot: the pipeline can scrape reddit, news feeds, and trending sources to find topics without any input from you.

```
python -m verticals run --news "artemis ii crew just launched to the moon" --niche science
```

that one command does everything below, automatically.

---

## what it does

| stage | what happens |
|-------|-------------|
| **research** | searches duckduckgo for real facts about your topic |
| **script** | an llm writes a 60–90 second hook-driven voiceover script |
| **b-roll** | generates ai images via gpt-image-1 (primary) → gemini imagen (fallback) → solid colour |
| **voiceover** | text-to-speech via sarvam ai (indian voices), elevenlabs (premium), or edge tts (free) |
| **captions** | whisper generates word-level timestamps, burns animated subtitles into video |
| **music** | picks a mood-matched background track and auto-ducks under the voice |
| **assemble** | ffmpeg combines everything with ken burns zoom/pan effects |
| **upload** | posts to youtube (private by default) with title, tags, and description |

---

## how to try it

**step 1 — install**
```bash
git clone https://github.com/03shraddha/reel-generator.git
cd reel-generator
pip install -r requirements.txt
```

**step 2 — add your api keys**

create a `.env` file in the project root (already gitignored):

```env
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
OPENAI_API_KEY=
NEWSAPI_KEY=
ELEVENLABS_API_KEY=
SARVAM_API_KEY=          # enables indian-language voices (auto-selected when set)
```

the pipeline auto-loads `.env` at startup — no `python-dotenv` install or manual `export` needed.

or use the first-run setup wizard, or create `~/.verticals/config.json` manually.

> ⚠️ never commit `.env` or `config.json` — both are already in `.gitignore`

**step 3 — generate a video**
```bash
# full pipeline — draft + produce + upload
python -m verticals run --topic "your topic here" --niche tech

# just write the script first (dry run)
python -m verticals draft --topic "your topic here" --niche tech

# produce from a saved draft
python -m verticals produce --draft ~/.verticals/drafts/<id>.json --lang en
```

---

## api keys you'll need

| key | what it's for | free tier? |
|-----|--------------|------------|
| `ANTHROPIC_API_KEY` | script writing (claude) | no — ~$0.02/video |
| `GEMINI_API_KEY` | script writing fallback + thumbnail (primary) + b-roll (fallback) | yes |
| `OPENAI_API_KEY` | b-roll images (primary via gpt-image-1) + thumbnail (fallback) | no — ~$0.04/video |
| `SARVAM_API_KEY` | indian-language voiceover (bulbul:v3) | free tier available |
| `ELEVENLABS_API_KEY` | premium voiceover | optional |

**image generation priority:**
- b-roll: `gpt-image-1` → `gemini imagen` → solid-colour fallback
- thumbnail: `gemini imagen` → `gpt-image-1` fallback

tts priority when auto-detected: `sarvam` → `elevenlabs` → `edge` → `say`

edge tts (voiceover) is completely free with no key needed.

---

## run it for free

```bash
python -m verticals run \
  --topic "your topic" \
  --niche general \
  --provider gemini \
  --voice edge
```

uses gemini free tier for the script + b-roll images + edge tts for voice. total cost: $0.

---

## niche profiles

niche profiles shape the tone, visuals, and music of every video. built-in options:

`tech` `science` `gaming` `finance` `fitness` `cooking` `travel` `true_crime` `politics` `entertainment` `sports` `fashion` `education` `motivation` `comedy` `general`

```bash
python -m verticals run --topic "headline" --niche cooking
```

or build your own by dropping a yaml file in `niches/`. see `niches/tech.yaml` for the format.

> the `pace` field in a niche yaml can be a plain number (`1.15`) or a descriptive string (`"moderate, approximately 150 words per minute"`) — the pipeline coerces it to a float automatically before passing it to the sarvam api.

---

## useful flags

| flag | what it does |
|------|-------------|
| `--niche NAME` | pick a niche profile (default: general) |
| `--provider NAME` | llm: claude, gemini, openai, ollama |
| `--voice NAME` | tts: sarvam, elevenlabs, edge, say |
| `--lang CODE` | language: en, hi, es, pt, de, fr |
| `--dry-run` | write the script only, skip video production |
| `--force` | redo all stages even if already done |

---

## cost per video

| setup | cost |
|-------|------|
| claude + gpt images + edge tts | ~$0.06 |
| gemini only | ~$0.00 |
| ollama (local) + edge tts | $0.00 |

---

## requirements

- python 3.10+
- ffmpeg installed and on your path
- at least one llm api key (or ollama running locally)

---

mit license
