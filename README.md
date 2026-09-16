# FIMOBOOK

FC 모바일 선수 검색, 선수 비교, 선수 리뷰, 갱신시간, 쿠폰 및 커뮤니티 기능을 제공하는 Flask 웹 애플리케이션입니다.

## Production structure

- Application entry point: `app.py`
- Templates: `templates/`
- Static source assets: `static/`
- Data synchronization utilities: `scripts/`
- Database migrations: `migrations/`

The production service runs on Ubuntu with Gunicorn and systemd. Runtime configuration is supplied through environment variables and is intentionally excluded from this repository.

## Excluded runtime files

Secrets, databases, logs, user uploads, virtual environments, and the multi-gigabyte generated player image directories (`static/card/`, `static/faceon/`) are not committed. Those assets remain on the production server and can be regenerated or synchronized separately.

## Local setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```
