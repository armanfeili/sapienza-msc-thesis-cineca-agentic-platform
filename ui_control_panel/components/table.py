"""
Table component with pagination, sorting, and export.
"""

import json
from typing import Any

import pandas as pd
import streamlit as st


def render_table(
    data: list[dict[str, Any]],
    columns: list[str] | None = None,
    sortable: bool = True,
    show_export: bool = True,
    key_prefix: str = "table",
):
    """
    Render an interactive table with export options.

    Args:
        data: List of dictionaries to display
        columns: Optional list of column names to display (None = all)
        sortable: Enable sorting
        show_export: Show export buttons
        key_prefix: Unique prefix for widget keys
    """
    if not data:
        st.info("No data to display")
        return

    # Convert to DataFrame
    df = pd.DataFrame(data)

    # Filter columns if specified
    if columns:
        available_cols = [c for c in columns if c in df.columns]
        if available_cols:
            df = df[available_cols]

    # Column chooser
    with st.expander("🔧 Table Options"):
        selected_cols = st.multiselect(
            "Select columns to display", options=list(df.columns), default=list(df.columns), key=f"{key_prefix}_cols"
        )

        if selected_cols:
            df = df[selected_cols]

        # Export options
        if show_export:
            col1, col2, col3 = st.columns(3)

            with col1:
                # CSV export
                csv = df.to_csv(index=False)
                st.download_button(
                    label="📥 Export CSV", data=csv, file_name="export.csv", mime="text/csv", key=f"{key_prefix}_csv"
                )

            with col2:
                # JSON export
                json_str = json.dumps(data, indent=2)
                st.download_button(
                    label="📥 Export JSON",
                    data=json_str,
                    file_name="export.json",
                    mime="application/json",
                    key=f"{key_prefix}_json",
                )

            with col3:
                # Copy to clipboard (via text area)
                if st.button("📋 Copy", key=f"{key_prefix}_copy"):
                    st.code(df.to_string(), language="text")

    # Display table
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Show row count
    st.caption(f"Showing {len(df)} rows")
