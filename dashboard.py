#!/usr/bin/env python3
"""
Builder's Black Book - Complete Dashboard
Full version with Supabase integration for pending submissions
"""

import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from supabase import create_client, Client

# ================== PATHS ==================
DB_PATH = Path(__file__).parent / "permits.db"
ASSETS_PATH = Path("assets")
SUBS_CSV = Path("data/subcontractors.csv")

st.set_page_config(page_title="Builder's Black Book", layout="wide")

# ================== SUPABASE CONNECTION ==================
def get_supabase_client() -> Client:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        return None

# ================== HEADER ==================
st.title("Builder's Black Book")
st.caption("Nashville Residential Permit Intelligence")

st.markdown("---")
# Load permit data from local SQLite
@st.cache_data
def load_permit_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM permits", conn)
    conn.close()
    df["date_issued"] = pd.to_datetime(df["date_issued"], errors="coerce")
    return df

df = load_permit_data()

# ================== TABS ==================
tab1, tab2, tab3 = st.tabs(["📊 Overview", "👷 Contractors", "🔧 Sub-Contractors"])

# ================== TAB 1: OVERVIEW ==================
with tab1:
    st.sidebar.header("Filters")

    min_date = df["date_issued"].min()
    max_date = df["date_issued"].max()
    date_range = st.sidebar.date_input("Date Issued Range", value=(min_date, max_date))

    zip_codes = ["All"] + sorted(df["zip_code"].dropna().unique().tolist())
    selected_zip = st.sidebar.selectbox("ZIP Code", zip_codes)

    permit_types = ["All"] + sorted(df["permit_type"].dropna().unique().tolist())
    selected_type = st.sidebar.selectbox("Permit Type", permit_types)

    search_term = st.sidebar.text_input("Search Address or Contractor")

    # Apply filters
    filtered = df.copy()

    if len(date_range) == 2:
        filtered = filtered[
            (filtered["date_issued"] >= pd.to_datetime(date_range[0])) &
            (filtered["date_issued"] <= pd.to_datetime(date_range[1]))
        ]

    if selected_zip != "All":
        filtered = filtered[filtered["zip_code"] == selected_zip]

    if selected_type != "All":
        filtered = filtered[filtered["permit_type"] == selected_type]
    else:
        residential_mask = filtered["permit_type"].str.contains("residential", case=False, na=False)
        filtered = filtered[residential_mask]

    if search_term:
        mask = (
            filtered["address"].str.contains(search_term, case=False, na=False) |
            filtered["contractor"].str.contains(search_term, case=False, na=False)
        )
        filtered = filtered[mask]

    # Summary Metrics
    col1, col2 = st.columns(2)
    col1.metric("Total Permits", len(filtered))
    col2.metric("Total Value", f"${filtered['construction_cost'].sum():,.0f}")

    # Last 90 Days Snapshot
    st.subheader("🔥 Last 90 Days Snapshot")
    ninety_days_ago = datetime.now() - timedelta(days=90)
    recent_df = filtered[filtered["date_issued"] >= ninety_days_ago]

    c1, c2 = st.columns(2)
    c1.metric("Recent Permits", len(recent_df))
    c2.metric("Recent Value", f"${recent_df['construction_cost'].sum():,.0f}")

    # Hot ZIP Codes
    st.subheader("🔥 Hot ZIP Codes")
    st.caption("ZIP codes with the most residential permit activity in the last 90 days")

    if not recent_df.empty:
        hot_zips = (
            recent_df.groupby("zip_code")
            .agg(permits=("permit_id", "count"), total_value=("construction_cost", "sum"))
            .reset_index()
            .sort_values("permits", ascending=False)
            .head(6)
        )
        st.dataframe(
            hot_zips,
            width='stretch',
            hide_index=True,
            column_config={
                "total_value": st.column_config.NumberColumn("Total Value", format="$%,.0f"),
            }
        )
    else:
        st.info("No recent residential activity found.")

    st.divider()

    # Recent Movers at a Glance
    st.subheader("Recent Movers at a Glance")
    st.caption("High-value residential permits (>$150k) issued in the last 90 days")

    high_value = recent_df[recent_df["construction_cost"] >= 150000].head(15)

    if not high_value.empty:
        quick_cols = ["date_issued", "permit_type", "address", "zip_code", "construction_cost", "contractor"]
        st.dataframe(
            high_value[quick_cols].sort_values("construction_cost", ascending=False),
            width='stretch',
            hide_index=True,
            column_config={
                "construction_cost": st.column_config.NumberColumn("Value", format="$%,.0f"),
                "date_issued": st.column_config.DatetimeColumn("Date", format="YYYY-MM-DD"),
            }
        )
    else:
        st.info("No high-value recent residential permits found.")

    st.divider()

    # Main Table
    st.subheader("All Residential Permits")

    show_recent_only = st.toggle("Show only permits from the last 90 days", value=True)

    if show_recent_only:
        table_df = recent_df.copy()
        st.caption(f"Showing {len(table_df):,} residential permits from the last 90 days")
    else:
        table_df = filtered.copy()
        st.caption(f"Showing all {len(table_df):,} residential permits")

    display_cols = ["permit_id", "permit_type", "address", "zip_code", 
                    "construction_cost", "date_issued", "contractor"]

    st.dataframe(
        table_df[display_cols].sort_values("date_issued", ascending=False),
        width='stretch',
        hide_index=True,
        column_config={
            "construction_cost": st.column_config.NumberColumn("Value", format="$%,.0f"),
            "date_issued": st.column_config.DatetimeColumn("Date Issued", format="YYYY-MM-DD"),
        }
    )

    if st.button("Export Current View to CSV"):
        csv = table_df.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", csv, "permits_export.csv", "text/csv")

