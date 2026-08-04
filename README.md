# AI-Powered Customer Complaint Management System

This project implements a pharma-focused complaint intake workflow with a React + Redux frontend and a FastAPI backend.

## What it demonstrates
- A two-panel complaint intake experience
- AI-assisted extraction from complaint text or uploads
- Redux-driven form population from analysis results
- A lightweight backend endpoint flow for ingest, analyze, and chat

## Tech stack
- Frontend: React, Redux Toolkit, Vite
- Backend: FastAPI, SQLAlchemy
- AI: Groq-compatible LLM integration via a service layer

## Run locally
### Backend
```bash
cd backend
python -m uvicorn main:app --reload --port 8000
```

### Frontend
```bash
npm install
npm run dev
```

## Demo workflow
1. Open the app at http://localhost:5173
2. Paste a complaint email or text into the AI assistant panel
3. Submit the text for analysis
4. Observe the complaint form populate with extracted fields
5. Use the chat box to ask follow-up questions about the complaint

## Notes
- The AI layer uses a Groq-compatible client when a GROQ_API_KEY environment variable is set.
- If no key is configured, the system falls back to deterministic extraction heuristics so the demo still works locally.
