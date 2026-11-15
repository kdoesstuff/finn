# Network (phase G), 15 Nov 2026 sprint

**Built.** A synthetic network for the demo investor (`db/seed/network.json`, LinkedIn-format
`db/seed/Connections.csv`): 150 fictional people (91 direct contacts, 59 reached through one),
careers at the 21 covered companies and at clearly fictional firms, schools, how the investor knows
each, tie strength and last contact. Generated deterministically (`python -m finn.network_seed`); a
test checks the committed files are its output, that no name is on a blocklist of well-known people
(including those named in the covered companies' filings), and that every covered company has at
least three people. Real companies appear only as employers; no fact about a real person is stated,
and nobody in the network is matched to a person named in a filing (that needs evidence-based entity
resolution, G3, not built).

`0004_network.sql`: people, roles, schools, edges, every row owned by one investor under RLS; the
API role may only read; ingest sees nothing; deleting the investor deletes the network. Loaded by
the admin: `python scripts/ingest.py seed-network`.

Questions, all in code, no model (a test checks no module both reads the network and imports the
model router): who worked at a company; who can best explain an event there (insiders by function,
then sector peers, specialists, the value chain, ranked by tie strength, with the reason and the
path); diligence on a person (career, overlaps with the investor, what to ask); expertise by sector
and function; strong ties gone quiet, with a recent filing where they worked as the reason to call;
and a free-text `ask` that picks the question type. Current employees of a listed company carry a
caution: ask about what is public, never about unpublished price-sensitive information.

API (`api/routes_network.py`): `/v1/network/company/{symbol}`, `/person/{id}`, `/ask?q=`, and
`who_to_call` on digest items, only for `full` sessions with the network on; a `core` session gets
the same 404 as a route that does not exist. Web: "Your network" screen and "Who in your network can
explain this" on brief items, behind a build-time constant; the core bundle contains no network code
(checked in `e2e/build.spec.ts`; only the screen's CSS rules, class names, remain in the core CSS).

**Not built.** Importing a real Connections.csv and a delete-everything endpoint (the demo investor is
read-only); entity resolution against names in filings (G3); "who to call" on the Pull page (the
`WhoToCall` component and `/v1/network/company/{symbol}` are ready for it).