# ================== TAB 2: CONTRACTORS ==================
with tab2:
    st.subheader("👷 Contractor Directory")
    st.caption("Active General Contractors / Builders in Nashville")

    ninety_days_ago = datetime.now() - timedelta(days=90)
    recent_contractors = df[df["date_issued"] >= ninety_days_ago]

    st.markdown("**Top Active Contractors (Last 90 Days)**")

    if not recent_contractors.empty:
        top_contractors = (
            recent_contractors.groupby("contractor")
            .agg(
                permits=("permit_id", "count"),
                total_value=("construction_cost", "sum"),
                most_recent=("date_issued", "max")
            )
            .reset_index()
            .sort_values("total_value", ascending=False)
            .head(8)
        )

        st.dataframe(
            top_contractors,
            width='stretch',
            hide_index=True,
            column_config={
                "total_value": st.column_config.NumberColumn("Total Value", format="$%,.0f"),
                "most_recent": st.column_config.DatetimeColumn("Most Recent Permit", format="YYYY-MM-DD"),
            }
        )
    else:
        st.info("No recent contractor activity found.")

    st.divider()

    st.subheader("All Active Contractors")

    contractor_summary = (
        recent_contractors.groupby("contractor")
        .agg(
            total_permits=("permit_id", "count"),
            total_value=("construction_cost", "sum"),
            most_recent_permit=("date_issued", "max"),
            primary_zip=("zip_code", lambda x: x.mode()[0] if len(x.mode()) > 0 else "N/A")
        )
        .reset_index()
        .sort_values("total_value", ascending=False)
    )

    search = st.text_input("🔍 Search Contractors", placeholder="Search by name...")

    if search:
        contractor_summary = contractor_summary[
            contractor_summary.astype(str).apply(
                lambda x: x.str.contains(search, case=False, na=False)
            ).any(axis=1)
        ]

    st.dataframe(
        contractor_summary,
        width='stretch',
        hide_index=True,
        column_config={
            "total_value": st.column_config.NumberColumn("Total Value", format="$%,.0f"),
            "most_recent_permit": st.column_config.DatetimeColumn("Most Recent Permit", format="YYYY-MM-DD"),
        }
    )

    if st.button("Export Contractor Directory"):
        csv = contractor_summary.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", csv, "contractor_directory.csv", "text/csv")

# ================== TAB 3: SUB-CONTRACTORS ==================
with tab3:
    st.subheader("🔧 Approved Subcontractors")
    st.caption("Curated list of quality subcontractors in the Nashville area")

    # Load approved subcontractors from Supabase
    @st.cache_data(ttl=60)
    def load_approved_subs():
        try:
            supabase = get_supabase_client()
            if supabase is None:
                return pd.DataFrame()
            response = supabase.table("approved_subcontractors").select("*").order("approved_at", desc=True).execute()
            return pd.DataFrame(response.data)
        except Exception as e:
            st.error(f"Could not load approved subcontractors: {e}")
            return pd.DataFrame()

    approved_df = load_approved_subs()

    if approved_df.empty:
        st.info("No approved subcontractors yet.")
    else:
        # Simple search
        search = st.text_input("🔍 Search", placeholder="Search by company or trade...")

        display_df = approved_df.copy()
        if search:
            display_df = display_df[
                display_df.astype(str).apply(
                    lambda x: x.str.contains(search, case=False, na=False)
                ).any(axis=1)
            ]

        # Choose which columns to show publicly
        public_cols = ["company_name", "primary_trade", "areas_served", "phone", "email", "website"]
        available_cols = [c for c in public_cols if c in display_df.columns]

        st.dataframe(
            display_df[available_cols],
            use_container_width=True,
            hide_index=True
        )

        st.caption(f"Showing {len(display_df)} approved subcontractors")
