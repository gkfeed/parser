from app.configs.workers import heavy_parsers
from app.core.worker_loop import main

if __name__ == "__main__":
    main(heavy_parsers)
