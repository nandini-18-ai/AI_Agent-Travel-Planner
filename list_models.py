"""Print the Groq model IDs your API key can use.

Run:  python list_models.py
Then put one of the printed IDs in your .env file, for example:
    GROQ_MODEL=openai/gpt-oss-120b
"""

import sys

import requests

from config import get_secret

key = get_secret("GROQ_API_KEY")
if not key:
    sys.exit("GROQ_API_KEY not found. Add it to your .env file first.")

response = requests.get(
    "https://api.groq.com/openai/v1/models",
    headers={"Authorization": f"Bearer {key}"},
    timeout=15,
)
response.raise_for_status()
for model in sorted(response.json()["data"], key=lambda item: item["id"]):
    print(model["id"])
