from pydantic_settings import BaseSettings


class BackendSettings(BaseSettings):
    base_url: str = "http://localhost:9000"
    timeout: float = 30.0

    model_config = {"env_prefix": "BACKEND_"}


class LLMSettings(BaseSettings):
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = ""

    model_config = {"env_prefix": "", "env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


class Settings(BaseSettings):
    log_level: str = "INFO"
    environment: str = "development"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
