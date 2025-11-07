# Syker Data Processor

Serverless web application that converts Syker Systems `.dtl` telemetry files into Excel workbooks.

## Project structure

- `backend/` – core processing library and FastAPI app
- `api/` – Vercel serverless entry points for the backend
- `app/`, `components/`, `styles/` – Next.js frontend (App Router)
- `tests/` – automated test suites
- `requirements.txt` – Python dependencies for the API
- `package.json` – Node dependencies for the frontend

## Getting started

1. **Install Python deps**

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements-dev.txt
   ```

2. **Install Node deps**

   ```bash
   npm install
   ```

3. **Run locally**

   ```bash
   # Terminal 1 – FastAPI (auto-reloads)
   uvicorn backend.app:app --reload

   # Terminal 2 – Next.js frontend
   npm run dev
   ```

4. Open http://localhost:3000 to access the UI. Configure the frontend `.env.local` file if you need to point to a different API origin (defaults to `http://localhost:8000`).

## Testing & linting

```bash
pytest
ruff check
npm run lint
```

## Deployment

1. Push to GitHub and connect the repository to Vercel.
2. Set the Python build command to `pip install -r requirements.txt`.
3. Set environment variables in Vercel:
   - `NEXT_PUBLIC_API_BASE_URL` (optional – leave unset to use same origin)
4. Verify serverless logs and run an end-to-end upload once deployed.

See `docs/DEPLOYMENT.md` (to be written) for detailed deployment guidance.


