# gunicorn.conf.py
import multiprocessing

# Worker processes
workers = 1  # or multiprocessing.cpu_count() * 2 + 1
timeout = 120  # seconds
keepalive = 5
