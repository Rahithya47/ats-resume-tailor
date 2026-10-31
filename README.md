# ATS Resume Tailor

Compare a resume (PDF or DOCX) with a job description and see which skills match, which are missing, and what to review. It runs locally, needs no paid API and no internet connection once installed.

> The match percentage is an **estimated keyword match**. It is not an official ATS score and does not predict whether a recruiter or employer will shortlist you.

vercel link : https://ats-resume-tailor-app.vercel.app/

## Features

- Dashboard with total analyses, latest score and recent activity
- PDF/DOCX upload (drag-and-drop or browse), optional job title and company, required job description
- Required vs preferred skill detection from a curated skills dictionary
- Matched, missing and related keywords, with evidence from your resume (shown once, right after analysis)
- Explainable score breakdown and ranked recommendations
- History with single and bulk deletion (CSRF-protected, with confirmation)
- Clear errors for unsupported, empty, oversized, corrupted, encrypted or scanned files
- **Tailored resume generator** (see below): ATS-friendly PDF and DOCX built from your own resume content

## Generate a tailored, ATS-friendly resume

1. Run an analysis as usual, then click **Generate Tailored Resume** on the results page. Optionally tick skills the job asks for that you *genuinely* have; unticked skills are never added.
2. Review the **preview**, the list of what changed, the keyword coverage report (matched/missing required and preferred skills) and the export checks. Edit anything in the plain-text editor and press **Save changes**.
3. Use **Download ATS Resume (PDF)** or **Download ATS Resume (DOCX)**. Both files are built from the same saved content, read back and validated first; if a check fails, no file is served and the preview explains why.

What the tailoring does (deterministic, no AI service or API key needed):

- Reorders skills, projects, bullet points and certifications so job-relevant items come first. Experience entries keep their original (normally reverse-chronological) order; only the bullets inside each role are reordered.
- Rewrites a short whitelist of exact synonyms to the job's wording (JS to JavaScript, Postgres to PostgreSQL, k8s to Kubernetes, ...) and only when the job description uses that term. Related technologies are never treated as the same skill.
- Keeps your summary and appends matching skills already in your resume, or writes a short summary from them if you had none.
- Makes dates consistent (`June 2024 - August 2024` becomes `Jun 2024 - Aug 2024`).
- **Never** adds a skill, employer, project, certification or metric that is not in your resume or explicitly ticked by you.

ATS-friendly layout: single column, standard headings in a fixed order (Professional Summary, Technical Skills, Projects, Experience, Education, Certifications; empty sections are omitted), Arial/Helvetica, real text, conventional bullets, contact details in the body. No tables, text boxes, images, icons, rules or header/footer content. The PDF tries 10.5, 10 and 9.5 pt to fit one page and otherwise uses two; more than two pages fails validation so you can trim it in the editor.

Always check the final content yourself. The keyword coverage is an estimate; it is not an official ATS score and does not guarantee interviews or hiring.

## Setup (Windows PowerShell)

```powershell
cd C:\Users\USER\Projects\ats-resume-tailor

# Create the virtual environment (first time only)
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
python -m pip install -r requirements.txt

# Configure secrets (first time only)
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # paste the output as SECRET_KEY in .env

# Run the tests
python -m pytest -q

# Start the app
python app.py
```

Open <http://127.0.0.1:5000/>. `python app.py` starts Flask's development server, which is for local use only.

If PowerShell blocks activation: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

After the tests pass on your machine, run `python -m pip freeze` and pin the versions you tested in `requirements.txt` before publishing.

## How the score works

```
coverage(group) = matched skills in group / total skills in group x 100
overall         = 0.8 x required coverage + 0.2 x preferred coverage
```

- If the posting has only one group, that group's coverage is the score.
- If no recognizable skills are found, there is no score (shown as N/A), so there is no division by zero.
- Skills under headings such as "Nice to have" or on lines containing phrases like "a plus" are *preferred*; everything else is *required*. Required wins if a skill appears in both.
- Only exact matches count, including listed aliases (JS = JavaScript, k8s = Kubernetes, Postgres = PostgreSQL).
- **Related** skills (for example Azure when the job asks for AWS, or Angular for React) are flagged for your review but never counted as matches.

