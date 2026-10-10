"""OpenAI chat completions and Responses, with PII stripped before the wire.

Requires: pip install unseeing openai
"""

from openai import OpenAI

from unseeing import Scrubber
from unseeing.openai import UnseeingOpenAI

scrubber = Scrubber(resume=True, allow=["Acme Corp"])
client = UnseeingOpenAI(OpenAI(), scrubber=scrubber)

completion = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {
            "role": "user",
            "content": "Summarize this resume for Ava Chen, ava.chen@example.com.",
        }
    ],
)
print(completion.choices[0].message.content)

response = client.responses.create(
    model="gpt-4o-mini",
    input="Draft a reply to ava.chen@example.com about the Acme Corp role.",
)
print(response.output_text)
print(scrubber.audit().format())
