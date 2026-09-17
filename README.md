# Gerbert

Gerbert is a small Flask + React dashboard for seeing when tracks were added to your Spotify playlists.

It connects to Spotify, lets you pick playlists, and turns their add history into charts and a few lightweight insights.

## What it does

- Spotify login with playlist and top-track data kept on the backend
- Playlist search and multi-selection
- Monthly and seasonal add-history charts
- Playlist comparisons and totals
- Activity insights and Spotify taste matching

## Run it locally

You’ll need Python 3.10+, Node.js 20.19+, and a Spotify developer application.

Copy `backend/.env.example` to `backend/.env` and fill in your Spotify app values:

```text
SPOTIPY_CLIENT_ID=your-client-id
SPOTIPY_CLIENT_SECRET=your-client-secret
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
APP_HOST=127.0.0.1
PORT=8888
```

Add the same redirect URI to your Spotify Developer Dashboard. Spotify requires the URI to match exactly; use `127.0.0.1`, not `localhost`.

Start the backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

In another terminal, start the frontend:

```powershell
cd frontend
npm ci
npm start
```

Open `http://localhost:3000`.

The app is designed for personal, local use. Spotify credentials and the token cache stay on the backend, and generated files such as `.env`, `.cache`, `node_modules`, and `frontend/build` are ignored by Git.
