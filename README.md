# FJMC Academy Smart OMR — Advanced v2

FastAPI + OpenCV + SQLAlchemy application with an admin API, student login/results, exam and answer-key management, OMR scan endpoint, review queue, CSV export, basic analytics, booking slots, SQLite/PostgreSQL support, Docker and Render blueprint.

## Run locally
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# Set ADMIN_KEY in your environment before starting
uvicorn app.main:app --reload
```
Open `http://127.0.0.1:8000` and `/docs`.

## Deploy
Push the folder to GitHub and create a Render web service using the included `render.yaml`/Dockerfile. Set `ADMIN_KEY` to a long random value. Set `DATABASE_URL` to a managed PostgreSQL connection string for persistent records. Render ephemeral disks are not durable; do not rely on local SQLite/uploads for production.

## Main API
- `POST /api/students` (admin key): add student
- `POST /api/student/login`: student login
- `POST /api/exams` (admin key): create exam with answer key
- `PUT /api/exams/{id}/key` (admin key): update answer key
- `POST /api/exams/{id}/publish` (admin key)
- `POST /api/scan/{id}` (admin key, multipart): scan JPG/PNG
- `GET /api/admin/review-queue` (admin key)
- `GET /api/exams/{id}/analytics` (admin key)
- `GET /api/exams/{id}/export.csv` (admin key)
- `POST /api/slots` and `POST /api/slots/{id}/book`

## OMR template calibration — important
The reader is a **fixed-layout prototype**, not a universal scanner. Its default normalized coordinates assume two columns and a particular bubble grid. Before real exams, print a test sheet, scan it at multiple angles/lighting conditions, then calibrate `app/omr.py` coordinates/radii/thresholds to the exact printed form. The current reader does not generate the matching answer-sheet PDF and does not guarantee accurate handwritten OCR or roll-number bubble decoding. Enter roll number/name in the scan form or integrate a verified OCR workflow.

## Feature status / honest limitations
- Included: perspective/page-boundary correction attempt, illumination normalization, denoising, bubble darkness comparison, confidence/review flags, scoring, student/admin API, PostgreSQL-ready ORM, CSV and basic exam analytics.
- Not included as production-ready: Google-Scanner-equivalent AI enhancement, reliable handwriting OCR, arbitrary template auto-detection, multiple answer-sheet set layouts, automatic roll-number bubble reading, registered-device enforcement, Gmail/Firebase identity, secure student session tokens, item discrimination/distractor statistics, PDF multi-page batch scanning, backup automation.
- Student login in this starter verifies credentials but returns no signed session token; production authentication must add JWT/session cookies, rate limiting, CSRF protections and password reset.
- Protect `/docs` and admin endpoints before public production use. Configure HTTPS, backups, monitoring, storage retention and access controls.

This is a deployable development baseline; validate the scanner on your exact answer sheet and run security/functional tests before using it for live examinations.
