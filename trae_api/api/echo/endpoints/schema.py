from pydantic import BaseModel


class Message(BaseModel):
    """Simple message model."""

    message: str
