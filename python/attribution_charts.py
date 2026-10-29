"""
Multi-channel attribution: Python version of the BigQuery pipeline, plus charts.

Reads the 5 CSVs in ../data, applies the same cleaning and attribution logic
as the SQL files (30-day lookback; last click, linear and 7-day time decay),
prints a summary table and saves 4 charts to python/charts.

Run:  python python/attribution_charts.py      (from the repo root)
Needs: pandas, matplotlib
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
CHART_DIR = REPO_ROOT / "python" / "charts"

LOOKBACK_DAYS = 30
HALF_LIFE_DAYS = 7
MODELS = ["Last click", "Linear", "Time decay (7d)"]

CHANNEL_COLORS = {            # one fixed color per channel, used in every chart
    "Google Ads": "#2a78d6",
    "Meta Ads": "#eb6834",
    "Microsoft Ads": "#1baf7a",
}
MODEL_COLORS = {              # single-hue ramp: light -> dark
    "Last click": "#b7cdea",
    "Linear": "#6f9bd6",
    "Time decay (7d)": "#1f4f8f",
}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({
    "figure.dpi": 150,
    "font.size": 10,
    "axes.edgecolor": GRID,
    "axes.labelcolor": MUTED,
    "axes.titlecolor": INK,
    "axes.titleweight": "bold",
    "axes.titlesize": 12,
    "axes.titlelocation": "left",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "legend.frameon": False,
})


# ---------------------------------------------------------------------------
# 1. Load and clean (same rules as 02_udfs.sql and 03_staging.sql)
# ---------------------------------------------------------------------------
def to_num(series):
    """Text -> number. Strips spaces, thousands separators and currency symbols."""
    cleaned = series.astype(str).str.replace(r"[,$₱\s]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


def to_dt(series):
    """Text -> datetime. Accepts 2026-07-01, 07/01/2026, 7/1/2026, with or without times."""
    return pd.to_datetime(series.astype(str).str.strip(), format="mixed", errors="coerce")


def load_ad_performance():
    google = pd.read_csv(DATA_DIR / "google_ads_raw.csv", dtype=str)
    meta = pd.read_csv(DATA_DIR / "meta_ads_raw.csv", dtype=str)
    microsoft = pd.read_csv(DATA_DIR / "microsoft_ads_raw.csv", dtype=str)

    frames = [
        pd.DataFrame({
            "date": to_dt(google["Day"]),
            "channel": "Google Ads",
            "campaign": google["Campaign"].str.strip().str.upper(),
            "clicks": to_num(google["Clicks"]),
            "spend": to_num(google["Cost (micros)"]) / 1_000_000,  # micros -> currency
            "platform_revenue": to_num(google["Conv. value"]),
        }),
        pd.DataFrame({
            "date": to_dt(meta["date_start"]),
            "channel": "Meta Ads",
            "campaign": meta["campaign_name"].str.strip().str.upper(),  # fixes case + spaces
            "clicks": to_num(meta["link_clicks"]),
            "spend": to_num(meta["amount_spent"]),
            "platform_revenue": to_num(meta["purchase_value"]).fillna(0),
        }),
        pd.DataFrame({
            "date": to_dt(microsoft["TimePeriod"]),  # MM/DD/YYYY
            "channel": "Microsoft Ads",
            "campaign": microsoft["CampaignName"].str.strip().str.upper(),
            "clicks": to_num(microsoft["Clicks"]),
            "spend": to_num(microsoft["Spend"]),
            "platform_revenue": to_num(microsoft["Revenue"]),
        }),
    ]
    return pd.concat(frames, ignore_index=True)


def map_channel(source):
    s = str(source).lower()
    if "google" in s:
        return "Google Ads"
    if "facebook" in s or s.startswith("fb") or "meta" in s:
        return "Meta Ads"
    if "bing" in s or "microsoft" in s:
        return "Microsoft Ads"
    return "Other"


def load_touchpoints():
    tp = pd.read_csv(DATA_DIR / "touchpoints.csv", dtype=str)
    return pd.DataFrame({
        "touch_id": tp["touch_id"].str.strip(),
        "user_id": tp["user_id"].str.strip(),
        "touch_time": to_dt(tp["touch_time"]),
        "channel": tp["source"].map(map_channel),
        "campaign": tp["campaign"].str.strip().str.upper(),
    })


def load_conversions():
    cv = pd.read_csv(DATA_DIR / "conversions.csv", dtype=str)
    return pd.DataFrame({
        "order_id": cv["order_id"].str.strip(),
        "user_id": cv["user_id"].str.strip(),
        "conversion_time": to_dt(cv["conversion_time"]),
        "revenue": to_num(cv["revenue"]),
    })


# ---------------------------------------------------------------------------
# 2. Attribution (same logic as 05_attribution_models.sql)
# ---------------------------------------------------------------------------
def build_attribution(conversions, touchpoints):
    paths = conversions.merge(touchpoints, on="user_id")
    window_start = paths["conversion_time"] - pd.Timedelta(days=LOOKBACK_DAYS)
    paths = paths[(paths["touch_time"] <= paths["conversion_time"])
                  & (paths["touch_time"] >= window_start)].copy()

    paths["days_before"] = (paths["conversion_time"] - paths["touch_time"]).dt.total_seconds() / 86400
    paths = paths.sort_values(["order_id", "touch_time", "touch_id"])
    paths["path_length"] = paths.groupby("order_id")["touch_id"].transform("count")
    is_last = ~paths.duplicated("order_id", keep="last")

    paths["Last click"] = is_last.astype(float)
    paths["Linear"] = 1 / paths["path_length"]
    weight = 0.5 ** (paths["days_before"] / HALF_LIFE_DAYS)
    paths["Time decay (7d)"] = weight / weight.groupby(paths["order_id"]).transform("sum")

    long = paths.melt(
        id_vars=["order_id", "revenue", "channel", "campaign", "path_length"],
        value_vars=MODELS, var_name="model", value_name="credit",
    )
    long["attributed_revenue"] = long["credit"] * long["revenue"]
    return paths, long


# ---------------------------------------------------------------------------
# 3. Channel x model summary (same logic as 06_reporting_views.sql)
# ---------------------------------------------------------------------------
def channel_summary(ads, credits):
    spend = ads.groupby("channel")["spend"].sum()
    revenue = credits.pivot_table(index="channel", columns="model",
                                  values="attributed_revenue", aggfunc="sum").reindex(columns=MODELS)
    share_of_spend = spend / spend.sum()
    share_of_credit = revenue / revenue.sum()
    efficiency = share_of_credit.div(share_of_spend, axis=0)
    return spend, revenue, efficiency


# ---------------------------------------------------------------------------
# 4. Charts
# ---------------------------------------------------------------------------
def save(fig, name):
    CHART_DIR.mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(CHART_DIR / name, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"saved charts/{name}")


def chart_daily_spend(ads):
    daily = ads.groupby(["date", "channel"])["spend"].sum().unstack()
    fig, ax = plt.subplots(figsize=(8, 4))
    for channel, color in CHANNEL_COLORS.items():
        ax.plot(daily.index, daily[channel], color=color, linewidth=2)
        ax.annotate(channel, (daily.index[-1], daily[channel].iloc[-1]),
                    xytext=(6, 0), textcoords="offset points", va="center", color=INK)
    ax.set_title("Daily ad spend by channel, July 2026")
    ax.set_ylabel("Spend ($)")
    ax.set_ylim(bottom=0)
    ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%b %d"))
    ax.grid(axis="x", visible=False)
    save(fig, "01_daily_spend.png")


def chart_path_length(paths):
    per_order = paths.groupby("order_id").agg(touches=("touch_id", "count"),
                                              channels=("channel", "nunique"))
    counts = per_order["touches"].value_counts().sort_index()
    multi_channel = (per_order["channels"] > 1).mean()

    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(counts.index.astype(str), counts.values, color="#2a78d6", width=0.6)
    ax.bar_label(bars, padding=3, color=INK)
    ax.set_title("Most customers click more than one ad before buying")
    ax.set_xlabel("Ad clicks in the 30 days before purchase")
    ax.set_ylabel("Orders")
    ax.grid(axis="x", visible=False)
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.text(0.98, 0.95, f"{multi_channel:.0%} of orders touched 2+ channels",
            transform=ax.transAxes, ha="right", va="top", color=MUTED)
    save(fig, "02_path_length.png")


def chart_revenue_by_model(revenue):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    channels = list(CHANNEL_COLORS)
    width = 0.26
    for i, model in enumerate(MODELS):
        x = [c + (i - 1) * width for c in range(len(channels))]
        bars = ax.bar(x, revenue.loc[channels, model], width=width - 0.02,
                      color=MODEL_COLORS[model], label=model)
        ax.bar_label(bars, labels=[f"${v:,.0f}" for v in revenue.loc[channels, model]],
                     padding=2, fontsize=8, color=MUTED)
    ax.set_xticks(range(len(channels)), channels)
    ax.set_title("Revenue credited to each channel under each model")
    ax.set_ylabel("Attributed revenue ($)")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper right", ncols=3)
    ax.set_ylim(0, revenue.values.max() * 1.2)
    save(fig, "03_revenue_by_model.png")


def spread_labels(values, min_gap):
    """Nudge label positions apart so end-of-line labels never overlap."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    placed = list(values)
    for prev, cur in zip(order, order[1:]):
        placed[cur] = max(placed[cur], placed[prev] + min_gap)
    return placed


