# MED RSM PoC — QA Log

One row per planned day. Use `—` when a column doesn't apply yet.

Since there is no SMTP delivery log, this file is the AUTHORITATIVE record of
what was sent when. After each send, verify the message appears in your Sent
Mail folder and record the sent timestamp in the `Sent UTC` column.

| Date | Artifact | Sent? | Sent UTC | QA time | Corrections made | RSM replied? | Reply class | Sponsor-worthy? | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 2026-05-DD | `poc/intelligence-brief-rsm/output/poc/med/2026-05-DD/email.html` | yes/no/skip | 2026-05-DDT07:32Z | 7m | "fixed Palermo personnel count" | yes/no | useful / noise / missed context / false positive | yes/no | free-form |

Notes on columns:
- `Artifact` — path to the rendered `email.html` (the SOURCE artifact). The
  operator-sent email is the DELIVERED artifact and lives in your mail
  client's Sent folder — not on disk.
- `Sent?` — `yes` = pasted and sent, `no` = blocked (validator/QA), `skip` =
  planned skip (e.g. weekend, agreed with RSM).
- `Sent UTC` — verify from your Sent Mail timestamp after sending, not from
  when you ran the runner.
- `Reply class` — the G14 taxonomy. `Sponsor-worthy?` flags rows that should
  be quoted verbatim in the sponsor memo.
