#!/bin/bash
# Arrenca el servidor de demo per gravar el video
cd "$(dirname "$0")"
source venv/bin/activate
rm -f demo_video.db

python3 << 'EOF'
import fakeredis
import app.extensions
app.extensions.redis_client = fakeredis.FakeRedis()
import app.routes.auth as auth_mod
auth_mod.redis_client = app.extensions.redis_client

from app import create_app
from app.config import Settings
from app.extensions import db

a = create_app(Settings(
    database_url='sqlite:///demo_video.db',
    redis_url='redis://localhost:6379/15',
    jwt_secret='demo-secret-key-32-chars-long-1234'
))
with a.app_context():
    db.create_all()
print("\n>>> Servidor llest! Ara executa 'bash run_demo.sh' a l'altra terminal\n")
a.run(port=5556, debug=False)
EOF