Example: 12 of 20 required skills found means 60% required coverage.

## Privacy

- Uploaded files are written to a randomly named temporary file and deleted in a `finally` block, even when parsing fails.
- To let you generate and edit a tailored resume after the analysis, the extracted resume text and your draft are kept in **server memory only**, tied to your browser session, for up to `CONTEXT_TTL_SECONDS` (default 2 hours, sliding). They are never written to disk, to the database or to history, and are lost when the app restarts. **Discard my resume data** (on the preview page) removes them immediately.
- History stores only: job title, company, timestamp, score, keyword lists, breakdown and recommendations. Evidence snippets (which come from your resume) are shown on the results page only and are not saved. Emails and phone numbers are redacted from snippets.
- Everything is processed locally. No external service is called.
- `.env`, `instance/*` (the database) and resume files are excluded by `.gitignore`.

## Security

CSRF tokens on every POST form; parameterized SQL; Jinja2 autoescaping; extension, size and file-signature checks; upload size limit (`MAX_UPLOAD_MB`, default 5); secrets from environment variables. Uploaded content is only parsed for text, never executed or rendered as HTML.

## Limitations

- Only skills in the built-in dictionary (`app/services/keyword_extractor.py`) are detected. Niche tools, certifications and domain terms are not. Extend `SKILLS` to add more.
- Matching is keyword-based. It does not understand context, seniority, years of experience, or whether a skill is described truthfully.
- Short ambiguous words can still produce false positives (for example, "testing" as a general word).
- Scanned or image-only PDFs are rejected because OCR is not implemented. Use a text-based PDF or a DOCX.
- Password-protected PDFs and DOCX files are rejected.
- Section detection for required vs preferred relies on common headings and phrases; unusual postings may be classified as all-required.
- scikit-learn / TF-IDF discovery of terms outside the dictionary is not implemented, so it is not in `requirements.txt`.
- Resume tailoring is rule-based, not AI-written. No AI provider is integrated; it will not rewrite sentences beyond the synonym whitelist.
- Splitting an uploaded resume into sections/entries is heuristic. Unusual layouts can be mis-split, which is why the editor step exists. Unrecognized sections are kept as "additional sections".
- The PDF uses standard fonts (Helvetica), so characters outside Western European text are shown as `?` in the PDF. The DOCX keeps them.
- Drafts live in one process's memory: they do not survive restarts and do not work across multiple worker processes. Use the built-in single-process server locally.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `ModuleNotFoundError` | Activate the venv and run `python -m pip install -r requirements.txt`. |
| "The file is too large" | Raise `MAX_UPLOAD_MB` in `.env` and restart. |
| "Security check failed" | The form expired or `SECRET_KEY` changed. Reload the page and resubmit. Set a fixed `SECRET_KEY` in `.env`. |
| "No selectable text was found" | The PDF is a scan. Export a text PDF or upload a DOCX. |
| Port 5000 in use | Set `PORT=5001` in `.env` (or the environment) and restart. |
| Reset all data | Stop the app and delete `instance\ats_resume_tailor.db`. |
| "Your session expired ... run the analysis again" | Drafts are kept in memory for a limited time and are lost on restart. Re-run the analysis. |
| Download buttons are greyed out | Open **Export checks** on the preview page. Usually the name or contact details are missing, or the resume is over two pages. Fix it in the editor and save. |
| `ModuleNotFoundError: reportlab` or `pypdf` | Run `python -m pip install -r requirements.txt` again; these were added for the resume generator. |

## Project layout

```
app.py                    entry point
config.py                 environment-driven config
app/__init__.py           app factory, CSRF, error handlers
app/routes.py             HTTP routes
app/database.py           SQLite (parameterized queries)
app/validators.py         upload and form validation
app/resume_routes.py      generate / preview / edit / download routes
app/context_store.py      session-bound, in-memory, expiring store for drafts
app/services/             resume_parser, text_cleaner, keyword_extractor,
                          scoring, recommendations, analysis (orchestration),
                          resume_structure (parse into sections), tailoring,
                          resume_edit (editor form), resume_export (PDF + DOCX),
                          export_validation (read-back checks)
app/templates, app/static HTML, CSS, JS
tests/                    pytest suite (temporary SQLite DB, offline)
```
