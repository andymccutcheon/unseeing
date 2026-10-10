"""30-second unseeing walkthrough. No API keys required."""

from unseeing import scrub

text = "Email Ava Chen at ava.chen@example.com or +1-555-010-0142."
scrubbed, vault = scrub(text, resume=True)
print(scrubbed)
# Email <PERSON_1> at <EMAIL_1> or <PHONE_1>.

print(vault.restore(scrubbed))
print(vault.audit().format())
