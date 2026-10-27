from fastapi import APIRouter

from app.api import (
    admin,
    billing,
    businesses,
    chat,
    content,
    conversations,
    documents,
    feedback,
    law,
    search,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(chat.router)
api_router.include_router(conversations.router)
api_router.include_router(documents.router)
api_router.include_router(businesses.router)
api_router.include_router(feedback.router)
api_router.include_router(content.router)
api_router.include_router(billing.router)
api_router.include_router(search.router)
api_router.include_router(law.router)
api_router.include_router(admin.router)
