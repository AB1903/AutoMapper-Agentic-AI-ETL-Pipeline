"""
FastAPI application for AutoMapper.
Now serves a full HTML frontend at /

Endpoints:
  GET  /              — frontend UI
  POST /map           — upload CSV + run full pipeline
  GET  /schemas       — list available target schemas
  GET  /health        — service health + Ollama status
  GET  /download/{id} — download generated ETL script
"""

import logging
import os
import shutil
import uuid
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.core.ollama_client import OllamaClient
from backend.core.pipeline import AutoMapperPipeline
from backend.core.target_schemas import SCHEMA_REGISTRY

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

# ── Config ─────────────────────────────────────────────────────
with open("config/config.yaml") as f:
    CFG = yaml.safe_load(f)

UPLOAD_DIR = Path(CFG["data"]["upload_dir"])
OUTPUT_DIR = Path(CFG["data"]["output_dir"])
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── App ────────────────────────────────────────────────────────
app = FastAPI(
    title="AutoMapper API",
    description="LLM-Powered Schema Mapping & ETL Automation",
    version="1.0.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store
JOB_STORE: dict = {}


# ── Frontend ───────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def frontend():
    """Serve the AutoMapper frontend UI."""
    html_path = Path("frontend/index.html")
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text())
    return HTMLResponse(content="<h1>Frontend not found</h1><p>Place index.html in frontend/</p>")


# ── Health ─────────────────────────────────────────────────────
@app.get("/health")
async def health():
    ollama    = OllamaClient()
    ollama_ok = ollama.is_available()
    models    = ollama.list_models()
    return {
        "status":           "healthy" if ollama_ok else "degraded",
        "ollama_running":   ollama_ok,
        "ollama_model":     CFG["ollama"]["model"],
        "available_models": models,
        "message": "Ready" if ollama_ok else "Ollama not running."
    }


# ── Schemas ────────────────────────────────────────────────────
@app.get("/schemas")
async def list_schemas():
    return {
        "schemas": [
            {
                "name":        name,
                "description": info["description"],
                "tables":      list(info["tables"].keys()),
            }
            for name, info in SCHEMA_REGISTRY.items()
        ]
    }


# ── Map ────────────────────────────────────────────────────────
@app.post("/map")
async def map_schema(
    file:          UploadFile = File(...),
    target_schema: str        = Form("retail_dwh"),
    target_table:  str        = Form("staging.raw_transactions"),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    job_id    = str(uuid.uuid4())[:8]
    file_path = UPLOAD_DIR / f"{job_id}_{file.filename}"

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    log.info("Received file: %s | job_id: %s", file.filename, job_id)

    try:
        pipeline = AutoMapperPipeline()
        result   = pipeline.run(
            file_path=str(file_path),
            target_schema_name=target_schema,
            target_table=target_table,
        )

        script_path = OUTPUT_DIR / f"{job_id}_etl.py"
        with open(script_path, "w") as f:
            f.write(result.get("generated_code", ""))

        result["job_id"]       = job_id
        result["download_url"] = f"/download/{job_id}"

        JOB_STORE[job_id] = {
            "script_path": str(script_path),
            "result":      result,
        }

        result_response = {k: v for k, v in result.items() if k != "generated_code"}
        result_response["code_preview"] = "\n".join(
            result.get("generated_code", "").split("\n")[:30]
        )

        return JSONResponse(content=result_response)

    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error("Pipeline error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")
    finally:
        if file_path.exists():
            file_path.unlink()


# ── Download ───────────────────────────────────────────────────
@app.get("/download/{job_id}")
async def download_script(job_id: str):
    job = JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    script_path = Path(job["script_path"])
    if not script_path.exists():
        raise HTTPException(status_code=404, detail="Script file not found")

    return FileResponse(
        path=str(script_path),
        filename=f"automapper_etl_{job_id}.py",
        media_type="text/x-python",
    )
