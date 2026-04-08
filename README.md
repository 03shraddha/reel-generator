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

Reel Generator is a command-line pipeline that produces YouTube Shorts end-to-end from a single topic string. It orchestrates eight sequential stages: web research (DuckDuckGo), LLM script writing, AI image generation, TTS voiceover, Whisper caption sync, background music selection, FFmpeg assembly, and YouTube upload. Every stage has a provider fallback chain — Claude → Gemini → OpenAI → Ollama for LLM; Sarvam → ElevenLabs → Edge TTS for voice; GPT-image-1 → Gemini Imagen → solid color for images — so the same codebase operates from $0.00 (Gemini free tier + Edge TTS) to ~$0.06 per video (Claude + GPT images). Niche profiles defined in YAML files parameterize tone, visual style, music mood, and script pacing per content category without code changes.

---

### Narrative

The project originated as a **Claude Code skill** — a structured prompt that invoked existing tools rather than a standalone application. Repackaging it as an importable Python module (`python -m verticals`) was the first architectural decision: it created a clean entry point, separated configuration from execution, and made the pipeline testable as a unit.

Before that repackaging could advance, two independent security audits surfaced seven vulnerabilities: a TOCTOU race condition in file handling, unsanitized inputs passed to subprocess calls, and missing dependency version pins. Both audits arrived as pull requests within the same development window, before v2 features were added. The effect was structural — fixing the vulnerabilities required breaking the monolithic script into discrete, auditable modules. V2's modular architecture was partly a feature choice and partly a consequence of making the v1 code defensible.

V2 was a full rewrite. The additions — captions, background music, topic sourcing, thumbnails, and a draft-resume system — transformed a single-use script into a resumable pipeline. The draft-resume capability reflects a specific operational insight: an eight-stage pipeline that accumulates 2–4 minutes of API latency can fail at any stage, and restarting from scratch is expensive. Checkpointing each completed stage locally converts a catastrophic failure into a recoverable one.

V3 introduced the **niche intelligence engine**: YAML-configurable profiles that parameterize every content-specific variable. The decision to externalise these into configuration rather than branching logic in code means adding a new niche (e.g., a regional news profile for Hindi content) requires a YAML file, not a code change. This design choice surfaced a post-hoc bug: the `pace` field in niche YAMLs was documented as a float but the system accepted descriptive strings ("moderate, approximately 150 words per minute") — the coercion was added after the fact when the Sarvam API rejected non-numeric pace values.

Sarvam AI TTS was added in v3 specifically for Indian-language content using `bulbul:v3` with the `ishita` voice. A subsequent commit corrected a voice mismatch where the niche YAML referenced one speaker name and the Sarvam client was initialized with another — the integration worked in isolation but had not been tested through the full niche-profile code path before merge.

---

### Technical Reflection

**Constraints encountered.** The eight-stage sequential pipeline accumulates API latency at each step — image generation alone can take 30–60 seconds per frame, and a typical Short requires 4–6 images. The Sarvam `bulbul:v3` speaker name set is fixed; using a name valid in v2 (or an unsupported string) fails at runtime without a descriptive error. YAML niche profiles lack schema validation, so malformed fields produce runtime errors rather than load-time warnings.

**Resolution patterns.** The provider fallback hierarchy is the central resilience mechanism: each stage degrades gracefully through alternatives rather than failing hard when a primary provider is unavailable or rate-limited. Draft checkpointing converts pipeline failures from restart-from-zero events into resume-from-stage events. The `--dry-run` flag (script generation only) allows content iteration without incurring image or video production costs — useful for validating niche profiles before committing to full pipeline execution.

**Failure points under scale.** The YouTube upload step assumes valid OAuth credentials, sufficient API quota, and a private-by-default upload target — three independent failure surfaces that are not retried or surfaced clearly when they fail mid-pipeline after all prior stages have completed successfully. Whisper's caption timestamp accuracy degrades on non-English content; as `--lang hi` and other Indian language flags are used more widely, caption sync errors will become more frequent. The DuckDuckGo research stage scrapes a public interface rather than an official API — it has no rate limit handling and will fail silently if the search page structure changes.

**Long-term maintenance considerations.** Each provider in the fallback chains has independent API versioning, pricing, and deprecation timelines. The `gpt-image-1` endpoint name and the `bulbul:v3` speaker list are both subject to change without the pipeline having a validation step that would surface breakage before a user encounters it at runtime. As the niche YAML library grows, schema drift between profiles (inconsistent field names, missing required keys) will produce inconsistent outputs that are difficult to diagnose without a schema validator at load time.
