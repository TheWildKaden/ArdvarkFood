# ArdvarkFood

## AI Buddy

This repository includes a live, general-purpose AI chat app. The FastAPI
server runs inside your GitHub Codespace and sends chat requests from the
server to an OpenAI-compatible AI provider. Your API key stays on the server;
it is never sent to the browser or committed to the repository.

### Configure the AI provider

Create an API key with your AI provider, then add it to your Codespace as a
secret named `AI_API_KEY`:

1. In GitHub, open **Settings → Secrets and variables → Codespaces**.
2. Select **New repository secret**, name it `AI_API_KEY`, and paste your key.
3. Restart the Codespace so the secret is available in its environment.

OpenAI is used by default. To use another OpenAI-compatible provider, add
the corresponding variables in Codespaces settings. The chat backend uses the
standard [OpenAI Chat Completions endpoint](https://platform.openai.com/docs/api-reference/chat/create)
so compatible providers can use the same integration:

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_API_KEY` | — | Provider API key. `OPENAI_API_KEY` is also accepted. |
| `AI_BASE_URL` | `https://api.openai.com/v1` | Provider's API base URL. |
| `AI_MODEL` | `gpt-5.5` | Model name available to your provider account. |
| `AI_SYSTEM_PROMPT` | Buddy's built-in assistant instructions | Optional personality and behavior instructions. |

Provider usage may incur charges under your provider account's pricing and
limits. Keep the Codespace port private, and never put API keys in frontend
code, chat messages, or committed files.

### Run in a Codespace

From the repository root, start the app:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open the forwarded port 8000 in the Codespaces **Ports** tab. Codespaces also
detects the printed localhost address and provides a link to the app. If the
dependencies are not installed yet, run `pip install -r requirements.txt`
first.

Chat requests go to `/api/chat`; `/api/health` reports whether the web server
is running. The app shows provider and configuration errors instead of
generating pretend replies.
