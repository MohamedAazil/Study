# Study Assistant

An AI study assistant for students, with read-only access for their parents and teachers. Product intent lives in [`Claude.md`](./Claude.md).

- **Timetable onboarding**: upload a timetable PDF or enter it manually.
- **To-do list**: tasks set by students or teachers, linked to subjects and timetable slots.
- **Document library**: textbooks, study materials and past papers stored in Supabase Storage.
- **Tutor chat**: RAG over textbooks/materials only, with citations that open the PDF at the cited page.
- **Examiner**: builds practice papers from past papers + mark schemes, then grades text/PDF answers and writes a per-topic focus report.
- **Parent reports**: an end-of-day job writes daily reports and sends them to parents in-app and/or by email.

## Architecture

```
frontend/  React + TypeScript + Vite ──(Supabase JWT)──▶ backend/  FastAPI
                │                                             │
                └── Supabase Auth (login) ◀───────────────────┤ verifies JWT (HS256 secret or JWKS)
                                                              ├── Supabase Postgres (service role + RLS)
                                                              ├── Supabase Storage  (bucket "documents")
                                                              ├── Pinecone (namespaces "materials" / "pastpapers")
                                                              ├── LLMs: OpenAI → Anthropic → Cohere (failover)
                                                              └── Resend (parent emails)
```

| Path | Purpose |
| --- | --- |
| `backend/app/main.py` | FastAPI app, CORS, optional in-process scheduler, `/health` |
| `backend/app/config.py` | Environment-driven settings (pydantic-settings) |
| `backend/app/auth.py` | Supabase JWT verification, `require_roles(...)`, parent/teacher access helpers |
| `backend/app/db/` | Supabase client and storage helpers |
| `backend/supabase/migrations/` | SQL schema, RLS policies, storage bucket |
| `backend/app/routers/` | `auth`, `timetable`, `tasks`, `documents`, `chat`, `exams`, `reports`, `notifications` |
| `backend/app/llm/` | `GenerationProvider` / `EmbeddingProvider` protocols, OpenAI/Anthropic/Cohere, retry + failover factory |
| `backend/app/ingestion/` | PDF text (pdfplumber → PyMuPDF), page-aware chunking, embeddings, Pinecone upsert, timetable parser |
| `backend/app/agents/rag_chat.py` | LangChain RAG chain over the `materials` namespace only |
| `backend/app/agents/examiner.py` | LangGraph graphs: retrieve → extract → select → adapt → finalise; grade → focus report → persist |
| `backend/app/notifications/` | `Notifier` interface, Resend implementation, end-of-day job, APScheduler hook |
| `backend/scripts/` | `seed.py`, `run_eod_job.py` |
| `frontend/src/lib/` | `api.ts` (typed client), `supabase.ts`, `auth.tsx` (session + role) |
| `frontend/src/pages/` | Login, Timetable, To-Do, Documents, Chat, Examiner, Parent dashboard |

### Key design points

- **Roles**: `student`, `teacher` or `parent`, set from signup metadata by a trigger on `auth.users`. Students own their data. Teachers can read all students and assign tasks to them. Parents can only *read* data of children linked through `parent_student_links`.
- **Authorization**: the backend uses the Supabase service-role key and enforces access in `app/auth.py`. RLS policies in the migration enforce the same rules for any direct anon-key/JWT access, so parents only see linked children's rows.
- **Citations**: chunks are split page by page, so every vector maps to exactly one page. Vector metadata includes `doc_id`, `page`, `storage_path` (plus `title`, `kind`, `owner_id`, `is_shared`, `text`). Chat returns `{doc_id, page, excerpt, storage_path}` and the frontend opens a signed URL in `react-pdf` at that page, with the excerpt highlighted.
- **Retrieval separation**: chat queries only `PINECONE_MATERIALS_NAMESPACE`, and the examiner queries only `PINECONE_PASTPAPERS_NAMESPACE`. Document kind picks the namespace: `textbook`/`material` go to materials and `past_paper` goes to pastpapers.
- **Exam totals**: questions are picked by a subset-sum over marks (preferring the requested difficulty). If no exact match exists, the LLM re-allocates marks and the mark scheme to hit `total_marks`.
- **Submissions**: `text` and typed `pdf` are supported. `image` exists in the DB enum but the API rejects it with 422 in v1.
- **LLM failover**: providers are tried in the order of `GENERATION_PROVIDERS` / `EMBEDDING_PROVIDERS`, with tenacity retries and exponential backoff on each one. An embedding provider whose dimension ≠ `EMBEDDING_DIMENSION` is skipped, so it can never write mixed-dimension vectors.

## Environment variables

Copy `backend/.env.example` → `backend/.env` and `frontend/.env.example` → `frontend/.env`.

### Backend (`backend/.env`)

