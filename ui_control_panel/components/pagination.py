"""
Pagination component for lists and tables.
"""

import math

import streamlit as st


def render_pagination(
    total_items: int, items_per_page: int = 20, current_page: int = 1, key_prefix: str = "pagination"
) -> int:
    """
    Render pagination controls and return the selected page number.

    Args:
        total_items: Total number of items across all pages
        items_per_page: Number of items to show per page
        current_page: Current page number (1-indexed)
        key_prefix: Unique prefix for Streamlit keys

    Returns:
        Selected page number (1-indexed)
    """
    total_pages = max(1, math.ceil(total_items / items_per_page))

    # Ensure current_page is within bounds
    current_page = max(1, min(current_page, total_pages))

    if total_pages <= 1:
        # No pagination needed
        return 1

    # Create pagination controls
    col1, col2, col3, col4, col5 = st.columns([1, 1, 3, 1, 1])

    with col1:
        # First page button
        if st.button("⏮️ First", key=f"{key_prefix}_first", disabled=current_page == 1):
            return 1

    with col2:
        # Previous page button
        if st.button("◀️ Prev", key=f"{key_prefix}_prev", disabled=current_page == 1):
            return current_page - 1

    with col3:
        # Page selector
        st.markdown(
            f"<div style='text-align: center; padding-top: 8px;'>"
            f"Page <strong>{current_page}</strong> of <strong>{total_pages}</strong> "
            f"({total_items} items)"
            f"</div>",
            unsafe_allow_html=True,
        )

    with col4:
        # Next page button
        if st.button("Next ▶️", key=f"{key_prefix}_next", disabled=current_page >= total_pages):
            return current_page + 1

    with col5:
        # Last page button
        if st.button("Last ⏭️", key=f"{key_prefix}_last", disabled=current_page >= total_pages):
            return total_pages

    # Page jump (optional, in expander)
    with st.expander("🔢 Jump to Page"):
        page_input = st.number_input(
            "Enter page number", min_value=1, max_value=total_pages, value=current_page, key=f"{key_prefix}_jump"
        )
        if st.button("Go", key=f"{key_prefix}_go"):
            return page_input

    return current_page


def render_compact_pagination(
    total_items: int, items_per_page: int = 20, current_page: int = 1, key_prefix: str = "pagination"
) -> tuple[int, int]:
    """
    Render compact pagination with page size selector.

    Args:
        total_items: Total number of items
        items_per_page: Default items per page
        current_page: Current page number
        key_prefix: Unique prefix for keys

    Returns:
        Tuple of (selected_page, items_per_page)
    """
    col1, col2, col3 = st.columns([2, 1, 2])

    with col1:
        # Items per page selector
        page_size = st.selectbox(
            "Items per page",
            options=[10, 20, 50, 100],
            index=[10, 20, 50, 100].index(items_per_page) if items_per_page in [10, 20, 50, 100] else 1,
            key=f"{key_prefix}_size",
        )

    with col2:
        st.markdown("<div style='padding-top: 30px;'></div>", unsafe_allow_html=True)

    with col3:
        # Page navigation
        total_pages = max(1, math.ceil(total_items / page_size))
        current_page = max(1, min(current_page, total_pages))

        page_num = st.number_input(
            f"Page (1-{total_pages})", min_value=1, max_value=total_pages, value=current_page, key=f"{key_prefix}_page"
        )

    # Navigation buttons
    col1, col2, col3, col4 = st.columns(4)

    page_to_return = page_num

    with col1:
        if st.button("⏮️", key=f"{key_prefix}_first_compact", disabled=page_num == 1):
            page_to_return = 1

    with col2:
        if st.button("◀️", key=f"{key_prefix}_prev_compact", disabled=page_num == 1):
            page_to_return = page_num - 1

    with col3:
        if st.button("▶️", key=f"{key_prefix}_next_compact", disabled=page_num >= total_pages):
            page_to_return = page_num + 1

    with col4:
        if st.button("⏭️", key=f"{key_prefix}_last_compact", disabled=page_num >= total_pages):
            page_to_return = total_pages

    return page_to_return, page_size


def get_page_slice(items: list, page: int, items_per_page: int) -> list:
    """
    Get a slice of items for the current page.

    Args:
        items: Full list of items
        page: Current page number (1-indexed)
        items_per_page: Number of items per page

    Returns:
        Sliced list for the current page
    """
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    return items[start_idx:end_idx]
