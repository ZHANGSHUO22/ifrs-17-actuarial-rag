#!/bin/bash
# Exit on error
set -e

mkdir -p bootstrap
echo '{"step": 1, "message": "Installing heavy dependencies (chromadb, sentence-transformers)...", "ready": false}' > bootstrap/status.json

# 1. Start Bootstrap Status Server on Port 3000
echo "--- Starting Status Tracker ---"
python3 -m http.server 3000 --directory bootstrap &
STATUS_PID=$!

# 2. Install Dependencies
echo "--- Step 1: Installing Dependencies ---"
pip install --prefer-binary -r requirements.txt

# 3. Start Backend
echo '{"step": 2, "message": "Starting FastAPI Backend...", "ready": false}' > bootstrap/status.json
echo "--- Step 2: Starting Backend ---"
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
BACKEND_PID=$!

# 4. Wait for Backend Health & Model Loading
echo '{"step": 3, "message": "Loading Actuarial Models (this takes a moment)...", "ready": false}' > bootstrap/status.json
echo "--- Step 3: Waiting for Backend Health ---"
for i in {1..60}; do
    if curl -s http://localhost:8000/api/health > /dev/null; then
        echo "Backend is UP"
        break
    fi
    echo "Waiting for backend... ($i/60)"
    sleep 2
done

# 5. Switch to Streamlit
echo '{"step": 4, "message": "Launching Streamlit UI...", "ready": true}' > bootstrap/status.json
echo "--- Step 4: Launching Streamlit ---"
sleep 2
kill $STATUS_PID || true

streamlit run frontend/app.py \
    --server.port 3000 \
    --server.address 0.0.0.0 \
    --server.enableCORS false \
    --server.enableXsrfProtection false \
    --browser.gatherUsageStats false
