"""Target data models. Claude's output must pass these before we accept it."""
import re

from pydantic import BaseModel, Field, field_validator  # type: ignore[reportMissingImports]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Contact(BaseModel):
    name: str = Field(min_length=1, description="Person's full name as written in the text")
    email: str | None = Field(default=None, description="Email address, if present")
    phone: str | None = Field(default=None, description="Phone number, if present")
    company: str | None = Field(default=None, description="Company or organisation")
    job_title: str | None = Field(default=None, description="Role or job title")

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str | None) -> str | None:
        if v is not None and not EMAIL_RE.match(v):
            raise ValueError(f"'{v}' is not a valid email address")
        return v.lower() if v else v

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        digits = re.sub(r"\D", "", v)
        if not 7 <= len(digits) <= 15:
            raise ValueError(f"'{v}' must contain 7-15 digits")
        return ("+" if v.strip().startswith("+") else "") + digits


class ContactList(BaseModel):
    """Every person mentioned in the text, with their contact details."""
    contacts: list[Contact] = Field(description="All people found; empty list if none")
