import os
import shutil
import time
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.pipeline import MultiModelProductPipeline
from src.config import UPLOAD_DIR, OUTPUT_DIR, BASE_DIR
from src.database.connection import engine, Base, SessionLocal
from src.database.seed_data import seed_database
from src.routers import inspections_router, management_router, legal_router
from ultralytics import YOLO, RTDETR

# Load model weights
model_yolo = YOLO("yolo11n.pt")
model_rtdetr = RTDETR("rtdetr-l.pt")

# Initialize database tables & seed data
Base.metadata.create_all(bind=engine)
_db = SessionLocal()
try:
    seed_database(_db)
finally:
    _db.close()

app = FastAPI(
    title="Packaged Commodities Legal Metrology Enforcement System",
    description="AI-Assisted Compliance Platform adhering to Legal Metrology Act, 2009 & Packaged Commodities Rules, 2011",
    version="2.0.0"
)

# Robust CORS Configuration allowing all origins, methods, and headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Mount static and output directories
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR = BASE_DIR / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)
REPORTS_DIR = OUTPUT_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# -----------------------------------------------------------------------------
# Modular Router Inclusions
# Mount both directly and with /api prefix to guarantee matching routes
# -----------------------------------------------------------------------------
app.include_router(inspections_router.router)
app.include_router(management_router.router)
app.include_router(legal_router.router)

app.include_router(inspections_router.router, prefix="/api")
app.include_router(management_router.router, prefix="/api")
app.include_router(legal_router.router, prefix="/api")

# Lazy pipeline initialization
pipeline = None

def get_pipeline():
    global pipeline
    if pipeline is None:
        pipeline = MultiModelProductPipeline()
    return pipeline


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = TEMPLATES_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return HTMLResponse("<h1>Multi-Model Product Extraction Engine</h1><p>UI is initializing...</p>")


@app.get("/favicon.ico")
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)


@app.get("/api/status")
async def get_status():
    return {
        "status": "ready",
        "models": {
            "detection": ["YOLO11", "RT-DETR", "RF-DETR"],
            "preprocessing": ["OpenCV CLAHE", "Bilateral Filter", "Sauvola (scikit-image)", "PyTorch/Kornia Filter", "Deskew"],
            "ocr": ["PaddleOCR", "WinOCR", "Surya-VL", "Tesseract"],
            "validation": ["Gemini Multimodal", "Google Translate", "PyZBar Barcode"]
        },
        "target_accuracy": "Accuracy > Completeness > Speed"
    }


# Primary AI Image Processing Logic
@app.post("/api/analyze")
async def analyze_product(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be a valid image (JPEG, PNG, WEBP).")

    # Save uploaded file
    filename = f"upload_{int(time.time()*1000)}_{file.filename}"
    file_path = UPLOAD_DIR / filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        p = get_pipeline()
        result = p.process_image(str(file_path))
        result["uploaded_image_url"] = f"/uploads/{filename}"
        result["evidence_image_url"] = f"/uploads/{filename}"
        return JSONResponse(content=result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# Dedicated route aliases matching inspections endpoints in frontend app.js
@app.post("/api/inspections/analyze-evidence")
async def analyze_evidence_alias(file: UploadFile = File(...)):
    return await analyze_product(file)

@app.post("/inspections/analyze-evidence")
async def analyze_evidence_root_alias(file: UploadFile = File(...)):
    return await analyze_product(file)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"[Server] Starting server on http://0.0.0.0:{port}")
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
