# Reconstruction notes

## Method

All JSON files in the source folder and its `final/` subfolder were parsed and
classified. Chronology was based primarily on stable n8n workflow IDs, stable
node IDs, node names and connections, Fillout field IDs, functional diffs, and
cross-workflow references. Modification times were used as supporting evidence,
not as the sole ordering rule. Exact hashes identified duplicate re-exports.

The six exports formerly under `final/` were treated as the authoritative n8n
end state. They were promoted to stable names under `workflows/`; only their
paths changed. `Job Hunt (1).json` was promoted to `forms/job-hunt.json` because
its AI option and `Page Content` field match the final unified workflow. The
canonical files are byte-for-byte copies of those authoritative exports.

## Verified relationships

These relationships are supported by persistent workflow IDs:

| Workflow family | Stable n8n ID | Representative progression |
| --- | --- | --- |
| Hourly LinkedIn ingestion | `MxVJsDcM1ViEMkK3` | Baserow/Apify/OpenRouter, Python migration trial, parallel uploads, early row, fail-soft generation, numeric Job ID |
| Unified job entry | `Z6eQO7DbDI5JJKaI` | manual form, conditional form, Fillout trigger, LinkedIn ID, upsert, AI entry, Baserow prompt config, validated mappings/date |
| CV content | `4sa273djfXRAtOe0` -> `KnYoLlFjWSv6cYYc` -> `NTyHpEu6JpWlafcj` -> `qWB5UMZoKmMpFV4I` | monolithic CV creation, Baserow integration, parent context, structured output |
| Cover-letter content | `sKj0AxXk8F0xwuBi` -> `U1q2LLLGN7WLCYRT` -> `GutFx2P0jerXjCCh` | basic generation, parent context, structured output |
| Document rendering | `SbPNHIhQ9K5AZVS9` / `NHHTSfjSASEpUNWn` -> `lRDjCWKyxz9iILOQ` | CV-only renderer, combined worker, reusable PDF/TeX renderer |
| LinkedIn URL generation | `Y885JEPu9jL7l8yp` -> `ih8KVW6xFuMKHhCS` | static/Airtable source, Baserow source, active criteria filter |

Exact duplicate exports included:

- `CV content creation.json` and `CV content creation (1).json`.
- `CV content creation (3).json` and `(4).json`.
- `Render Document and Upload to Cloudinary (1).json` and `(2).json`.
- `Hourly LinkedIn Job Hunt Pipeline - Baserow Apify OpenRouter.json` and
  `(1).json`.
- `Hourly LinkedIn Job Hunt Pipeline - Baserow Apify OpenRouter (5).json` and
  `(5) - Integer Job ID.json`.
- `LinkedIn URL - Active Baserow Criteria (1).json` and the corresponding
  authoritative export formerly in `final/`.

## Inferred evolution

1. `minimal_job_automation_mvp.json` was the earliest usable proof of concept.
2. It was replaced by `1-job-search-main*.json` and
   `2-job-processor*.json`, representing a split into discovery and processing.
3. The `tailor_*` workflows explored project selection, prompt storage,
   deterministic output, and parallel CV assembly. Their successful ideas were
   consolidated into the `CV content creation*` family; the experimental
   workflows were then removed.
4. CV PDF generation evolved through the `CV_pdf_generation*`,
   `CV PDF Generation*`, `CV_PDF_Generation*`, and
   `CV_Cloudinary_Airtable_Workflow*` families. The separate rendering concern
   eventually became the reusable document-rendering workflow.
5. Cover-letter generation and the combined document worker were introduced,
   after which the hourly flow was renamed and expanded into the Baserow/Apify
   pipeline.
6. A Python-native migration was trialed across hourly, manual, and rendering
   workflows. Later exports returned the canonical path to n8n nodes; the trial
   remains visible in history but is absent from the final tree.
7. Manual external entry was expanded to accept either URLs or full details,
   then unified with LinkedIn entry. The native n8n form was replaced with
   Fillout.
8. The form and unified workflow gained a numeric LinkedIn Job ID, parallel
   document uploads, early Baserow row creation, exact-ID upsert, and numeric
   Job ID handling.
9. AI page-content entry was added. Prompt configuration moved to Baserow,
   structured Gemini parsing and a backup model were added, and Baserow field
   values and dates were validated for the final version.

