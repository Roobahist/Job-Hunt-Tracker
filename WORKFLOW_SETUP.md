# n8n Job Hunt Workflow Setup

This repository contains seven n8n workflow exports configured for tenant-specific values stored in an internal n8n Data Table. Workflow canvases intentionally contain no Sticky Note nodes or node-level notes; operational documentation lives in this file.

## Required Data Table

Create an internal n8n Data Table with the exact name:

`n8n user configuration`

Import [`n8n-user-configuration.csv`](n8n-user-configuration.csv) into it. The table must contain these columns:

| Column | Purpose |
| --- | --- |
| `configKey` | Unique configuration key used by workflow expressions |
| `category` | Organizational label |
| `valueType` | One of `text`, `number`, `boolean`, or `json` |
| `value` | The stored value; JSON objects and arrays remain serialized text |
| `enabled` | Whether the configuration row can be used |
| `description` | Human-readable explanation |

Every workflow begins by reading this table by name. **Build User Configuration** converts each value according to `valueType` and rejects duplicate keys, malformed values, and missing required settings. Empty tables also produce a configuration error instead of silently stopping execution.

Keep one enabled row per `configKey`. Do not place credentials, API keys, access tokens, or other secrets in this table; use n8n Credentials for authentication.

## Bootstrap Values

Some identifiers must exist before runtime configuration can be loaded:

- The Data Table name `n8n user configuration` is the stable bootstrap identifier used by every workflow.
- The Fillout trigger must be manually bound to the form represented by `fillout_form_id`. Trigger configuration is resolved before workflow execution. **Submit Job** validates the received form ID against the configured value.
- The schedule trigger runs every hour. After configuration loads, **Tenant Enabled and Schedule Due?** applies `tenant_enabled` and `linkedin_schedule_interval_hours`. Manual runs bypass the interval check but still require `tenant_enabled` to be true.
- Each workflow retains its own n8n workflow ID. Execute Workflow nodes read destination IDs from `workflow_ids`, so update that JSON value after importing workflows into another instance if n8n assigns different IDs.
- `telegram_album_document_count` is intentionally not tenant configuration. The Telegram album remains hardcoded to five documents: one ZIP plus four individual PDF/TeX files.

## Credentials and Services

Create and select the appropriate credential in every node that requires one:

- Baserow
- Apify
- Google Gemini
- Cloudinary
- Telegram
- Baserow HTTP Header Auth
- Fillout

The Baserow HTTP Header Auth credential used for file uploads must send an `Authorization` header containing the Baserow database token. Keep all credential values in n8n Credentials rather than workflow fields or the Data Table.

The configured `master_cv_path` must be mounted and readable inside the n8n container. The service at `document_worker_url` must be reachable from the n8n container. Select the Cloudinary credential in both document-upload nodes.

## Workflow Responsibilities

### LinkedIn URL

[`workflows/linkedin-url.json`](workflows/linkedin-url.json) reads Search Criteria rows from the configured Baserow table, skips inactive criteria, builds LinkedIn search URLs from `linkedin_base_search_url`, and writes each generated URL using `search_criteria_field_ids.generatedUrl`.

### Hourly LinkedIn Job Hunt

[`workflows/hourly-linkedin-job-hunt.json`](workflows/hourly-linkedin-job-hunt.json) performs the scheduled job search and application-document pipeline:

1. Apply the tenant-enabled and configured-interval gate.
2. Generate active LinkedIn URLs.
3. Read the master CV and configured Baserow search criteria.
4. Run the configured Apify LinkedIn-search actor with the configured exclusions and item limit.
5. Deduplicate scraped jobs against the configured Jobs table.
6. Create the initial Baserow metadata row.
7. Score qualification through `workflow_ids.scoreQualification`.
8. Continue when the score reaches `qualification_threshold`.
9. Generate CV and cover-letter content and render their files.
10. Upload the files to Baserow and optionally send the configured Telegram document album.

The metadata row is created before document generation. Protected content-generation, rendering, file-upload, payload-construction, and final-update failures route to **Skip Failed Document Generation**, preserving the metadata row and allowing the next job to continue.

The four generated application files share one application ID:

- `cv_<application-id>.pdf`
- `cv_<application-id>.tex`
- `cover-letter_<application-id>.pdf`
- `cover-letter_<application-id>.tex`

### Unified Job Entry

[`workflows/unified-job-entry.json`](workflows/unified-job-entry.json) accepts Fillout submissions for three entry types:

- **LinkedIn:** builds a job URL from the submitted ID and runs the configured single-job Apify actor.
- **External:** uses manually submitted job fields.
- **AI:** extracts normalized job fields from submitted page content.

All branches normalize to the same job schema, resolve or generate a positive numeric Job ID, write metadata using the configured Baserow field and option IDs, score qualification, and generate the application documents.

### CV Content

[`workflows/create-cv-content.json`](workflows/create-cv-content.json) reads six active prompt settings from the configured Prompts table, selects `project_selection_count` projects and `work_experience_selection_count` experiences, rewrites the selected content, tailors skills, and produces the final CV JSON.

The two selection counts are independent configuration values. Prompt templates should also use `[[selection_count]]` so their textual instructions stay aligned with workflow validation.

### Cover-Letter Content

[`workflows/create-cover-letter-content.json`](workflows/create-cover-letter-content.json) reads the active cover-letter prompt from the configured Prompts table, generates structured content with the configured Gemini model, and returns the final cover-letter JSON.

### Qualification Scoring

[`workflows/score-job-qualification.json`](workflows/score-job-qualification.json) receives `job_description`, `master_cv`, and `job_context`. It reads the active qualification prompt from the configured Prompts table, uses structured Gemini output, and returns the original context with `qualification_score`, `should_apply`, and prompt-usage metadata.

### Document Rendering

[`workflows/render-document.json`](workflows/render-document.json) normalizes CV or cover-letter input, calls `document_worker_url`, downloads the generated PDF and TeX files, and uploads them to the configured Cloudinary folder with the configured base tags.

Valid `document_type` values are `cv` and `cover-letter`.

## Telegram Album Test

The hourly workflow contains a disabled manual test path:

1. Enable **TEST — Enable Sample Telegram Path**.
2. Run the workflow manually.
3. Confirm that Telegram receives one five-document album at `telegram_chat_id`: the ZIP followed by the four individual PDF/TeX files.
4. Disable the test trigger again.

This path uses synthetic files and does not scrape LinkedIn, call AI workflows, or write to Baserow.

## New-Tenant Checklist

1. Create the new n8n instance or isolated n8n project.
2. Import all workflow JSON files.
3. Create `n8n user configuration` and import the CSV.
4. Replace the Data Table values for the new tenant.
5. Update `workflow_ids` if the imported workflows received different IDs.
6. Bind the Fillout trigger to the tenant's form and keep it aligned with `fillout_form_id`.
7. Create and select the tenant's credentials in every credentialed node.
8. Mount the configured master-CV file and ensure the document worker is reachable.
9. Run each workflow manually with controlled test input before activation.
10. Activate the trigger workflows only after their executions and external writes have been verified.
