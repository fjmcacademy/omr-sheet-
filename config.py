import os
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fjmc_omr.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
ADMIN_KEY = os.getenv("ADMIN_KEY", "change-this-admin-key")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))
