from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """NM-HireX application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # ---------------------------------------------------------
    # DATABASE
    # ---------------------------------------------------------
    DATABASE_URL: str

    # ---------------------------------------------------------
    # AI / LLM
    # ---------------------------------------------------------
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    OPENAI_API_KEY: str = ""

    # ---------------------------------------------------------
    # AUTHENTICATION
    # ---------------------------------------------------------
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ---------------------------------------------------------
    # AI MODELS
    # ---------------------------------------------------------
    EXTRACTION_MODEL: str = "openai/gpt-oss-120b"
    EVALUATION_MODEL: str = "openai/gpt-oss-120b"

    # ---------------------------------------------------------
    # RESUME / CANDIDATE MATCHING
    # ---------------------------------------------------------
    TOP_K_VECTOR: int = 150
    SEMANTIC_TOP_K: int = 100
    TOP_N: int = 50

    # ---------------------------------------------------------
    # DIRECTORIES
    # ---------------------------------------------------------
    RESUME_DIR: str = "data/resumes"
    JD_DIR: str = "data/job_descriptions"

    # ---------------------------------------------------------
    # RESUME MATCHING API
    # ---------------------------------------------------------
    RESUME_MATCHING_BASE_URL: str = (
        "https://d4u8k6edt3njs.cloudfront.net/api/public/resume-matching/v1"
    )

    RESUME_MATCHING_API_KEY: str = ""

    RESUME_MATCHING_TIMEOUT_SECONDS: int = 60

    RESUME_MATCHING_POLL_MAX_ATTEMPTS: int = 6

    RESUME_MATCHING_POLL_DEFAULT_WAIT_SECONDS: int = 5

    # ---------------------------------------------------------
    # OUTREACH
    # ---------------------------------------------------------
    OUTREACH_TOP_N: int = 50

    # ---------------------------------------------------------
    # WHATSAPP / NMVE
    # ---------------------------------------------------------
    WHATSAPP_API_KEY: str = ""

    WHATSAPP_BASE_URL: str = (
        "https://nmve.io/whatsapp/api/integrations/whatsapp/messages"
    )

    WHATSAPP_STAGE_NUMBER: str = ""

    WHATSAPP_CALLBACK_URL: str = (
        "https://nmhirex.onrender.com/api/webhooks/whatsapp"
    )

    # Template used for the initial candidate shortlisting outreach
    WHATSAPP_TEMPLATE_NAME: str = "candidate_shortlisted_outreach"

    WHATSAPP_TEMPLATE_LANGUAGE: str = "en"

    # Company name injected into the outreach template body params
    WHATSAPP_COMPANY_NAME: str = "the company"

    # ---------------------------------------------------------
    # WHATSAPP TEST MODE
    # ---------------------------------------------------------
    # When True, all outgoing WhatsApp messages will be sent
    # to WHATSAPP_TEST_NUMBER instead of the candidate's number.
    WHATSAPP_TEST_MODE: bool = False
    WHATSAPP_TEST_NUMBER: str = ""

    # Test number.
    # You can override this from Render Environment Variables.
   

    # ---------------------------------------------------------
    # FRONTEND / SCHEDULING
    # ---------------------------------------------------------
    FRONTEND_URL: str = "http://localhost:5173"

    # ---------------------------------------------------------
    # WEBHOOK
    # ---------------------------------------------------------
    # Optional webhook verification secret.
    WEBHOOK_SECRET: str = ""


settings = Settings()