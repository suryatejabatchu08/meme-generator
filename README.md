# Meme Generator

A lightweight FastAPI service that uses Google Gemini/Gemma to generate meme captions from a conversation, selects a best-fit meme template from Imgflip, and produces a final meme image URL using the Imgflip API.

This repository is a minimal production-friendly service that demonstrates integrating a generative LLM with a third-party image meme API to produce contextual memes automatically.

## Quick overview

- Language: Python 3.11+
- Web framework: FastAPI
- HTTP client: httpx (async)
- LLM: Google Generative AI (Gemini/Gemma via `google.generativeai`)
- Meme image generation: Imgflip API
- Environment: configured via `.env` (Dotenv)

Key files

- `main.py` — main FastAPI application and core flow (fetch templates, generate captions, choose template, create meme)
- `bot_prompt.py` — bot personality prompts used by the LLM (customize per bot id)
- `requirements.txt` — Python dependencies
- `.github/workflows/main.yml` — GitHub Actions workflow to build and deploy a Docker image to Google Cloud Run

## Environment & secrets

Create a `.env` file in the project root (do NOT commit this file). Required environment variables:

- `GEMINI_API_KEY` — API key for Google Generative AI (Gemini/Gemma). Required for `google.generativeai` client.
- `IMGFLIP_USERNAME` — Imgflip account username (for captioning API).
- `IMGFLIP_PASSWORD` — Imgflip account password.

Example `.env` (local only):

```
GEMINI_API_KEY=ya29.xxxxxx
IMGFLIP_USERNAME=your_imgflip_username
IMGFLIP_PASSWORD=your_imgflip_password
```

Note: Keep keys and credentials secret. Use your platform's secrets manager in production (Cloud Run, GitHub Secrets, etc.).

## Install dependencies (local)

Install the project dependencies into a virtual environment. Example using PowerShell on Windows:

```
python -m venv .venv; .\.venv\Scripts\Activate; pip install --upgrade pip; pip install -r requirements.txt
```

## Run locally

Start the FastAPI app with Uvicorn:

```
.\.venv\Scripts\Activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open the interactive docs at http://localhost:8000/docs to test the endpoint.

## API

POST /generate-meme

Description: Generates meme captions using the LLM, selects a template using Gemini, and creates the final meme image via Imgflip.

Request JSON body:

```json
{
	"previous_conversation": ["User: I'm having a rough day", "Bot: I'm sorry to hear that. Tell me more."],
	"bot_id": "default"
}
```

Fields:
- `previous_conversation`: array of strings representing recent chat lines or context the bot should consider
- `bot_id`: identifier used by `bot_prompt.py` to load the bot personality/prompt

Example curl (Linux/macOS) or use PowerShell's Invoke-RestMethod on Windows:

```
# PowerShell example
$body = @{ previous_conversation = @('User: I failed my exam', 'Bot: That sucks — want some help?'); bot_id = 'default' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/generate-meme -Body $body -ContentType 'application/json'
```

Successful response JSON:

```json
{
	"meme_url": "https://i.imgflip.com/xxxxx.jpg",
	"template_name": "Distracted Boyfriend",
	"top_text": "...",
	"bottom_text": "..."
}
```

If the service cannot fetch templates or generate an image, the response will contain an `error` field with a short message.

## How the flow works (high-level)

1. `fetch_templates()` calls Imgflip's `get_memes` API to retrieve available templates.
2. `improvise_meme_text()` calls the Gemma model to produce short JSON containing `top_text` and `bottom_text` based on the prior conversation and the bot personality (from `bot_prompt.py`).
3. `suggest_template()` calls Gemini to intelligently pick a template name from the fetched list (it tries exact match, partial match, and falls back to random).
4. `generate_meme_imgflip()` calls Imgflip's `caption_image` endpoint to create the meme and return the hosted meme URL.

## Deployment

This repo contains a GitHub Actions workflow `.github/workflows/main.yml` that builds a Docker image and deploys it to Google Cloud Run. The workflow expects the following GitHub secrets:

- `GCP_SA_KEY` — service account JSON for GCP with permissions to push images and deploy to Cloud Run
- `IMGFLIP_USERNAME`, `IMGFLIP_PASSWORD`, `GEMINI_API_KEY`

The workflow builds a Docker image and pushes it to Artifact Registry, then deploys to Cloud Run with the required environment variables.

Dockerfile

The included `Dockerfile` builds the Python app. You can build and run locally with Docker:

```
# build
docker build -t meme-generator:local .
# run (map port 8000)
docker run -e GEMINI_API_KEY="${env:GEMINI_API_KEY}" -e IMGFLIP_USERNAME="${env:IMGFLIP_USERNAME}" -e IMGFLIP_PASSWORD="${env:IMGFLIP_PASSWORD}" -p 8000:8000 meme-generator:local
```

## Configuration and customization

- `bot_prompt.py`: Add or modify bot personalities keyed by `bot_id`. This file should return the prompt used to instruct the LLM about the bot's voice/tone.
- LLM models: `main.py` uses two helpers: `call_gemini_api()` and `call_gemma_api()` which target `gemini-1.5-flash` and `gemma-3n-e2b-it`. You can change the model names or generation settings there.
- Template selection behavior: `suggest_template()` contains rules and fallbacks and prints debug info; update it if you want different selection heuristics.

## Testing and sanity checks

- Verify network access to Imgflip (api.imgflip.com) and that the Imgflip account is valid.
- Verify `GEMINI_API_KEY` is valid; invalid keys will cause the generative calls to fail.
- Use the interactive FastAPI docs at `/docs` to quickly exercise the endpoint.

## Troubleshooting

- "Could not fetch meme templates": network issue to Imgflip or Imgflip API changed. Use `curl https://api.imgflip.com/get_memes` to inspect.
- LLM errors / timeouts: inspect logs for exceptions. Increase generation timeouts or reduce temperature if outputs are inconsistent.
- Template selection mismatch: the model may return a template name with extra text. The code tries exact/partial matches and falls back to random.