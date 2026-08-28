from fastapi import FastAPI


def create_app() -> FastAPI:
    api = FastAPI(title="Opportunity OS", version="0.1.0")

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "opportunity-os"}

    return api


app = create_app()
