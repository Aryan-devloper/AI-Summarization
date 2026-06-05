# AI Summarizer Pro 🤖✨

A full-featured AI Text Summarization SaaS built with **Django 5**, **Tailwind CSS**, **SQLite**, and **Google Gemini 2.5 Flash**.

## Features

- 🔐 **Auth**: Register, Login, Logout, Profile, Password Change
- 📊 **Dashboard**: Stats, Weekly Activity Chart, Summary Type Distribution
- ✦ **AI Summarizer**: 5 summary types (Short, Medium, Detailed, Bullets, Key Points)
- 📄 **Document Uploads**: Summarize PDF, DOCX, and TXT files directly
- 🧠 **MCQ Generator**: Create multiple-choice questions from uploaded documents or pasted text
- 💬 **AI Chatbot**: Floating assistant for help and summarization guidance
- 🔐 **OTP Password Reset**: Email-based code reset flow
- 📚 **History**: Search, Filter, Paginate, Delete, Download
- ⚡ **AJAX**: No page refresh on summary generation
- 📋 **Copy & Download**: One-click copy and TXT download
- 🎨 **Dark Theme**: Glassmorphism, gradient accents, premium feel

## Setup

### 1. Install dependencies

```bash
pip install django==5.1 google-generativeai
```

### 2. Set your Gemini API Key

Option A — Environment variable (recommended):
```bash
export GEMINI_API_KEY="your_gemini_api_key_here"
```

Option B — Edit `ai_summarizer/settings.py`:
```python
GEMINI_API_KEY = 'your_gemini_api_key_here'
```

Get your API key free at: https://aistudio.google.com/

### 3. Run migrations

```bash
python manage.py migrate
```

### 4. Create superuser (optional)

```bash
python manage.py createsuperuser
```

### 5. Start the server

```bash
python manage.py runserver
```

Visit: http://localhost:8000

## Project Structure

```
ai_summarizer_pro/
├── manage.py
├── README.md
├── ai_summarizer/
│   ├── settings.py       ← Config + GEMINI_API_KEY
│   ├── urls.py
│   └── wsgi.py
├── summarizer/
│   ├── models.py         ← Summary + UserProfile models
│   ├── views.py          ← All views + Gemini API integration
│   ├── forms.py          ← Register, Profile, Summarize forms
│   ├── urls.py           ← All routes
│   └── admin.py
├── templates/
│   ├── base.html         ← Toast system, Tailwind config
│   ├── base_app.html     ← Sidebar layout
│   ├── home.html         ← Landing page
│   ├── dashboard.html    ← Stats + charts
│   ├── registration/
│   │   ├── login.html
│   │   └── register.html
│   └── summarizer/
│       ├── summarize.html  ← Main summarizer + AJAX
│       ├── history.html
│       ├── view_summary.html
│       ├── profile.html
│       └── change_password.html
└── static/
    ├── css/
    ├── js/
    └── images/
```

## Summary Types

| Type | Description |
|------|-------------|
| Short | 2-3 sentence summary |
| Medium | 1-2 paragraph summary |
| Detailed | Full comprehensive summary |
| Bullets | Bullet point list |
| Key Points | 5-7 numbered key points |

## Deployment (Production)

```bash
# Set environment variables
export GEMINI_API_KEY="your_key"
export DJANGO_SECRET_KEY="your_secret_key"
export DEBUG=False

# Collect static files
python manage.py collectstatic

# Run with gunicorn
pip install gunicorn
gunicorn ai_summarizer.wsgi:application --bind 0.0.0.0:8000
```

## Tech Stack

- **Backend**: Django 5.1
- **AI**: Google Gemini 2.5 Flash API
- **Frontend**: Tailwind CSS (CDN) + Vanilla JS
- **Database**: SQLite
- **Fonts**: DM Sans + Space Grotesk
- **Auth**: Django built-in + custom templates
