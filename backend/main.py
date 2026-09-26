from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv(Path(__file__).parent / ".env.local")

from verify import router as verify_router
from voice import router as voice_router

app = FastAPI(title="Ecuery API")
app.include_router(verify_router)
app.include_router(voice_router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
