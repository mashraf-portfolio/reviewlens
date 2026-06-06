"""Streamlit dashboard entry-point.

TODO: build report UI that:
  - Accepts storefront / date-range inputs in the sidebar
  - Triggers the LangGraph pipeline on demand
  - Renders theme distribution charts (plotly)
  - Shows significant shifts table from QuantStats
  - Displays representative quotes per cluster
  - Shows live cost meter during pipeline runs
"""

import streamlit as st

st.set_page_config(page_title="ReviewLens", page_icon="🔍", layout="wide")
st.title("ReviewLens")
st.info("Pipeline not yet implemented. Complete Phase 1 then re-run `make run`.")
