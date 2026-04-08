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

## credits

inspired by [youtube-shorts-pipeline](https://github.com/rushindrasinha/youtube-shorts-pipeline) by [@rushindrasinha](https://github.com/rushindrasinha).

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

---

## Interview Reference

### Overview

Reel Generator is a CLI pipeline that produces a complete YouTube Short from a single topic string — research, script, images, voiceover, captions, music, assembly, and upload, fully automated.

**Pipeline at a glance:**

| Stage | What happens | Primary provider |
|-------|-------------|-----------------|
| Research | Searches DuckDuckGo for real facts | DuckDuckGo scrape |
| Script | LLM writes a 60–90s hook-driven voiceover script | Claude → Gemini → OpenAI → Ollama |
| B-roll | Generates AI images per scene | GPT-image-1 → Gemini Imagen → solid color |
| Voiceover | Converts script to speech | Sarvam → ElevenLabs → Edge TTS → say |
| Captions | Whisper produces word-level timestamps; subtitles burned in | OpenAI Whisper |
| Music | Mood-matched background track, auto-ducked under voice | Local tracks |
| Assembly | FFmpeg combines everything with Ken Burns effects | FFmpeg |
| Upload | Posts to YouTube (private by default) | YouTube Data API v3 |

Every stage has a **fallback chain** — the same codebase runs from $0.00 (Gemini free tier + Edge TTS) to ~$0.06/video (Claude + GPT images) depending on which keys are configured.

**Niche profiles** (YAML files) parameterize tone, visual style, music mood, and script pacing per content category — no code changes needed to add a new content type.

---

### Narrative

**Where it started — a Claude Code skill**
- v1 was a structured prompt (a "skill") that invoked existing tools — not a standalone application
- The first real architectural decision was repackaging it as `python -m verticals`: a proper CLI entry point that separated config from execution and made the pipeline testable

**Security audits forced the modular architecture**
- Before v2 features were added, two independent security audits arrived as PRs in the same development window
- Seven vulnerabilities found: a TOCTOU race condition in file handling, unsanitized inputs to subprocess calls, missing dependency version pins
- Fixing these required breaking the monolithic v1 script into discrete, auditable modules
- V2's modular design was partly intentional and partly forced — the security fixes made it structurally necessary

**V2: from single-use script to resumable pipeline**
- Full rewrite with captions, background music, topic sourcing, thumbnails, and **draft-resume**
- Draft-resume was the key operational insight:
  - An 8-stage pipeline accumulates 2–4 minutes of API calls
  - If stage 7 fails, restarting from stage 1 is expensive and wasteful
  - Fix: checkpoint each completed stage to disk; resume picks up exactly where it failed

**V3: niche intelligence engine**
- Instead of hardcoding content style per niche in code, V3 moved everything into YAML config files
- Adding a new niche (e.g., Hindi regional news) = drop a YAML file in `niches/`, no code change
- This surfaced a bug immediately:
  - The `pace` field in niche YAMLs was documented as a float (`1.15`)
  - Some profiles were written with descriptive strings ("moderate, approximately 150 words per minute")
  - The Sarvam TTS API rejected non-numeric pace values at runtime
  - Fix: add explicit float coercion before the value reaches the API — applied after the fact

**Sarvam TTS integration**
- Added in v3 for Indian-language content: `bulbul:v3`, `ishita` voice
- A voice mismatch bug appeared after merge:
  - The niche YAML specified one speaker name
  - The Sarvam client was initialized with a different default
  - The integration was tested in isolation but not through the full niche-profile code path
  - Required a follow-up fix commit to align the two

---

### Technical Reflection

**Constraints**

| Constraint | What it means in practice |
|-----------|--------------------------|
| 8 sequential API stages | Total latency: 2–4 minutes per video; image gen alone is 30–60s per frame |
| `bulbul:v3` speaker names are a fixed list | Invalid names fail at runtime with no descriptive error |
| YAML profiles have no schema validation | Malformed fields (wrong type, missing keys) cause runtime errors, not load-time warnings |
| DuckDuckGo research is a scrape, not an API | No rate limit handling; fails silently if the page structure changes |
| YouTube upload is last in the chain | OAuth failures and quota errors surface only after all prior stages have succeeded |

**How key problems were resolved**

| Problem | Solution |
|---------|---------|
| Pipeline failure requiring full restart | Checkpoint each stage to disk; `--resume` picks up from the last completed stage |
| High cost for content iteration | `--dry-run` runs script generation only — validate the script before paying for images and video |
| Provider unavailability / rate limits | Fallback chain at every stage — degrades gracefully rather than failing hard |
| YAML `pace` field accepting wrong types | Explicit float coercion before the value reaches the Sarvam API |
| Voice mismatch between YAML and client | Align niche YAML speaker name with the client initialization; test through the full code path |

**What breaks at scale**
- **Latency**: 8 sequential stages means no video is ready in under 2 minutes even with fast providers — there's no parallelism at the stage level
- **Whisper caption sync**: accuracy degrades on non-English content; `--lang hi` and other Indian language flags will produce caption timing errors at scale
- **YouTube OAuth**: credentials expire and quota refreshes daily — silent failures at the upload stage after all compute has already been spent
- **YAML schema drift**: as the niche library grows, profiles written at different times will have inconsistent fields, producing subtly different outputs with no error to diagnose

**Maintenance risks**
- Each provider in each fallback chain has its own API versioning and deprecation timeline — `gpt-image-1`, `bulbul:v3` speaker names, Whisper model versions can all change independently
- No schema validator runs at startup on YAML profiles — breakage only surfaces at the stage that reads the malformed field
- The pipeline has no observability layer: if a stage produces subtly wrong output (bad image, off-pace audio), there's no automated check — the user only sees it in the final video
