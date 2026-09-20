"""APIx Real-Time Airfare Price Index Dashboard."""
import os
import requests
import pandas as pd
import streamlit as st

# Configure Streamlit Page
st.set_page_config(
    page_title="APIx Airfare Price Index",
    page_icon="✈️",
    layout="wide",
)

# API URL Base
API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")


@st.cache_data(ttl=10)
def fetch_api_data(endpoint: str):
    """Fetches data from FastAPI backend with error handling."""
    url = f"{API_URL}{endpoint}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
        st.error(f"API Error ({response.status_code}): {response.text}")
        return None
    except Exception as e:
        st.warning(f"Could not connect to API server at {url}: {e}")
        return None


def render_national_overview():
    st.title("✈️ APIx Real-Time Airfare Price Index")
    st.caption("Page 1 — National Overview")

    # Fetch Latest Index Level
    index_res = fetch_api_data("/api/index")

    col1, col2, col3, col4 = st.columns(4)

    if index_res:
        current_level = index_res.get("level", 100.0)
        base_level = index_res.get("base_fare_level", 100.0)
        change_pct = index_res.get("change_pct", 0.0)
        meta = index_res.get("metadata", {})

        col1.metric(
            label="National APIx Level",
            value=f"{current_level:.2f}",
            delta=f"{change_pct:+.2f}% vs prev",
        )
        col2.metric(
            label="Base Fare Index Level",
            value=f"{base_level:.2f}",
        )
        col3.metric(
            label="Active Cells (n_cells)",
            value=meta.get("n_cells", 0),
        )
        col4.metric(
            label="Provenance Label",
            value=meta.get("label", "estimated").capitalize(),
        )
    else:
        col1.metric("National APIx Level", "100.00", "0.00%")
        col2.metric("Base Fare Index Level", "100.00")
        col3.metric("Active Cells", "0")
        col4.metric("Provenance Label", "Estimated")

    st.markdown("---")

    # Section 1: Daily Trend Line Chart
    st.subheader("📈 Daily APIx Trend Series")
    daily_res = fetch_api_data("/api/index/daily")

    if daily_res and daily_res.get("data"):
        df_daily = pd.DataFrame(daily_res["data"])
        if not df_daily.empty and "date" in df_daily.columns:
            df_daily["date"] = pd.to_datetime(df_daily["date"])
            df_daily = df_daily.sort_values("date")

            chart_data = df_daily.set_index("date")[["level", "base_fare_level"]]
            chart_data.columns = ["Total Fare APIx", "Base Fare APIx"]

            st.line_chart(chart_data)

            # CSV Download Button
            csv_url = f"{API_URL}/api/index/daily?format=csv"
            st.markdown(f"📥 [Download Daily Series CSV]({csv_url})")
        else:
            st.info("No daily series records found yet. Run the scraper pipeline to populate data.")
    else:
        st.info("Daily APIx trend data currently empty. Run daily scraper pipeline.")

    st.markdown("---")

    # Section 2: Flagged Surges & Anomalies List
    st.subheader("🚨 Flagged Price Surges & Anomalies")
    anomalies_res = fetch_api_data("/api/anomalies")

    if anomalies_res and anomalies_res.get("anomalies"):
        anom_list = anomalies_res["anomalies"]
        df_anom = pd.DataFrame(anom_list)
        if not df_anom.empty:
            df_anom = df_anom.rename(
                columns={
                    "route_id": "Route",
                    "date": "Date",
                    "lead_days": "Lead Window",
                    "score": "Robust Z-Score",
                    "pct_from_expected": "% vs Expected Median",
                    "direction": "Surge / Drop",
                }
            )
            st.warning(f"Detected {len(df_anom)} flagged fare surges/drops (Robust Z-Score > 3.5)")
            st.dataframe(df_anom, use_container_width=True, hide_index=True)
        else:
            st.success("No active price surges flagged for current period.")
    else:
        st.success("No active price surges or anomalies detected.")

    st.markdown("---")

    # Section 3: Underlying Route Indices Table with Volatility Band
    st.subheader("🗺️ Underlying Route Indices & Volatility Bands")
    routes_res = fetch_api_data("/api/routes")

    if routes_res and routes_res.get("routes"):
        df_routes = pd.DataFrame(routes_res["routes"])
        if not df_routes.empty:
            df_routes = df_routes.rename(
                columns={
                    "route_id": "Route",
                    "origin": "Origin",
                    "destination": "Destination",
                    "weight": "DGCA Weight",
                    "dgca_pax": "DGCA Monthly Pax Volume",
                    "latest_level": "Current Route Index Level",
                    "volatility_band": "Volatility Band (Tercile)",
                }
            )
            st.dataframe(
                df_routes,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No route indices available.")
    else:
        st.info("Route indices currently empty.")


def render_why_prices_moved():
    st.title("🔍 Explainability — Why Did Prices Move?")
    st.caption("Page 4 — Measurable Attribution & Coincident Signal Panel")

    attr_res = fetch_api_data("/api/attribution")

    if attr_res and attr_res.get("level1_decomposition"):
        decomp = attr_res["level1_decomposition"]
        st.subheader("1️⃣ Level 1 Additive Price Movement Decomposition")
        st.caption("Decomposes APIx change with an explicit, un-fudged residual component.")

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Total Change", f"{decomp.get('total_change', 0.0):+.4f}")
        c2.metric("Route Mix", f"{decomp.get('route_mix_contribution', 0.0):+.4f}")
        c3.metric("Carrier Mix", f"{decomp.get('carrier_mix_contribution', 0.0):+.4f}")
        c4.metric("Lead Time Mix", f"{decomp.get('lead_time_mix_contribution', 0.0):+.4f}")
        c5.metric("Base vs Tax/Fee", f"{decomp.get('base_vs_taxes_contribution', 0.0):+.4f}")
        c6.metric("Unexplained Residual", f"{decomp.get('residual', 0.0):+.4f}", help="Explicit residual: Total Change - Explained Sum")

        st.markdown("---")

        st.subheader("2️⃣ Level 2 Coincident Event & Macro Signals")
        signals = attr_res.get("level2_signals", [])
        if signals:
            df_sig = pd.DataFrame(signals)
            st.dataframe(df_sig, use_container_width=True, hide_index=True)
        else:
            st.info("No coincident signals recorded for this period.")

        st.markdown("---")

        st.subheader("3️⃣ Level 3 Causal Regression (Sample-Size Gated)")
        reg_info = attr_res.get("level3_causal_regression", {})
        if reg_info.get("sample_size_sufficient"):
            st.success(reg_info.get("message"))
            coefs = reg_info.get("coefficients", [])
            if coefs:
                st.dataframe(pd.DataFrame(coefs), use_container_width=True, hide_index=True)
        else:
            st.warning(f"⚠️ {reg_info.get('message', 'Sample size below threshold N >= 30 for causal percentage claims.')}")


def render_forecast():
    st.title("🔮 APIx Forecast & Baseline Comparison Engine")
    st.caption("Page 5 — Walk-Forward Model Forecast with Interval Bounds & Baseline Evaluation")

    selected_route = st.selectbox(
        "Forecast Subject Filter:",
        ["National APIx", "DEL-BOM", "DEL-BLR", "BOM-BLR", "DEL-CCU", "BLR-HYD", "MAA-DEL"],
    )
    route_param = None if selected_route == "National APIx" else selected_route
    horizon = st.slider("Forecast Horizon (Days):", min_value=1, max_value=30, value=7)

    endpoint = f"/api/forecast?horizon={horizon}"
    if route_param:
        endpoint += f"&route={route_param}"

    fc_res = fetch_api_data(endpoint)

    if fc_res and fc_res.get("forecast_points"):
        chosen_model = fc_res.get("chosen_model", "")
        beats_baselines = fc_res.get("beats_baselines", False)

        if beats_baselines:
            st.success(f"✅ Model **{chosen_model}** beat both Naive and Seasonal-Naive baselines during walk-forward evaluation.")
        else:
            st.warning(f"⚠️ Model fell short of baselines on held-out data. Surfacing fallback: **{chosen_model}**.")

        # Metrics comparison table
        metrics = fc_res.get("evaluation_metrics", {})
        st.subheader("📊 Walk-Forward Evaluation Metrics (Model vs Baselines)")
        df_metrics = pd.DataFrame(
            [
                {"Model / Baseline": "Gradient Boosting (Cell Model)", "MAE": metrics.get("model", {}).get("mae"), "MAPE (%)": metrics.get("model", {}).get("mape")},
                {"Model / Baseline": "Last Value (Naive)", "MAE": metrics.get("last_value", {}).get("mae"), "MAPE (%)": metrics.get("last_value", {}).get("mape")},
                {"Model / Baseline": "Seasonal Naive (7-Day)", "MAE": metrics.get("seasonal_naive", {}).get("mae"), "MAPE (%)": metrics.get("seasonal_naive", {}).get("mape")},
            ]
        )
        st.dataframe(df_metrics, use_container_width=True, hide_index=True)

        st.markdown("---")

        st.subheader("📈 Point Forecast & 95% Interval Spread Bounds")
        points = fc_res.get("forecast_points", [])
        df_pts = pd.DataFrame(points)
        st.dataframe(df_pts[["target_date", "level", "lower", "upper", "model"]], use_container_width=True, hide_index=True)

        # Plot Forecast Chart
        if not df_pts.empty:
            chart_df = df_pts.set_index("target_date")[["level", "lower", "upper"]]
            chart_df.columns = ["Point Forecast", "Lower Bound (95%)", "Upper Bound (95%)"]
            st.line_chart(chart_df)
    else:
        st.info("Forecast data unavailable.")


def render_data_quality():
    st.title("🛡️ APIx Data Quality & Coverage Monitor")
    st.caption("Page 7 — Data Quality Dashboard")

    quality_res = fetch_api_data("/api/quality")

    col1, col2, col3, col4 = st.columns(4)

    if quality_res:
        col1.metric("Total Clean Quotes Ingested", f"{quality_res.get('total_quotes', 0):,}")
        col2.metric("Active Cells", quality_res.get("active_cells", 0))
        col3.metric("Missing / Dropped Cells", quality_res.get("missing_cells", 0))
        col4.metric("MAD Outliers Flagged", quality_res.get("outliers_count", 0))

        st.markdown("---")

        st.subheader("📊 Scraping Coverage & Status Breakdown by Source")
        sources_list = quality_res.get("sources", [])
        if sources_list:
            df_sources = pd.DataFrame(sources_list)
            df_sources = df_sources.rename(
                columns={
                    "source": "Carrier / Source Code",
                    "total_quotes": "Total Scraped Quotes",
                    "available_quotes": "Available Flights",
                    "sold_out_quotes": "Sold Out / Cancelled",
                    "outliers_count": "Outliers Flagged",
                    "coverage_pct": "Availability %",
                }
            )
            st.dataframe(df_sources, use_container_width=True, hide_index=True)
        else:
            st.info("No source quality metrics available yet. Execute scraper run.")
    else:
        st.info("Data quality metrics unavailable.")


def main():
    st.sidebar.title("APIx Dashboard")
    page = st.sidebar.radio(
        "Select View Page:",
        ["1. National Overview", "4. Why did prices move?", "5. Forecast", "7. Data Quality"],
    )

    api_status_url = f"{API_URL}/docs"
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"[📖 OpenAPI API Documentation]({api_status_url})")

    if page == "1. National Overview":
        render_national_overview()
    elif page == "4. Why did prices move?":
        render_why_prices_moved()
    elif page == "5. Forecast":
        render_forecast()
    elif page == "7. Data Quality":
        render_data_quality()


if __name__ == "__main__":
    main()
