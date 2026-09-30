"""
Local/dev entrypoint: `python run.py`. In production, run with gunicorn
instead (see README) - but always with exactly 1 worker, since the daily
scheduler lives in-process and would double-fire with more than one.
"""
import logging

from app.config import Config
from app.web import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = create_app()

if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=False)
