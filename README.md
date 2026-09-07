# Legal Metrology Compliance Enforcement System (GoI &bull; PCR 2011)

AI-Assisted statutory compliance platform adhering to the **Legal Metrology Act, 2009** and **Packaged Commodities Rules, 2011**.

---

## 📁 Decoupled Project Structure

```plaintext
project_humnread/
├── backend/
│   ├── src/                    # Pipeline, DB models, rule engine, routers, reports
│   ├── uploads/                # Evidence uploads & sample product images
│   ├── outputs/                # Generated PDF inspection memos & visualizer crops
│   ├── app.py                  # FastAPI ASGI application & API endpoints
│   ├── requirements.txt        # Production dependencies for Render
│   ├── legal_metrology.db      # SQLite central registry database
│   ├── rtdetr-l.pt             # RT-DETR model weights (~66.5 MB)
│   ├── yolo11n.pt              # YOLO11 model weights (~5.6 MB)
│   └── test_*.py               # Automated pipeline & compliance test suites
├── frontend/
│   ├── index.html              # Field Inspector, Supervisor, Admin & Legal portal
│   ├── app.js                  # Frontend controller with environment-aware API_BASE
│   ├── style.css               # Clean styling & responsive layout
│   └── vercel.json             # Vercel static routing configuration
├── .gitignore                  # Excludes .env, virtualenvs, transient runs
└── README.md                   # Full 4-Phase deployment and setup guide
```

---

## 🛠️ Local Development

### 1. Run Backend Locally
Open a terminal in the `backend/` directory:
```bash
cd backend
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```
The API documentation is accessible at `http://127.0.0.1:8000/docs`.

### 2. Run Frontend Locally
Simply open `frontend/index.html` in your web browser, or use a local static server:
```bash
cd frontend
# Using Python:
python -m http.server 3000
# Open http://localhost:3000 in your browser
```
`frontend/app.js` automatically detects `localhost` or `127.0.0.1` and points API requests to `http://127.0.0.1:8000`.

---

## 🚀 Deployment Guide (Phases 1 - 4)

### Phase 1: Frontend & Backend Separation ✅
- **Frontend** is organized in `frontend/` (`index.html`, `app.js`, `style.css`).
- Static links use relative paths: `<link rel="stylesheet" href="./style.css">` and `<script src="./app.js"></script>`.
- **Backend** is organized in `backend/` (`app.py`, `src/`, `requirements.txt`, weights, database).

---

### Phase 2: Backend Preparation for Render ✅
1. **FastAPI CORS**: Enabled via `CORSMiddleware` in `backend/app.py` allowing cross-origin requests from Vercel frontends.
2. **Model Weight Files on Git**:
   - `yolo11n.pt` is **~5.6 MB** (under 100 MB, safe for direct Git push).
   - `rtdetr-l.pt` is **~66.5 MB** (under GitHub's 100 MB limit, safe for direct Git push).
   - *Note*: If you replace `rtdetr-l.pt` with a larger checkpoint exceeding 100 MB in the future, track it using [Git LFS](https://git-lfs.com/) (`git lfs track "*.pt"`).
3. **Requirements**: Production dependencies configured in `backend/requirements.txt` including `fastapi`, `uvicorn[standard]`, `gunicorn`, `torch`, `ultralytics`, `reportlab`, and `deep-translator`.

---

### Phase 3: Deploy Backend to Render

1. **Initialize Git and Push Repository to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Decouple frontend and backend for Render & Vercel deployment"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<your-repo-name>.git
   git push -u origin main
   ```

2. **Create Web Service on Render**:
   - Go to [dashboard.render.com](https://dashboard.render.com/) $\rightarrow$ **New +** $\rightarrow$ **Web Service**.
   - Connect your GitHub repository.

3. **Configure Service Settings**:
   - **Name**: `project-humnread-api` (or your preferred name)
   - **Region**: Select the region closest to your users (e.g., Singapore / Frankfurt)
   - **Root Directory**: `backend`
   - **Runtime**: `Python 3`
   - **Build Command**:
     ```bash
     pip install --no-cache-dir -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     uvicorn app:app --host 0.0.0.0 --port $PORT
     ```
     *(Or with Gunicorn: `gunicorn -w 2 -k uvicorn.workers.UvicornWorker app:app --bind 0.0.0.0:$PORT --timeout 120`)*

4. **Environment Variables on Render**:
   - Add `GEMINI_API_KEY`: Your Google Gemini API Key (optional, for multimodal validation).
   - Add `PYTHON_VERSION`: `3.10.12` or `3.11.8`

5. **Select Instance Plan**:
   > [!IMPORTANT]
   > PyTorch + RT-DETR and YOLO object detection models require sufficient RAM during inference. If the service experiences Out-of-Memory (OOM) errors during model loading on the free tier (512 MB), select the **Starter plan (2 GB RAM)**.

6. **Deploy**:
   - Click **Create Web Service**.
   - Wait for the build to finish.
   - Copy your assigned Render service URL (e.g., `https://project-humnread-api.onrender.com`).

---

### Phase 4: Deploy Frontend to Vercel

1. **Update API Base in `frontend/app.js`**:
   Open `frontend/app.js` and set your Render URL on line 11:
   ```javascript
   const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.protocol === 'file:')
       ? 'http://127.0.0.1:8000'
       : 'https://project-humnread-api.onrender.com'; // <--- Insert your live Render URL here
   ```
   Commit and push the change to GitHub:
   ```bash
   git add frontend/app.js
   git commit -m "Set production Render backend URL"
   git push
   ```

2. **Import Project to Vercel**:
   - Go to [vercel.com](https://vercel.com/) and click **"Add New... > Project"**.
   - Import your GitHub repository.

3. **Configure Project Settings**:
   - **Framework Preset**: `Other`
   - **Root Directory**: Click **Edit** and choose `frontend`.
   - **Build & Development Settings**: Leave blank / default (pure static HTML/CSS/JS).

4. **Deploy**:
   - Click **Deploy**.
   - Vercel will build and deploy the frontend in seconds, providing a production domain (e.g., `https://project-humnread.vercel.app`).

5. **End-to-End Verification**:
   - Open your Vercel URL in your browser.
   - Click **Load Compliant Sample** or **Load Non-Compliant Sample** in the Inspector terminal.
   - Click **Analyze Evidence (AI Vision)** to verify the connection to your Render backend.
   - Test generating the GoI Form I PDF report and issuing supervisor adjudication orders.
