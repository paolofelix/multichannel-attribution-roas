# Findings: which ad channel actually earns its budget?

**Short version:** if this business judged its ads on last click alone, it would overfund Microsoft brand search and underfund Meta prospecting. Once every click in the customer's path gets some credit, Meta's share of revenue rises by about a fifth and Microsoft's falls by about a third. Google Ads looks the same under every model.

The data is synthetic (July 2026, 3 ad platforms, 80 customers, 50 orders), so treat the numbers as a worked example of the method, not a benchmark.

---

## The problem

Google, Meta and Microsoft each report their own conversions, and each one counts the same customer if that customer clicked its ad at any point. Add the three reports together and you get more sales than the business made. A marketing team that splits budget by platform-reported ROAS is splitting it on numbers that overlap.

To get past that, I joined ad spend to actual orders and to each customer's click history, then asked a narrower question: who gets credit for a sale when a customer clicked several ads before buying?

## What I did

1. Pulled raw exports from three ad platforms into BigQuery. Each had its own quirks: Google reports cost in micros, Meta campaign names were inconsistently cased, Microsoft uses US-style dates, and one channel showed up under six different source labels.
2. Cleaned everything into one table with the same columns and units for every platform.
3. Built each customer's click path for the 30 days before their order.
4. Split the credit for each order three ways:
   - **Last click:** the final ad clicked gets 100%.
   - **Linear:** every click gets an equal share.
   - **Time decay:** recent clicks get more, with weight halving every 7 days.
5. Compared each channel's share of credited revenue with its share of spend.

The full pipeline is in `/sql` (BigQuery) and `/python` (pandas version that produces the charts). Both give identical results.

---

## Finding 1: most buyers click more than one ad first

![Path length](charts/02_path_length.png)

40 of the 50 orders (80%) came after two or more ad clicks, and 68% of orders involved two or more channels. A single-touch model has to throw away information on four out of five sales. That alone is the case for looking past last click.

## Finding 2: last click overstates Microsoft brand search

![Revenue by model](charts/03_revenue_by_model.png)

Under last click, Microsoft gets $1,114 of revenue. Under time decay it gets $762, about 32% less. Most Microsoft clicks in this data are brand searches that happen right before purchase, from people who had already clicked a Google or Meta ad earlier in the month. Last click hands the whole sale to that final search.

## Finding 3: last click understates Meta prospecting

Meta tends to appear at the start of the path and rarely at the end. Its credited revenue goes from $1,661 under last click to $2,043 under linear (+23%) and $2,003 under time decay (+21%).

## Finding 4: what this means for budget

![Efficiency index](charts/04_efficiency_index.png)

The efficiency index compares a channel's share of credited revenue with its share of spend. At 1.0 the channel earns exactly the credit its budget would predict.

| Channel | Share of spend | Last click | Linear | Time decay |
|---|---|---|---|---|
| Google Ads | 49% | 1.00 | 1.00 | 1.00 |
| Meta Ads | 39% | 0.79 | 0.98 | 0.96 |
| Microsoft Ads | 12% | 1.65 | 1.06 | 1.13 |

Read on last click, Microsoft looks like the obvious place to add budget and Meta looks like the obvious place to cut. Under either multi-touch model that gap mostly closes. Microsoft still comes out slightly ahead, but nowhere near 1.65, and Meta lands close to break-even.

## Recommendations

1. **Don't cut Meta prospecting on last-click numbers.** It starts paths that other channels finish. Cutting it would likely shrink the brand searches that make Microsoft and Google look good.
2. **Use time decay as the default view in budget reviews.** It still favors the clicks closest to the sale, which matches how most teams think about intent, without giving the last one all the credit.
3. **Move budget in small steps and measure.** A modest shift toward Microsoft is defensible. Pair it with a holdout test (pause or reduce spend in some regions and compare) before treating any of these models as proof.

## Limitations

- **Synthetic and small.** 80 customers and 50 orders is enough to show the method, not to set a real budget. Absolute ROAS here is not meaningful.
- **Clicks only.** A large part of Meta's influence comes from ad views that never get clicked. Click-based paths understate it, so the Meta finding is probably conservative.
- **These models assign credit; they don't prove cause.** None of them can say whether a sale would have happened without the ad. That needs an incrementality test.

## What I'd do next with real data

- Run a geo holdout test on Meta prospecting to measure its actual incremental effect.
- Compare these rule-based models with Google Analytics data-driven attribution.
- Build a Looker Studio dashboard on the reporting views so the team can switch models themselves.
