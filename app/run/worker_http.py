from app.configs.workers import http_parsers
from app.core.worker_loop import main

if __name__ == "__main__":
    main(http_parsers)
