"""
Multi-Channel Attribution & ROAS - interactive dashboard (Streamlit).

Rebuilds the same pipeline as python/attribution_charts.py from the CSVs in /data,
then lets the viewer change the attribution model, lookback window, time-decay
half-life and date range, and see how channel credit moves.

Run locally:  streamlit run dashboard/app.py      (from the repo root)
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPO_URL = "https://github.com/paolofelix/multichannel-attribution-roas"

CHANNELS = ["Google Ads", "Meta Ads", "Microsoft Ads"]
CHANNEL_COLORS = {"Google Ads": "#2a78d6", "Meta Ads": "#eb6834", "Microsoft Ads": "#1baf7a"}
MODELS = ["Last click", "Linear", "Time decay"]
MODEL_COLORS = {"Last click": "#b7cdea", "Linear": "#6f9bd6", "Time decay": "#1f4f8f"}

st.set_page_config(page_title="Attribution & ROAS Dashboard", page_icon="📊", layout="wide")


# ---------------------------------------------------------------------------
# 1. Load and clean (same rules as sql/02_udfs.sql and sql/03_staging.sql)
# ---------------------------------------------------------------------------
def to_num(series):
    return pd.to_numeric(series.astype(str).str.replace(r"[,$₱\s]", "", regex=True), errors="coerce")


def to_dt(series):
    return pd.to_datetime(series.astype(str).str.strip(), format="mixed", errors="coerce")


def map_channel(source):
    s = str(source).lower()
    if "google" in s:
        return "Google Ads"
    if "facebook" in s or s.startswith("fb") or "meta" in s:
        return "Meta Ads"
    if "bing" in s or "microsoft" in s:
        return "Microsoft Ads"
    return "Other"


@st.cache_data
def load_data():
    g = pd.read_csv(DATA_DIR / "google_ads_raw.csv", dtype=str)
    m = pd.read_csv(DATA_DIR / "meta_ads_raw.csv", dtype=str)
    ms = pd.read_csv(DATA_DIR / "microsoft_ads_raw.csv", dtype=str)
    ads = pd.concat([
        pd.DataFrame({"date": to_dt(g["Day"]), "channel": "Google Ads",
                      "campaign": g["Campaign"].str.strip().str.upper(),
                      "impressions": to_num(g["Impressions"]), "clicks": to_num(g["Clicks"]),
                      "spend": to_num(g["Cost (micros)"]) / 1_000_000,
                      "platform_conversions": to_num(g["Conversions"]),
                      "platform_revenue": to_num(g["Conv. value"])}),
        pd.DataFrame({"date": to_dt(m["date_start"]), "channel": "Meta Ads",
                      "campaign": m["campaign_name"].str.strip().str.upper(),
                      "impressions": to_num(m["impressions"]), "clicks": to_num(m["link_clicks"]),
                      "spend": to_num(m["amount_spent"]),
                      "platform_conversions": to_num(m["purchases"]).fillna(0),
                      "platform_revenue": to_num(m["purchase_value"]).fillna(0)}),
        pd.DataFrame({"date": to_dt(ms["TimePeriod"]), "channel": "Microsoft Ads",
                      "campaign": ms["CampaignName"].str.strip().str.upper(),
                      "impressions": to_num(ms["Impressions"]), "clicks": to_num(ms["Clicks"]),
                      "spend": to_num(ms["Spend"]),
                      "platform_conversions": to_num(ms["Conversions"]),
                      "platform_revenue": to_num(ms["Revenue"])}),
    ], ignore_index=True)

    tp_raw = pd.read_csv(DATA_DIR / "touchpoints.csv", dtype=str)
    tp = pd.DataFrame({
        "touch_id": tp_raw["touch_id"].str.strip(),
        "user_id": tp_raw["user_id"].str.strip(),
        "touch_time": to_dt(tp_raw["touch_time"]),
        "source_raw": tp_raw["source"],
        "channel": tp_raw["source"].map(map_channel),
        "campaign": tp_raw["campaign"].str.strip().str.upper(),
    })

    cv_raw = pd.read_csv(DATA_DIR / "conversions.csv", dtype=str)
    cv = pd.DataFrame({
        "order_id": cv_raw["order_id"].str.strip(),
        "user_id": cv_raw["user_id"].str.strip(),
        "conversion_time": to_dt(cv_raw["conversion_time"]),
        "revenue": to_num(cv_raw["revenue"]),
    })
    return ads, tp, cv


# ---------------------------------------------------------------------------
# 2. Attribution (same logic as sql/05_attribution_models.sql, but parameterised)
# ---------------------------------------------------------------------------
@st.cache_data
def build_attribution(tp, cv, lookback_days, half_life_days):
    paths = cv.merge(tp, on="user_id", how="inner")
    paths = paths[(paths["touch_time"] <= paths["conversion_time"])
                  & (paths["touch_time"] >= paths["conversion_time"] - pd.Timedelta(days=lookback_days))].copy()
    paths["days_before"] = (paths["conversion_time"] - paths["touch_time"]).dt.total_seconds() / 86400
    paths = paths.sort_values(["order_id", "touch_time", "touch_id"])

    grp = paths.groupby("order_id")
    paths["path_length"] = grp["touch_id"].transform("count")
    paths["touch_number"] = grp.cumcount() + 1
    paths["Last click"] = (paths["touch_number"] == paths["path_length"]).astype(float)
    paths["Linear"] = 1.0 / paths["path_length"]
    w = 0.5 ** (paths["days_before"] / half_life_days)
    paths["Time decay"] = w / w.groupby(paths["order_id"]).transform("sum")

    credits = paths.melt(
        id_vars=["order_id", "conversion_time", "revenue", "touch_id", "touch_time", "channel",
                 "campaign", "path_length", "touch_number", "days_before"],
        value_vars=MODELS, var_name="model", value_name="credit")
    credits["attributed_revenue"] = credits["credit"] * credits["revenue"]
    return paths, credits


def channel_table(ads, credits):
    spend = ads.groupby("channel").agg(spend=("spend", "sum"),
                                       platform_revenue=("platform_revenue", "sum"))
    rev = credits.pivot_table(index="channel", columns="model", values="attributed_revenue",
                              aggfunc="sum").reindex(CHANNELS).fillna(0)
    share_spend = spend["spend"] / spend["spend"].sum()
    share_rev = rev / rev.sum()
    eff = share_rev.div(share_spend, axis=0)
    return spend.reindex(CHANNELS), rev.reindex(columns=MODELS), eff.reindex(columns=MODELS), share_spend


def money(v):
    return f"${v:,.0f}"


# ---------------------------------------------------------------------------
# 3. Sidebar controls
# ---------------------------------------------------------------------------
ads, tp, cv = load_data()

st.sidebar.header("Controls")
model = st.sidebar.radio("Attribution model", MODELS, index=2,
                         help="Last click: 100% to the final click. Linear: equal split. "
                              "Time decay: recent clicks weigh more.")
lookback = st.sidebar.slider("Lookback window (days)", 7, 30, 30,
                             help="Clicks older than this before the order get no credit.")
half_life = st.sidebar.slider("Time-decay half-life (days)", 1, 14, 7,
                              help="A click this many days before the order gets half the weight "
                                   "of a same-day click. Only affects the Time decay model.")
dmin, dmax = ads["date"].min().date(), ads["date"].max().date()
date_range = st.sidebar.date_input("Date range (spend and orders)", (dmin, dmax),
                                   min_value=dmin, max_value=dmax)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
else:
    start, end = pd.Timestamp(dmin), pd.Timestamp(dmax)

st.sidebar.markdown("---")
st.sidebar.caption("Defaults (30-day lookback, 7-day half-life, full July) reproduce the "
                   "numbers in the README and FINDINGS.")
st.sidebar.markdown(f"[GitHub repo]({REPO_URL}) · [Findings]({REPO_URL}/blob/main/FINDINGS.md)")

# Filter by date: spend by ad date, orders by conversion date
ads_f = ads[ads["date"].between(start, end)]
cv_f = cv[cv["conversion_time"].dt.normalize().between(start, end)]
paths, credits = build_attribution(tp, cv_f, lookback, half_life)

if ads_f.empty or cv_f.empty or paths.empty:
    st.warning("No spend or orders in the selected date range. Widen the range in the sidebar.")
    st.stop()

spend_tbl, rev_tbl, eff_tbl, share_spend = channel_table(ads_f, credits)
credits_m = credits[credits["model"] == model]

# ---------------------------------------------------------------------------
# 4. Header and KPIs
# ---------------------------------------------------------------------------
st.title("Multi-Channel Attribution & ROAS")
st.markdown("Which ad channel actually earns its budget? Change the attribution model in the sidebar "
            "and watch credit move between **Google**, **Meta** and **Microsoft Ads**. "
            "*Synthetic data, July 2026: 3 ad platforms, 80 users, 50 orders.*")

total_spend = ads_f["spend"].sum()
actual_rev = cv_f["revenue"].sum()
attributed_orders = credits_m["order_id"].nunique()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Ad spend", money(total_spend))
k2.metric("Orders", f"{len(cv_f):,}", help="Orders in the date range")
k3.metric("Order revenue", money(actual_rev), help="Revenue from real orders, counted once.")
k4.metric("Ad clicks tracked", f"{len(tp):,}",
          help="Click-level touchpoints from 80 users, used to build each customer's path.")

if attributed_orders < len(cv_f):
    st.caption(f"ℹ️ {len(cv_f) - attributed_orders} order(s) have no ad click inside the "
               f"{lookback}-day lookback, so no channel gets credit for them.")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Channel credit", "Campaigns", "Customer paths", "Daily spend", "Data quality"])

# ---------------------------------------------------------------------------
# Tab 1: Channel credit
# ---------------------------------------------------------------------------
with tab1:
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Efficiency index by model")
        st.caption("Share of credited revenue ÷ share of spend. Above 1.0 = the channel earns more "
                   "credit than its share of budget.")
        fig = go.Figure()
        ends = {ch: eff_tbl.loc[ch, MODELS[-1]] for ch in CHANNELS}
        order = sorted(CHANNELS, key=ends.get)          # lowest end value gets its label below the line
        for ch in CHANNELS:
            vals = eff_tbl.loc[ch].tolist()
            pos = "bottom right" if ch == order[0] else "top right"
            fig.add_trace(go.Scatter(
                x=MODELS, y=vals, name=ch, mode="lines+markers+text",
                line=dict(color=CHANNEL_COLORS[ch], width=2),
                marker=dict(size=10, line=dict(color="white", width=2)),
                text=[f"{vals[0]:.2f}", "", f"{vals[-1]:.2f}"],
                textposition=[pos.replace("right", "center")] * 3,
                hovertemplate=f"<b>{ch}</b>: %{{y:.2f}}<extra></extra>"))
        fig.add_hline(y=1.0, line_dash="dash", line_color="#52514e")
        fig.update_layout(height=420, yaxis_title="Efficiency index", hovermode="x unified",
                          xaxis=dict(range=[-0.35, 2.25]),
                          legend=dict(orientation="h", y=-0.15), margin=dict(t=20))
        st.plotly_chart(fig, width="stretch")

    with c2:
        st.subheader("Revenue credited to each channel")
        st.caption("Same 50 orders, same total revenue: only the split changes.")
        long = rev_tbl.reset_index().melt(id_vars="channel", var_name="Model", value_name="Revenue")
        fig = px.bar(long, x="channel", y="Revenue", color="Model", barmode="group",
                     color_discrete_map=MODEL_COLORS, text_auto="$,.0f")
        fig.update_traces(textposition="outside", marker_line_color="white", marker_line_width=2,
                          hovertemplate="%{x}<br>%{fullData.name}: $%{y:,.0f}<extra></extra>")
        fig.update_layout(height=400, xaxis_title=None, yaxis_title="Attributed revenue ($)",
                          legend=dict(orientation="h", y=-0.15), margin=dict(t=20))
        st.plotly_chart(fig, width="stretch")

    st.subheader(f"Channel summary: {model}")
    summary = pd.DataFrame({
        "Spend": spend_tbl["spend"],
        "Share of spend": share_spend.reindex(CHANNELS),
        f"Attributed revenue ({model})": rev_tbl[model],
        "Share of credit": rev_tbl[model] / rev_tbl[model].sum(),
        "Efficiency index": eff_tbl[model],
    })
    st.dataframe(summary.style.format({
        "Spend": "${:,.0f}", "Share of spend": "{:.0%}", f"Attributed revenue ({model})": "${:,.0f}",
        "Share of credit": "{:.0%}", "Efficiency index": "{:.2f}"}),
        width="stretch")

    lc, td = eff_tbl.loc["Meta Ads", "Last click"], eff_tbl.loc["Meta Ads", "Time decay"]
    ms_lc, ms_td = eff_tbl.loc["Microsoft Ads", "Last click"], eff_tbl.loc["Microsoft Ads", "Time decay"]
    st.info(f"**Read-out:** on last click, Microsoft's index is **{ms_lc:.2f}** and Meta's is "
            f"**{lc:.2f}**. With time decay ({half_life}-day half-life) they move to **{ms_td:.2f}** "
            f"and **{td:.2f}**. Brand search closes sales that Meta prospecting often starts, so "
            "cutting Meta on last-click numbers would likely be a mistake.")

# ---------------------------------------------------------------------------
# Tab 2: Campaigns
# ---------------------------------------------------------------------------
with tab2:
    st.subheader(f"Campaign share of spend vs share of credit ({model})")
    camp = ads_f.groupby(["channel", "campaign"]).agg(
        spend=("spend", "sum"), clicks=("clicks", "sum")).reset_index()
    camp_rev = credits.pivot_table(index="campaign", columns="model", values="attributed_revenue",
                                   aggfunc="sum")
    for m_ in MODELS:
        camp[m_] = camp["campaign"].map(camp_rev[m_]).fillna(0)
    camp["Share of spend"] = camp["spend"] / camp["spend"].sum()
    camp["Share of credit"] = camp[model] / camp[model].sum()
    camp["Efficiency index"] = camp["Share of credit"] / camp["Share of spend"]
    camp = camp.sort_values(["channel", "campaign"])

    long = camp.melt(id_vars=["campaign", "channel"], value_vars=["Share of spend", "Share of credit"],
                     var_name="Measure", value_name="Share")
    fig = px.bar(long, y="campaign", x="Share", color="Measure", barmode="group", orientation="h",
                 color_discrete_map={"Share of spend": "#b7cdea", "Share of credit": "#1f4f8f"},
                 text_auto=".0%")
    fig.update_traces(marker_line_color="white", marker_line_width=2,
                      hovertemplate="%{y}<br>%{fullData.name}: %{x:.1%}<extra></extra>")
    fig.update_layout(height=420, yaxis_title=None, xaxis_title=None, xaxis_tickformat=".0%",
                      yaxis=dict(categoryorder="array", categoryarray=camp["campaign"].tolist()[::-1]),
                      legend=dict(orientation="h", y=-0.15, title=None), margin=dict(t=20))
    st.plotly_chart(fig, width="stretch")
    st.caption("A campaign whose dark bar is longer than its light bar earns more credit than its "
               "share of budget under the selected model. Switch models in the sidebar to see "
               "brand search and prospecting trade places.")

    st.markdown("**Attributed revenue by campaign under every model**")
    st.dataframe(camp.rename(columns={"channel": "Channel", "campaign": "Campaign", "spend": "Spend",
                                      "clicks": "Clicks"})
                 .style.format({"Spend": "${:,.0f}", "Clicks": "{:,.0f}", "Last click": "${:,.0f}",
                                "Linear": "${:,.0f}", "Time decay": "${:,.0f}",
                                "Share of spend": "{:.0%}", "Share of credit": "{:.0%}",
                                "Efficiency index": "{:.2f}"}),
                 width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Tab 3: Customer paths
# ---------------------------------------------------------------------------
with tab3:
    per_order = paths.groupby("order_id").agg(
        touches=("touch_id", "count"), channels=("channel", "nunique"),
        first=("channel", "first"), last=("channel", "last"), revenue=("revenue", "first"))
    multi = (per_order["touches"] > 1).mean()
    multi_ch = (per_order["channels"] > 1).mean()

    m1, m2, m3 = st.columns(3)
    m1.metric("Orders with 2+ ad clicks", f"{multi:.0%}")
    m2.metric("Orders touching 2+ channels", f"{multi_ch:.0%}")
    m3.metric("Average clicks per order", f"{per_order['touches'].mean():.1f}")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Ad clicks before purchase")
        counts = per_order["touches"].value_counts().sort_index().reset_index()
        counts.columns = ["Clicks in path", "Orders"]
        fig = px.bar(counts, x="Clicks in path", y="Orders", text_auto=True,
                     color_discrete_sequence=["#2a78d6"])
        fig.update_traces(hovertemplate="%{x} clicks: %{y} orders<extra></extra>")
        fig.update_layout(height=360, xaxis=dict(dtick=1), margin=dict(t=20))
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.subheader("First click vs last click channel")
        st.caption("Rows: channel that started the path. Columns: channel that closed it.")
        xt = pd.crosstab(per_order["first"], per_order["last"]).reindex(
            index=CHANNELS, columns=CHANNELS, fill_value=0)
        fig = px.imshow(xt, text_auto=True, color_continuous_scale="Blues", aspect="auto",
                        labels=dict(x="Last click", y="First click", color="Orders"))
        fig.update_traces(hovertemplate="Started on %{y}<br>Closed on %{x}<br>%{z} orders<extra></extra>")
        fig.update_layout(height=360, margin=dict(t=20))
        st.plotly_chart(fig, width="stretch")

    st.subheader("Explore a single customer path")
    order_ids = per_order.sort_values("touches", ascending=False).index.tolist()
    pick = st.selectbox("Order (sorted by number of clicks)", order_ids,
                        format_func=lambda o: f"{o} · {per_order.loc[o, 'touches']} clicks · "
                                              f"${per_order.loc[o, 'revenue']:,.2f}")
    p = credits[credits["order_id"] == pick].pivot_table(
        index=["touch_time", "channel", "campaign", "days_before"], columns="model",
        values="credit").reset_index().sort_values("touch_time")
    fig = go.Figure()
    for ch in CHANNELS:
        sub = p[p["channel"] == ch]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["touch_time"], y=[ch] * len(sub), mode="markers", name=ch,
            marker=dict(size=16, color=CHANNEL_COLORS[ch], line=dict(color="white", width=2)),
            customdata=sub[["campaign", "Last click", "Linear", "Time decay"]],
            hovertemplate="%{customdata[0]}<br>%{x|%b %d %H:%M}<br>Credit: last click "
                          "%{customdata[1]:.0%} · linear %{customdata[2]:.0%} · time decay "
                          "%{customdata[3]:.0%}<extra></extra>"))
    conv_time = cv.loc[cv["order_id"] == pick, "conversion_time"].iloc[0]
    fig.add_vline(x=conv_time, line_dash="dash", line_color="#52514e")
    fig.add_annotation(x=conv_time, y=1.05, yref="paper", text="Purchase", showarrow=False)
    fig.update_layout(height=260, yaxis=dict(categoryorder="array", categoryarray=CHANNELS[::-1]),
                      showlegend=False, margin=dict(t=30))
    st.plotly_chart(fig, width="stretch")
    st.dataframe(p.rename(columns={"touch_time": "Click time", "channel": "Channel",
                                   "campaign": "Campaign", "days_before": "Days before order"})
                 .style.format({"Days before order": "{:.1f}", "Last click": "{:.0%}",
                                "Linear": "{:.0%}", "Time decay": "{:.0%}"}),
                 width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Tab 4: Daily spend
# ---------------------------------------------------------------------------
with tab4:
    st.subheader("Daily spend by channel")
    daily = ads_f.groupby(["date", "channel"])["spend"].sum().reset_index()
    fig = px.line(daily, x="date", y="spend", color="channel", color_discrete_map=CHANNEL_COLORS,
                  markers=True)
    fig.update_traces(line_width=2, hovertemplate="%{fullData.name}: $%{y:,.0f}<extra></extra>")
    fig.update_layout(height=400, hovermode="x unified", xaxis_title=None, yaxis_title="Spend ($)",
                      legend=dict(orientation="h", y=-0.15, title=None), margin=dict(t=20))
    st.plotly_chart(fig, width="stretch")

    metric = st.radio("Daily metric", ["Clicks", "Impressions", "CPC"], horizontal=True)
    d2 = ads_f.groupby(["date", "channel"]).agg(Clicks=("clicks", "sum"),
                                                Impressions=("impressions", "sum"),
                                                spend=("spend", "sum")).reset_index()
    d2["CPC"] = d2["spend"] / d2["Clicks"]
    fig = px.line(d2, x="date", y=metric, color="channel", color_discrete_map=CHANNEL_COLORS)
    fig.update_traces(line_width=2)
    fig.update_layout(height=320, hovermode="x unified", xaxis_title=None,
                      legend=dict(orientation="h", y=-0.2, title=None), margin=dict(t=20))
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------------------
# Tab 5: Data quality
# ---------------------------------------------------------------------------
with tab5:
    st.subheader("What the cleaning step fixed")
    labels = tp.groupby("channel")["source_raw"].unique().apply(lambda s: ", ".join(sorted(s)))
    dq = pd.DataFrame([
        {"Check": "Ad performance rows (3 platforms)", "Result": f"{len(ads)} (expected 180)"},
        {"Check": "Touchpoints", "Result": f"{len(tp)} (expected 211)"},
        {"Check": "Orders", "Result": f"{len(cv)} (expected 50)"},
        {"Check": "Unparsed dates", "Result": int(ads["date"].isna().sum() + tp["touch_time"].isna().sum()
                                                  + cv["conversion_time"].isna().sum())},
        {"Check": "Unmapped click sources", "Result": int((tp["channel"] == "Other").sum())},
        {"Check": "Google cost", "Result": "Converted from micros (÷ 1,000,000)"},
        {"Check": "Meta campaign names", "Result": "Trimmed and upper-cased"},
        {"Check": "Microsoft dates", "Result": "MM/DD/YYYY parsed to dates"},
    ])
    st.dataframe(dq.astype(str), width="stretch", hide_index=True)
    st.markdown("**Raw source labels mapped to each channel**")
    st.dataframe(labels.rename("Raw labels").reset_index().rename(columns={"channel": "Channel"}),
                 width="stretch", hide_index=True)

with st.expander("About this dashboard"):
    st.markdown(f"""
- **Data:** synthetic exports built to look like real Google, Meta and Microsoft Ads data, including
  the usual problems (cost in micros, mixed date formats, one channel under several source labels).
- **Pipeline:** the same cleaning and attribution logic as the BigQuery SQL in `/sql` and the pandas
  script in `/python`, recomputed live so the lookback and half-life can be changed.
- **Caveat:** 80 users and 50 orders is enough to show the method, not to set a real budget.
  These models assign credit; they don't prove cause. That needs a holdout test.
- **Code:** [{REPO_URL}]({REPO_URL})
""")