def chart_efficiency(efficiency):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = list(range(len(MODELS)))
    last = len(MODELS) - 1
    label_box = dict(facecolor="white", edgecolor="none", pad=1)

    ax.axhline(1.0, color=MUTED, linewidth=1, linestyle="--")
    ax.text(0.5, 1.0, "1.0 = credit matches spend", ha="center", va="bottom",
            color=MUTED, fontsize=8, bbox=label_box)

    channels = list(CHANNEL_COLORS)
    ends = efficiency.loc[channels, MODELS[-1]].tolist()
    starts = efficiency.loc[channels, MODELS[0]].tolist()
    end_pos = spread_labels(ends, 0.06)
    start_pos = spread_labels(starts, 0.06)

    for i, channel in enumerate(channels):
        values = efficiency.loc[channel, MODELS].values
        ax.plot(x, values, color=CHANNEL_COLORS[channel], linewidth=2, marker="o",
                markersize=8, markeredgecolor="white", markeredgewidth=2, zorder=3)
        ax.annotate(f"{channel}  {ends[i]:.2f}", (last, end_pos[i]), xytext=(12, 0),
                    textcoords="offset points", va="center", color=INK, bbox=label_box)
        ax.annotate(f"{starts[i]:.2f}", (0, start_pos[i]), xytext=(-12, 0),
                    textcoords="offset points", va="center", ha="right", color=INK, bbox=label_box)

    ax.set_xticks(x, MODELS)
    ax.set_xlim(-0.4, last + 0.9)
    ax.set_title("Last click overstates Microsoft and understates Meta")
    ax.set_ylabel("Efficiency index\n(share of credit / share of spend)")
    ax.grid(axis="x", visible=False)
    save(fig, "04_efficiency_index.png")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
def main():
    ads = load_ad_performance()
    touchpoints = load_touchpoints()
    conversions = load_conversions()

    # Data quality check (same as 04_data_quality_checks.sql)
    print(f"ad rows {len(ads)}, touchpoints {len(touchpoints)}, orders {len(conversions)}")
    print(f"unparsed dates: {ads['date'].isna().sum() + touchpoints['touch_time'].isna().sum()}"
          f" | unmapped sources: {(touchpoints['channel'] == 'Other').sum()}")

    paths, credits = build_attribution(conversions, touchpoints)
    spend, revenue, efficiency = channel_summary(ads, credits)

    summary = pd.concat([spend.rename("spend"), revenue,
                         efficiency.add_suffix(" index")], axis=1).round(2)
    print("\n", summary.to_string(), "\n")

    chart_daily_spend(ads)
    chart_path_length(paths)
    chart_revenue_by_model(revenue)
    chart_efficiency(efficiency)


if __name__ == "__main__":
    main()
