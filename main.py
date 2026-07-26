import asyncio

from app.run.dispatcher import dispatch_broker

if __name__ == "__main__":
    asyncio.run(dispatch_broker())
