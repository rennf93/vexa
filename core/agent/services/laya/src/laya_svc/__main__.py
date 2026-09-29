"""`python -m laya_svc` — run the service with the config.v1 env contract."""
import uvicorn

from laya_svc.main import HOST, LOG_LEVEL, PORT

if __name__ == "__main__":
    uvicorn.run("laya_svc.main:app", host=HOST, port=PORT, log_level=LOG_LEVEL.lower())
