from fastapi import FastAPI

from verify import router as verify_router

app = FastAPI(title="Ecuery API")
app.include_router(verify_router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
