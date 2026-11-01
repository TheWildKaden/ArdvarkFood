# ArdvarkFood

## Your own AI image generator

The **Make images** tab runs Stability AI's open-weight SD-Turbo model directly
inside this Codespace. Image prompts and generated images stay in the local app;
image generation does not use ChatGPT, an external image API, or an API key.
Generated PNGs are saved to `.generated/` in the workspace and can be downloaded
from the app.

This is a self-hosted application using an existing open-weight model, not a
model trained from scratch. The model weights are downloaded from Hugging Face
the first time you generate an image and cached for later runs. Review SD-Turbo's
model card and usage terms in [SOURES.TXT](./SOURES.TXT). SD-Turbo is designed
for 512 × 512 images and one to four inference steps; higher step counts take
longer.

### Install the local image model dependencies

This Codespace has no NVIDIA GPU, so use the PyTorch CPU build:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-image-generator.txt
```

The first install downloads the runtime packages. The first generated image
downloads the model weights and needs an internet connection and enough free
disk space. CPU generation is slower than a compatible GPU. For Codespaces with
a GPU, install the matching PyTorch build from the official
[PyTorch installation selector](https://pytorch.org/get-started/locally/) before
installing the image-generator requirements.

### Run the app in a Codespace

Start the app from the repository root:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open the forwarded port 8000 in the Codespaces **Ports** tab. Codespaces also
detects the localhost address and provides a link to the app.

### Chat

The separate **Chat** tab keeps the existing AI Buddy chat feature. It uses an
OpenAI-compatible chat provider and needs a provider API key. Image generation
is a separate locally run model and does not use those chat settings.

Chat configuration:

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_API_KEY` | — | Chat provider API key. `OPENAI_API_KEY` is also accepted. |
| `AI_BASE_URL` | `https://api.openai.com/v1` | Chat provider API base URL. |
| `AI_MODEL` | `gpt-5.5` | Model available to your chat provider account. |
| `AI_SYSTEM_PROMPT` | Buddy's built-in assistant instructions | Optional chat behavior instructions. |

Keep the Codespace port private, never put API keys in frontend code or
committed files, and check provider pricing before using the separate chat
feature.

### API

- `POST /api/images/generate` generates and saves a PNG using the local model.
- `GET /api/images/status` reports the local model's load status.
- `GET /api/images/{filename}` serves a generated PNG.
- `POST /api/chat` sends a request to the separately configured chat provider.
- `GET /api/health` reports whether the web server is running.

The app reports missing dependencies or model loading errors instead of
returning a pretend generated image.
