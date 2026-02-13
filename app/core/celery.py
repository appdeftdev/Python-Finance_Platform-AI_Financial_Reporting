# CELERY REMOVED - This file is no longer used
# All Celery functionality has been removed from the application

# from celery import Celery
# from app.core.config import settings
# import os
# import dotenv

# # Load environment variables from .env file
# dotenv.load_dotenv()

# # Get Redis URL from environment ONLY - no hardcoded fallbacks
# REDIS_URL = os.getenv("REDIS_URL")
# CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
# CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

# # Validate that required environment variables are set
# if not REDIS_URL:
#     raise ValueError("REDIS_URL environment variable is required. Please set it in your .env file.")

# if not CELERY_BROKER_URL:
#     raise ValueError("CELERY_BROKER_URL environment variable is required. Please set it in your .env file.")

# if not CELERY_RESULT_BACKEND:
#     raise ValueError("CELERY_RESULT_BACKEND environment variable is required. Please set it in your .env file.")

# # Debug logging
# print(f"REDIS_URL: {REDIS_URL}")
# print(f"CELERY_BROKER_URL: {CELERY_BROKER_URL}")
# print(f"CELERY_RESULT_BACKEND: {CELERY_RESULT_BACKEND}")

# # Celery configuration
# celery_app = Celery(
#     "pnl_formula_generator",
#     broker=CELERY_BROKER_URL,
#     backend=CELERY_RESULT_BACKEND,
#     include=["app.tasks.formula_generation_tasks"]
# )

# # Celery settings
# celery_app.conf.update(
#     task_serializer="json",
#     accept_content=["json"],
#     result_serializer="json",
#     timezone="UTC",
#     enable_utc=True,
#     task_track_started=True,
#     task_time_limit=30 * 60,  # 30 minutes
#     task_soft_time_limit=25 * 60,  # 25 minutes
#     worker_prefetch_multiplier=1,
#     worker_max_tasks_per_child=1000,
#     broker_connection_retry_on_startup=True,
# )

# # Optional: Configure result backend for task status tracking
# celery_app.result_backend_transport_options = {
#     "master_name": "mymaster",
#     "visibility_timeout": 3600,
# }