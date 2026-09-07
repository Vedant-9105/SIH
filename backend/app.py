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

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount media and output directories
REPORTS_DIR = OUTPUT_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Include Modular Routers for Phase 2, 3, and 4
app.include_router(inspections_router.router)
app.include_router(management_router.router)
app.include_router(legal_router.router)

# Lazy pipeline initialization
pipeline = None

def get_pipeline():
    global pipeline
    if pipeline is None:
        pipeline = MultiModelProductPipeline()
    return pipeline


@app.get("/")
async def root():
    return {
        "service": "Legal Metrology Compliance Enforcement API",
        "status": "online",
        "version": "2.0.0",
        "docs_url": "/docs",
        "api_status": "/api/status"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}


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
        return JSONResponse(content=result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"[Server] Starting server on http://127.0.0.1:{port}")
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
