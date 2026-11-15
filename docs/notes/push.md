# Push stream (phase D), 15 Nov 2026

Built, and tested at every layer (pipeline, API contract, web unit, Playwright at 360 px):

- **D1 Results in the brief.** A results filing for a holding carries `results`: the quarter's
  numbers from its stored XBRL, computed by the parser's own code exactly as `stored.card` computes
  them (a test asserts equality), consolidated where the company files it, bank template where it
  applies. The headline is written from the numbers ("Q2 FY27 results: revenue ₹980 cr, up 11.4%
  YoY; PAT ₹104 cr, up 30.0% YoY"). The card is attached only when the filing's quarter (ended up
  to 75 days before it) is stored: no number is ever estimated. NSE's leftover sentence fragments
  ("the financial results for ...") now start with a capital.
- **D4 Moves.** Every session's close in the window is judged by `alerts.signals_for` against the
  bars before it, with the investor's thresholds from `finn.prefs` (defaults otherwise). A move a
  filing may explain is attached to it (`rank.reaction_window`); the rest are `unexplained_moves`,
  shown as "Moves without a filing". A day on which NSE's previous close differs from the stored
  one by more than 2% (a split, bonus or rights adjustment) is not a move.
- **D3 Pledges.** `portfolio.pledges` lists holdings whose promoters have pledged shares, with the
  change since NSE's previous disclosure, shown as "Promoter pledges", "as published by NSE on".

Still one round trip for the holdings' data and one for the filings: results (only the facts the
card reads), bars, thresholds, names and pledges travel as JSON in the first statement.

Not built: per-investor alert categories and thresholds in the UI (the API reads `finn.prefs`, but
there is no settings screen), the lender template distinct from the bank one, explained moves for
filings just before the window, and EBITDA guidance against delivery (phase E).

Noted while building: the 9 Nov pledge snapshot's rows carry publication times from 16:30:32 to
16:31:54, not one single time as DECISIONS.md says ("every row carrying the same publication time").
