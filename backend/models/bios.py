from sqlmodel import SQLModel


class BiosItem(SQLModel):
    slug: str
    name: str
    platform: str
    bios_path: str
    guidance_text: str
    guidance_url: str
    is_present: bool
    required: bool = True
