import json
from pydantic import BaseModel
from typing import List, Dict, Any

class ChatRequest(BaseModel):
    message: str
    image: str | None = None
    history: List[Dict[str, Any]] = []

payload_json = """
{
  "message": "帮忙分析一下这份报告",
  "history": [
    {"role": "assistant", "content": "你好"},
    {"role": "user", "content": "帮忙分析一下这份报告", "image": "private://example_upload.jpg"}
  ]
}
"""

req = ChatRequest.parse_raw(payload_json)
print("Parsed history:", req.history)

has_image = False
for h in req.history:
    print("Checking h:", h)
    if h.get("image"):
        print("Found image:", h.get("image"))
        has_image = True

print("has_image:", has_image)
