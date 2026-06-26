from fastapi import FastAPI
from image2pptx.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="image2pptx-service")
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("image2pptx.api.app:app", host="0.0.0.0", port=8000, reload=False)
