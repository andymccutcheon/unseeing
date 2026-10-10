"""Anthropic Messages API wrapper.

Requires: pip install unseeing anthropic
"""

from anthropic import Anthropic

from unseeing import Scrubber
from unseeing.anthropic import UnseeingAnthropic

client = UnseeingAnthropic(Anthropic(), scrubber=Scrubber(resume=True))
message = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=200,
    messages=[
        {
            "role": "user",
            "content": "Is Priya Nair (priya.nair@example.co.uk) a fit for payments?",
        }
    ],
)
print(message.content)
