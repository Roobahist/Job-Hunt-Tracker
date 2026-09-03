from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from generate import (
    CVGenerationError,
    PdfLatexCompiler,
    generate_document,
)


DATA_ROOT = Path("/data/document-pipeline")
TEMPLATES_ROOT = DATA_ROOT / "templates"
RUNS_ROOT = DATA_ROOT / "runs"

INTERNAL_BASE_URL = "http://document-worker:8000"

RUN_ID_PATTERN = re.compile(
    r"^[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}$"
)

DOCUMENT_CONFIG = {
    "cv": {
        "template": TEMPLATES_ROOT / "cv_template.tex",
        "data_filename": "cv_data.json",
        "tex_filename": "generated_cv.tex",
        "pdf_filename": "generated_cv.pdf",
        "download_name": "generated_cv",
    },
    "cover-letter": {
        "template": TEMPLATES_ROOT / "cover_letter_template.tex",
        "data_filename": "cover_letter_data.json",
        "tex_filename": "generated_cover_letter.tex",
        "pdf_filename": "generated_cover_letter.pdf",
        "download_name": "generated_cover_letter",
    },
}


app = FastAPI(title="Document Worker")


class DocumentRequest(BaseModel):
    document_type: Literal["cv", "cover-letter"] = "cv"
    data: dict


def create_run_id(
    now: datetime,
    random_suffix: str,
) -> str:
    timestamp = now.astimezone(UTC).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    return f"{timestamp}_{random_suffix}"


def resolve_run_directory(run_id: str) -> Path:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise HTTPException(
            status_code=404,
            detail="Run not found.",
        )

    run_directory = (RUNS_ROOT / run_id).resolve()
    runs_root = RUNS_ROOT.resolve()

    if (
        run_directory.parent != runs_root
        or not run_directory.is_dir()
    ):
        raise HTTPException(
            status_code=404,
            detail="Run not found.",
        )

    return run_directory


def read_manifest(run_id: str) -> dict:
    manifest_path = (
        resolve_run_directory(run_id) / "manifest.json"
    )

    if not manifest_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Manifest not found.",
        )

    return json.loads(
        manifest_path.read_text(encoding="utf-8")
    )


def resolve_artifact(
    run_id: str,
    filename: str,
) -> Path:
    artifact_path = (
        resolve_run_directory(run_id) / filename
    )

    if not artifact_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Artifact not found.",
        )

    return artifact_path


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "document-worker",
    }


@app.post("/generate", status_code=201)
def generate(
    request: DocumentRequest,
) -> dict[str, str]:
    config = DOCUMENT_CONFIG[request.document_type]
    template_path = config["template"]

    if not template_path.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"Template not found: {template_path}",
        )

    RUNS_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    run_id = create_run_id(
        datetime.now(UTC),
        uuid4().hex[:12],
    )

    run_directory = RUNS_ROOT / run_id
    run_directory.mkdir()

    json_path = (
        run_directory / config["data_filename"]
    )
    tex_path = (
        run_directory / config["tex_filename"]
    )

    json_path.write_text(
        json.dumps(
            request.data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    try:
        result = generate_document(
            template_path=template_path,
            data_path=json_path,
            output_path=tex_path,
            document_type=request.document_type,
            compiler=PdfLatexCompiler(
                keep_auxiliary_files=True
            ),
        )
    except CVGenerationError as exc:
        error_path = run_directory / "error.txt"
        error_path.write_text(
            str(exc),
            encoding="utf-8",
        )

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        error_path = run_directory / "error.txt"
        error_path.write_text(
            str(exc),
            encoding="utf-8",
        )

        raise HTTPException(
            status_code=500,
            detail="Unexpected document generation failure.",
        ) from exc

    if (
        result.pdf_path is None
        or not result.pdf_path.is_file()
    ):
        raise HTTPException(
            status_code=500,
            detail=(
                "Generation completed without producing "
                "a PDF."
            ),
        )

    manifest = {
        "run_id": run_id,
        "document_type": request.document_type,
        "run_directory": str(run_directory),
        "json_path": str(json_path),
        "tex_path": str(result.tex_path),
        "pdf_path": str(result.pdf_path),
        "tex_download_url": (
            f"{INTERNAL_BASE_URL}/runs/{run_id}/tex"
        ),
        "pdf_download_url": (
            f"{INTERNAL_BASE_URL}/runs/{run_id}/pdf"
        ),
        "manifest_url": (
            f"{INTERNAL_BASE_URL}/runs/{run_id}"
        ),
    }

    manifest_path = (
        run_directory / "manifest.json"
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
        ),
        encoding="utf-8",
    )

    return manifest


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return read_manifest(run_id)


@app.get("/runs/{run_id}/tex")
def download_tex(run_id: str) -> FileResponse:
    manifest = read_manifest(run_id)
    document_type = manifest["document_type"]
    config = DOCUMENT_CONFIG[document_type]

    tex_path = resolve_artifact(
        run_id,
        config["tex_filename"],
    )

    return FileResponse(
        path=tex_path,
        media_type="application/x-tex",
        filename=(
            f"{run_id}_{config['download_name']}.tex"
        ),
    )


@app.get("/runs/{run_id}/pdf")
def download_pdf(run_id: str) -> FileResponse:
    manifest = read_manifest(run_id)
    document_type = manifest["document_type"]
    config = DOCUMENT_CONFIG[document_type]

    pdf_path = resolve_artifact(
        run_id,
        config["pdf_filename"],
    )

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=(
            f"{run_id}_{config['download_name']}.pdf"
        ),
    )
