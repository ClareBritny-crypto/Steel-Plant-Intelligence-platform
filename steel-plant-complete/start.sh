#!/bin/bash
echo "🚀 Starting Steel Plant Intelligence Platform..."
echo "=============================================="
echo ""
echo "Installing dependencies..."
pip install -q -r requirements.txt

echo ""
echo "Starting server on http://10.3.0.19:8000"
echo "Press Ctrl+C to stop"
echo "=============================================="
echo ""

python app.py