The hourly and unified flows were not literally merged into one n8n workflow.
Instead, they converged on a shared schema and the same CV, cover-letter, and
rendering subworkflows. The history represents that functional merge while
retaining both entry points.

## Rename, split, replacement, and deletion decisions

- **Split:** the MVP became separate LinkedIn search and job-processing
  workflows.
- **Renamed/expanded:** the search workflow became
  `hourly-linkedin-job-hunt.json`; the Airtable URL helper became
  `linkedin-url.json`.
- **Replaced:** project-tailoring experiments and the early processor were
  replaced by `create-cv-content.json`.
- **Split/reused:** CV-only PDF generation and combined worker experiments were
  replaced by the reusable `render-document.json`, called for both CVs and
  cover letters.
- **Renamed/replaced:** manual job entry became `unified-job-entry.json` when
  Fillout replaced the n8n-native form.
- **Removed:** Python migration variants, no-duplicate-check variants, test-mode
  renderers, Run Artifacts prototypes, native-form variants, and superseded
  export copies do not appear in the final tree.

## Fillout lineage

- `My form.json` is a two-step button-only stub and was excluded.
- `Fillout_Dynamic_Job_Entry_Form.json` is an early generated conditional-form
  experiment with synthetic field IDs.
- `My form 1.json` is the first substantial Fillout export with the stable
  `kz18` step and production field IDs.
- `Job Hunt.json` adds the numeric LinkedIn Job ID field and matches the
  LinkedIn/external Fillout workflow generation.
- `Job Hunt (1).json` adds the `ai` entry option and `uAXU...` Page Content
  field. This is the authoritative form.
- `gemini-code-1785192017679.json` is a separate generated form-description
  format, not a Fillout export, and was excluded.

## Excluded source material

The final tree intentionally excludes superseded exports and non-source
artifacts:

- `main-orchestrator.json`, `sub-*.json`, and `error-handler.json`: an abandoned
  modular prototype superseded by the later stable-ID workflows.
- All `tailor_master_*`, `tailor_cv_projects_*`, and
  `tailor_complete_cv_*` files: prompt and parallelization experiments later
  consolidated into CV content creation.
- Superseded `CV content creation*`, `CV Content Creation*`,
  `Cover Letter Content Creation*`, `CV_pdf_generation*`,
  `CV PDF Generation*`, `CV_PDF_Generation*`,
  `CV_Cloudinary_Airtable_Workflow*`, `Generate CV*`, and
  `Render Document*` exports.
- Superseded `Hourly LinkedIn Job Hunt Pipeline*`, `LinkedIn URL*`,
  `Manual External*`, `Manual External or LinkedIn*`,
  `Unified_LinkedIn_*`, and `Unified LinkedIn*` exports.
- `LLM_Provider_Fallback_*`: standalone provider-fallback experiments not
  referenced by the final workflows.
- `dataset_linkedin-jobs-scraper_*.json`, `mahsa_cv.json`, `cv_data*.json`,
  `generate_cv*.py`, and `app_run_artifacts.py`: sample data and local helper
  scripts, not authoritative workflow/form sources.
- ZIP archives, legacy README variants, `.DS_Store`, and exact duplicate export
  copies.

These files were used as reconstruction evidence and selected representatives
appear in earlier commits, but duplicate backups are not tracked in the final
tree.

## Ambiguities and assumptions

- Several early exports lack n8n workflow IDs. Their ordering relies on
  modification times plus structural similarity and is therefore inferred.
- The transition between the early `SbPN...`/`NHHT...` document workers and
  `lRDj...` is treated as a replacement/refactor because node purpose and call
  sites align even though the workflow ID changed.
- The CV workflow ID changes are treated as continued evolution because node
  IDs, names, connections, and payload schema persist across those exports.
- The Python migration appears to have been a short-lived trial. Its later
  timestamps overlap with native exports; functional consistency with the
  authoritative set was used to place the return to native n8n nodes.
- `Job Hunt (1).json` sits outside the former `final/` directory, but its field
  IDs and AI branch exactly match the final unified workflow, so it is treated
  as the final Fillout source.

No major functionality was invented. Intermediate commits use actual historical
exports, renamed into stable repository paths.
