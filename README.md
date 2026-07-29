# Job Hunt Automation Workflows

This repository contains the current n8n and Fillout sources for an automated
job-search pipeline. It discovers LinkedIn jobs, accepts manual or AI-assisted
job submissions, stores job records in Baserow, tailors CV and cover-letter
content with Gemini, renders documents, and uploads the resulting files.

## Current sources

### n8n workflows

- `workflows/hourly-linkedin-job-hunt.json` runs the scheduled LinkedIn search,
  filters duplicates, creates the initial Baserow row, generates application
  documents, uploads four artifacts, and updates the row.
- `workflows/linkedin-url.json` reads active Baserow search criteria and creates
  LinkedIn search URLs for the hourly workflow.
- `workflows/unified-job-entry.json` handles LinkedIn, external, and AI
  page-content submissions from Fillout. It normalizes all three paths, upserts
  by numeric Job ID, and invokes the same document workflows as the hourly path.
- `workflows/create-cv-content.json` selects and rewrites CV projects and work
  experience, tailors skills and summary, and returns structured CV data.
- `workflows/create-cover-letter-content.json` creates structured cover-letter
  content using the job, master CV, and active prompt configuration.
- `workflows/render-document.json` sends CV or cover-letter content to the
  document worker and uploads PDF and TeX results to Cloudinary.

### Fillout form

- `forms/job-hunt.json` is the conditional **Add a Job** form used by the unified
  workflow. It supports LinkedIn Job ID, complete external-job details, and
  pasted page content for AI extraction.

## Workflow relationships

```text
LinkedIn criteria -> linkedin-url -> hourly-linkedin-job-hunt
Fillout form ---------------------> unified-job-entry
                                      |
hourly-linkedin-job-hunt -------------+
                                      v
                     create-cv-content
                     create-cover-letter-content
                                      |
                                      v
                           render-document
                                      |
                                      v
                         Cloudinary + Baserow
```

## Import and configuration

Import the six files in `workflows/` into n8n and import
`forms/job-hunt.json` into Fillout. After import:

1. Configure the Baserow, Apify, Fillout, Google Gemini, Cloudinary, and HTTP
   Header Auth credentials referenced by the workflows.
2. Re-select called workflows in n8n if imported workflow IDs are remapped.
3. Configure the Jobs, Search Criteria, and Prompts tables. The exports refer to
   table IDs `1098021`, `1098022`, and `1098023`.
4. Make the master CV available at
   `/home/node/.n8n-files/document-pipeline/master_cv.json`.
5. Configure the document-worker endpoint used by `render-document.json`.
6. Install the verified Apify and Fillout community nodes when they are not
   already available.
7. Activate trigger workflows only after their credentials and dependent
   workflow selections are valid.

Credential objects in the exports are references by ID/name, not credential
values. Credentials, paths, endpoints, table IDs, and other
environment-specific settings may need to be changed after import. Do not
commit exported credentials or local `.env` files.

See `RECONSTRUCTION_NOTES.md` for the evidence and assumptions behind the
reconstructed history.
