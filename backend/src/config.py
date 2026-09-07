import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables (.env.local first, then .env)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env.local")
load_dotenv(BASE_DIR / ".env")
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
CACHE_DIR = BASE_DIR / "cache"

# Create required directories
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""

# Confidence Thresholds
DETECTION_CONF_THRESHOLD = float(os.getenv("DETECTION_CONF_THRESHOLD", "0.25"))
OCR_CONF_THRESHOLD = float(os.getenv("OCR_CONF_THRESHOLD", "0.40"))
CONSENSUS_IOU_THRESHOLD = float(os.getenv("CONSENSUS_IOU_THRESHOLD", "0.45"))

# Mandatory Legal Metrology & Product Declaration Fields
MANDATORY_FIELDS = [
    "product_name",
    "brand_name",
    "manufacturer_name",
    "manufacturer_address",
    "net_quantity",
    "mrp",
    "currency",
    "batch_number",
    "manufacturing_date",
    "expiry_date",
    "consumer_care",
    "country_of_origin",
    "barcode_or_qr",
    "other_declarations"
]

# Field Display Labels
FIELD_LABELS = {
    "product_name": "Product Name",
    "brand_name": "Brand Name",
    "manufacturer_name": "Manufacturer Name",
    "manufacturer_address": "Manufacturer / Packer Address",
    "net_quantity": "Net Quantity",
    "mrp": "Maximum Retail Price (MRP)",
    "currency": "Currency",
    "batch_number": "Batch / Lot No.",
    "manufacturing_date": "Manufacturing / Packing Date",
    "expiry_date": "Expiry / Best Before Date",
    "consumer_care": "Consumer Care Info",
    "country_of_origin": "Country of Origin",
    "barcode_or_qr": "Barcode / QR Details",
    "other_declarations": "Other Declarations / Notes"
}