| Variable | Required | Notes |
| --- | --- | --- |
| `SUPABASE_URL` | yes | `https://<project>.supabase.co` |
| `SUPABASE_ANON_KEY` | yes | Used by the seed script to sign in demo users |
| `SUPABASE_SERVICE_ROLE_KEY` | yes | Server-side only, never ship to the frontend |
| `SUPABASE_JWT_SECRET` | legacy only | Needed if the project signs JWTs with HS256; asymmetric keys are verified via JWKS |
| `SUPABASE_STORAGE_BUCKET` | | default `documents` (created by the migration) |
| `PINECONE_API_KEY` | yes | |
| `PINECONE_INDEX_NAME` | | default `study-assistant`. Created automatically (serverless, cosine) if missing |
| `PINECONE_CLOUD` / `PINECONE_REGION` | | default `aws` / `us-east-1` |
| `PINECONE_MATERIALS_NAMESPACE` / `PINECONE_PASTPAPERS_NAMESPACE` | | default `materials` / `pastpapers` |
| `EMBEDDING_DIMENSION` | | `3072` (native `text-embedding-3-large`). Use `1024` to allow Cohere as embedding fallback. Must match the index |
| `GENERATION_PROVIDERS` | | ordered, default `openai,anthropic,cohere` |
| `EMBEDDING_PROVIDERS` | | ordered, default `openai,cohere` |
| `LLM_MAX_ATTEMPTS` / `LLM_RETRY_MAX_WAIT_SECONDS` | | retries per provider before failing over |
| `OPENAI_API_KEY` | yes | `OPENAI_CHAT_MODEL=gpt-4o`, `OPENAI_EMBEDDING_MODEL=text-embedding-3-large` |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_CHAT_MODEL` | optional | generation fallback |
| `COHERE_API_KEY`, `COHERE_CHAT_MODEL`, `COHERE_EMBEDDING_MODEL` | optional | generation + embedding fallback |
| `RESEND_API_KEY`, `EMAIL_FROM` | optional | without a key, emails are logged to the console |
| `ENABLE_SCHEDULER`, `EOD_CRON_HOUR`, `EOD_CRON_MINUTE`, `EOD_TIMEZONE` | | in-process end-of-day job (see below) |
| `CORS_ORIGINS`, `FRONTEND_URL` | | default `http://localhost:5173` |

### Frontend (`frontend/.env`)

| Variable | Notes |
| --- | --- |
| `VITE_SUPABASE_URL` | same as `SUPABASE_URL` |
| `VITE_SUPABASE_ANON_KEY` | anon (public) key |
| `VITE_API_URL` | backend URL, default `http://localhost:8000` |

## Setup

Prerequisites: Python 3.10+, Node 20+, a Supabase project, a Pinecone account and an OpenAI API key.

### 1. Database migration

Run the migration once against your Supabase project. Either use the Supabase CLI:

```bash
cd backend
supabase link --project-ref <project-ref>
supabase db push            # applies supabase/migrations/*.sql
```

…or paste `backend/supabase/migrations/20261104000000_initial_schema.sql` into the Supabase dashboard's SQL editor and run it.

The migration creates the enums, tables, the `auth.users` → `public.users` trigger, the RLS policies, and the private `documents` storage bucket.

### 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt       # or requirements.txt for production
cp .env.example .env                      # fill in keys
uvicorn app.main:app --reload --port 8000
```

API docs are served at http://localhost:8000/docs. Run checks with `pytest` and `ruff check .`.

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env                      # fill in Supabase URL/anon key
npm run dev                               # http://localhost:5173
```

Other scripts: `npm run typecheck`, `npm run build`, `npm run preview`.

### 4. Seed demo data

```bash
cd backend
python -m scripts.seed                    # add --skip-ingest to skip Pinecone/OpenAI
```

The seed creates:
- `student@demo.study`, `parent@demo.study` (linked to the student) and `teacher@demo.study`, all with password `DemoPass123!`
- four subjects, a weekly timetable, and today's/tomorrow's tasks
- two generated sample PDFs (a physics textbook chapter and a past paper with mark schemes), uploaded and ingested into Pinecone

It is safe to re-run. The demo accounts are for local/dev projects only.

## End-of-day job

The job runs once per day. For each student it:
1. aggregates that day's tasks into `daily_reports` (upserted, so re-runs are safe);
2. writes an in-app `notifications` row for each linked parent with `in_app_enabled`;
3. emails each linked parent with `email_enabled` via Resend (or logs the email to the console if `RESEND_API_KEY` is unset).

There are three ways to run it:

```bash
# One-shot (e.g. from cron); --date defaults to today
cd backend && python -m scripts.run_eod_job [--date 2026-11-04]

# crontab: every day at 20:00
0 20 * * * cd /path/to/Study/backend && .venv/bin/python -m scripts.run_eod_job >> eod.log 2>&1
```

- **In the API process**: set `ENABLE_SCHEDULER=true` (plus `EOD_CRON_HOUR`, `EOD_CRON_MINUTE`, `EOD_TIMEZONE`). Use this only with a single API worker, or you will get duplicate emails.
- **Manually by a teacher**: `POST /reports/daily/run`.

Parents manage their in-app/email preferences on the Parent dashboard (`PUT /notifications/preferences`).

## API overview

| Area | Endpoints |
| --- | --- |
| Auth | `GET/PATCH /auth/me`, `GET /auth/students`, `POST /auth/links` |
| Timetable | `POST /timetable/upload` (PDF), `POST /timetable/manual`, `GET /timetable?week_of=`, `GET/POST /timetable/subjects` |
| Tasks | `GET /tasks?date=`, `POST /tasks`, `GET/PATCH/DELETE /tasks/{id}` |
| Documents | `POST /documents` (multipart), `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/download`, `POST /documents/{id}/reingest`, `DELETE /documents/{id}` |
| Chat | `POST /chat` → `{answer, citations: [{doc_id, page, excerpt, storage_path, title}]}` |
| Exams | `POST /exams/generate`, `GET /exams`, `GET /exams/{id}`, `POST /exams/{id}/submit` (`submission_type=text|pdf`), `GET /exams/{id}/result` |
| Reports | `GET /reports/daily`, `POST /reports/daily/run` |
| Notifications | `GET /notifications`, `POST /notifications/{id}/read`, `GET/PUT /notifications/preferences` |

## Known limitations (v1)

- Handwritten/image exam submissions are rejected (enum value reserved for a later release).
- Scanned (image-only) PDFs aren't OCR'd; they need a text layer.
- Ingestion runs as a FastAPI background task. For heavy workloads, move it to a queue/worker.
