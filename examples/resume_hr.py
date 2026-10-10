"""HR / job-matching mode: stable pseudonyms across a conversation."""

from unseeing import Scrubber

scrubber = Scrubber(resume=True, scrub_orgs=False, allow=["Northwind"])

resume = """\
Jordan Blake
Designer
jordan.blake@example.org
(608) 555-0199
https://www.linkedin.com/in/jordan-blake

EXPERIENCE
Product Designer at Northwind — 2022–2025
"""

print(scrubber.scrub(resume))
print("--- follow-up ---")
print(scrubber.scrub("Should we advance Jordan? Northwind already cleared the role."))
print("--- audit ---")
print(scrubber.audit().format())
