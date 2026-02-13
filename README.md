## Quick Start

### 1. Clone and Setup

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate
OR
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

```bash
# Copy environment example
cp env.example .env

# Edit .env file with your configuration
# Update database URL, secret key, etc.
```

### 3. Database Setup

```bash
# Initialize Alembic
alembic init alembic

# Create initial migration
alembic revision --autogenerate -m "Changes"

# Run migrations
alembic upgrade head
```

### 4. Run the Application

```bash
# Development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

# Production server
uvicorn app.main:app --host 0.0.0.0 --port 8015 --reload
```

### 5. Celery worker (REMOVED)

# CELERY REMOVED - No longer needed
# celery -A app.core.celery worker --loglevel=info --pool=solo -n worker1@%h