from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .database import engine
from .models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create missing tables for a fresh development database.
    # Existing tables/columns are NOT altered by create_all().
    Base.metadata.create_all(bind=engine)
    
    import asyncio
    from .scheduler import check_interview_reminders
    
    async def run_scheduler():
        while True:
            try:
                # Run sync function in thread pool
                await asyncio.to_thread(check_interview_reminders)
            except Exception as e:
                print(f"Scheduler error: {e}")
            await asyncio.sleep(300) # Every 5 minutes
            
    task = asyncio.create_task(run_scheduler())
    yield
    task.cancel()


app = FastAPI(
    title="NM-HireX",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "https://nm-hire-x.vercel.app",
        "https://nm-hire-x-omega.vercel.app",
        "https://nm-hire-xv-2new.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root():
    return {
        "service": "NM-HireX",
        "status": "running",
    }
