# Ecuery

Ecuery is a conversational environmental research tool. It lets people ask
plain-English questions about weather, air quality, natural hazards, and
long-term climate trends, then returns a direct answer, a chart, and links to
the underlying sources.

The project combines recent and historical environmental data, records data
provenance, and can anchor verification records on Solana so that results are
traceable. The local development setup uses in-memory demo data when Tiger
Data and Snowflake credentials are not configured.

## Run locally

You will need a recent version of Python, Node.js 20.9 or newer, and npm.

### 1. Start the API

From the repository root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create `backend/.env.local` and add a Gemini API key:

```dotenv
GEMINI_API_KEY=your_key_here
```

Then start the FastAPI server:

```bash
python main.py
```

The API runs at `http://127.0.0.1:8000`. You can confirm it is available at
`http://127.0.0.1:8000/health`.

### 2. Start the web app

In a second terminal, from the repository root:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open `http://localhost:3000`.

The default frontend configuration already points to the local API. Clerk keys
are optional for local development; add them to `frontend/.env.local` if you
want to test authentication.

## Optional services

Ecuery works with demo data by default. To use persistent, real data, configure
Tiger Data and Snowflake in `backend/.env.local`; setup details are in
`backend/tiger/README.md` and `backend/warehouse/README.md`. Redis, ElevenLabs,
and Solana credentials enable shared caching, generated speech, and on-chain
verification respectively.
