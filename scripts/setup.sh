#!/bin/bash

echo "Setting up environment..."

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Initializing database..."
flask db init
flask db migrate -m "Initial migration."
flask db upgrade