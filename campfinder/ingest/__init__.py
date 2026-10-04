"""
Brochure-to-listing: turn a camp's website or PDF into a proposed listing.

    python -m campfinder.ingest https://example-camp.org
    python -m campfinder.ingest brochure.pdf --json

The output is a proposal with a confidence and a quoted source for every
field. A person checks it before it becomes a listing; the tool saves time,
it does not replace review.
"""
