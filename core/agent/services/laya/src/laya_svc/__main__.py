"""`python -m laya_svc` - compose the app (fail-loud without LAYA_CHECKPOINT,
P14) and serve it with the config.v1 env contract."""
import uvicorn

from laya_svc.main import HOST, LOG_LEVEL, PORT, create_app

if __name__ == "__main__":
    app = create_app()
    uvicorn.run(app, host=HOST, port=PORT, log_level=LOG_LEVEL.lower())
