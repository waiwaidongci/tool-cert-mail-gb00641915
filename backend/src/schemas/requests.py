from pydantic import BaseModel, ConfigDict, Field

class Request(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

class Credentials(Request):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

class Upload(Request):
    name: str = Field(min_length=1, max_length=120)
    filename: str = Field(min_length=1, max_length=160)
    csv_text: str = Field(min_length=1, max_length=2_000_000)

class BatchRequest(Request):
    dataset_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)

class PostRequest(Request):
    note: str = Field(default='', max_length=500)
