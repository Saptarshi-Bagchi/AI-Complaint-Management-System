# 🤖 AI-Powered Customer Complaint Management System

> An AI-assisted Customer Complaint Management System for the **pharmaceutical manufacturing industry (API & FDF Quality Assurance)** built as part of an **AI Product Engineer Internship Assignment**.

The application enables QA teams to log customer complaints either manually or with an **AI Copilot** that extracts structured information from complaint documents (PDF, email, or plain text), evaluates complaint severity and priority, and auto-fills the complaint form for human verification before saving.

---

## ✨ Features

* 🤖 AI Copilot for complaint extraction
* 📄 Upload PDF, email, or text documents
* ⚡ Live extraction progress
* 💬 Follow-up AI chat interface
* 🎯 Automatic complaint field extraction
* 🗄️ Complaint storage using PostgreSQL

---

## 🛠 Tech Stack

| Category     | Technology                                        |
| ------------ | ------------------------------------------------- |
| Frontend     | React, Redux Toolkit                              |
| Backend      | FastAPI, Python                                   |
| AI Agent     | LangGraph                                         |
| LLM Provider | Groq                                              |
| Models       | `llama-3.1-8b-instant`, `llama-3.3-70b-versatile` |
| Database     | PostgreSQL                                        |
| UI Font      | Google Inter                                      |

> **Model Update**
>
> The original assignment specified **Groq's `gemma2-9b-it`** model. Since it was deprecated by Groq in **October 2025**, this project uses **`llama-3.1-8b-instant`** for fast structured extraction while maintaining the intended functionality. The larger **`llama-3.3-70b-versatile`** model is used for reasoning-intensive tasks such as risk assessment.

---

# 🚀 Getting Started

## Prerequisites

* Python 3.10+
* Node.js
* PostgreSQL (Local Installation)
* Groq API Key

---

## 1️⃣ Clone the Repository

```bash
git clone <repository-url>
cd <repository-name>
```

---

## 2️⃣ Backend Setup

Create a virtual environment:

```bash
cd backend

python -m venv venv
```

Activate it:

**Windows**

```bash
venv\Scripts\activate
```

**Linux/macOS**

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file:

```env
DATABASE_URL=postgresql://username:password@localhost:5432/complaints_db
GROQ_API_KEY=your_groq_api_key
```

Create the database:

```sql
CREATE DATABASE complaints_db;
```

Run the backend:

```bash
uvicorn main:app --reload
```

---

## 3️⃣ Frontend Setup

```bash
cd frontend

npm install

npm run dev
```

---

## 📌 API Endpoints

| Method | Endpoint                   | Description                                |
| ------ | -------------------------- | ------------------------------------------ |
| POST   | `/complaints/ingest`       | Create a new complaint                     |
| GET    | `/complaints/`             | Retrieve all complaints                    |
| POST   | `/complaints/{id}/analyze` | Run LangGraph extraction & risk assessment |
| POST   | `/complaints/{id}/chat`    | AI Copilot follow-up chat                  |

---

## 📄 License

This project was developed as part of an **AI Product Engineer Internship Assignment** and is intended for educational and demonstration purposes.
