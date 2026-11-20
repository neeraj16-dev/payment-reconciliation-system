from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.reconcile import router

app = FastAPI(
    title="Payment Reconciliation API",
    description="Reconciles platform transactions against bank settlements.",
    version="1.0.0",
)

# Vite dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "https://payment-reconciliation-system-self.vercel.app"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)
