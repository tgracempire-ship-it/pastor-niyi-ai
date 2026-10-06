# Pastor Niyi AI

A public sermon study assistant for Pastor Niyi Adetiloye. One FastAPI service hosts the chat interface and API on Render. Questions are matched against the existing Chroma vector database, then Gemini generates an answer with sermon references.

## Embed the chat widget

Add this script just before `</body>` on the church website. It adds a floating chat button; on small screens, the open chat uses the full screen.

```html
<script src="https://pastor-niyi-ai.onrender.com/widget.js" defer></script>
```

To place the launcher at the bottom left, add `data-position="bottom-left"`:

```html
<script src="https://pastor-niyi-ai.onrender.com/widget.js" data-position="bottom-left" defer></script>
```

The widget is hosted by this service and calls its existing `/api/chat` endpoint. The church site does not need its own API key or backend changes.

## Deploy on Render

1. In Render, choose **New → Blueprint** and connect `tgracempire-ship-it/pastor-niyi-ai`.
2. Add your Gemini key as `GEMINI_API_KEY`. The shared sermon database folder URL is already set in `render.yaml`.
3. Make sure the Drive folder is accessible to anyone with the link, then deploy. Share the service’s `onrender.com` URL.

The app downloads the Drive folder on first use and locates `chroma.sqlite3` within it. You can set a ZIP URL as `SERMON_DB_URL` instead. Keep the Gemini key in Render environment variables; never put it in this repository or browser code.

The included Blueprint uses Render’s free web service plan. Its local files are temporary and may be cleared on restart; the app downloads the database again when needed. For a larger or frequently used service, add a persistent disk mounted at `/var/data`, then set `SERMON_DB_DIR=/var/data/sermon_vector_db`. Persistent disks require a paid Render service. Do not commit the vector database to GitHub.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Set `GEMINI_API_KEY` and `SERMON_DB_URL`, then run `uvicorn app:app --reload` and open `http://127.0.0.1:8000`.
