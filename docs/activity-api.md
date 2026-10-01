# CampFinder Activity API v1

Verified, structured data on kids' programs for family assistants, apps and partners.
Camps in the Northeast US today; classes, lessons, leagues and after-school programs use
the same schema as they are added.

Base URL: `https://<api-host>/api/activity/v1`  ·  Interactive docs: `/docs#/Activity API v1`

## Authentication

Every data endpoint needs a key:

```
Authorization: Bearer cfa_live_...
```

Keys are issued per partner (`python -m campfinder.scripts.create_api_key "Partner" contact@partner.com`).
The default limit is 120 requests per minute; over it you get `429` with `Retry-After`.

## Terms in one paragraph

Show the `attribution` text and link wherever you display CampFinder data. Tell families
when a record is `unverified`. Send families to `url` or `registration_url` to register.
Don't resell the data. Don't send us anything that identifies a family.

## Endpoints

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/programs` | Search programs near a location for a child: `near`, `age`, `kind`, `format`, `category` (repeatable), `max_price_per_week`, `extended_care`, `transportation`, `meals`, `financial_aid`, `accredited`, `include_sessions`, `sort`, `limit`, `offset` |
| `GET` | `/programs/{id}` | One program with every session, policies and field-level verification |
| `GET` | `/programs/{id}/sessions` | A program's sessions |
| `GET` | `/sessions` | Open sessions in a date window: `near`, `age`, `category`, `starts_on_or_after`, `ends_on_or_before`, `open_only` |
| `GET` | `/sessions/{id}.ics` | Calendar file for one session. No key needed, so families can add it directly |
| `POST` | `/demand` | Report what a family looked for, especially when nothing fit. Anonymous; contact details are rejected |
| `GET` | `/schema` | JSON Schema for programs, sessions and demand signals. No key needed |

## Example

```bash
curl -G https://<api-host>/api/activity/v1/sessions \
  -H "Authorization: Bearer $CAMPFINDER_KEY" \
  --data-urlencode "near=Providence, RI" \
  -d age=8 -d category=STEM \
  -d starts_on_or_after=2027-07-06 -d ends_on_or_before=2027-07-10
```

Each result pairs a `session` (dates, price, availability, `calendar_url`) with its
`program` (provider, location, ages, price, logistics, `verification`, `registration_url`).

## Trust fields

`verification.status` is one of `team_verified`, `camp_verified`, `claimed`, `unverified`.
`fields_verified`, `fields_unverified` and `fields_missing` say which facts are confirmed,
so an assistant can say "price confirmed by the camp; refund policy not listed".

## Also available over MCP

The same search, sessions, details, compare and planning tools are served to MCP clients
(Claude, ChatGPT apps, other agents) at `/mcp`.
