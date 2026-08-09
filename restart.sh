set -e
cd ~/fimobook
source venv/bin/activate
echo "🔸 기존 Gunicorn 프로세스 종료 중..."
pkill -f -TERM "venv/bin/gunicorn app:app --bind 0.0.0.0:8000" || true
sleep 3
pgrep -f "venv/bin/gunicorn app:app --bind 0.0.0.0:8000" && \
  pkill -f -KILL "venv/bin/gunicorn app:app --bind 0.0.0.0:8000" || true
echo "🔸 새 Gunicorn 서버 시작..."
nohup venv/bin/gunicorn app:app --bind 0.0.0.0:8000 \
  --workers 2 --timeout 120 --graceful-timeout 30 \
 --access-logfile - --error-logfile - > gunicorn.log 2>&1 &
echo "✅ Gunicorn restarted successfully!"
