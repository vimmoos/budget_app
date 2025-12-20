import plotly.graph_objects as go
import pandas as pd


def create_sankey(df_merged):
    # df_merged expected cols: 'amount', 'group', 'category_name', 'type'
    if df_merged.empty:
        return go.Figure()

    expenses = df_merged[df_merged["type"] == "Expense"].copy()

    if expenses.empty:
        return go.Figure()

    # Aggregations
    # L1: Total Spend -> Groups
    l1 = expenses.groupby("group")["amount"].sum().reset_index()
    l1["source"] = "Total Spend"
    l1.rename(columns={"group": "target"}, inplace=True)

    # L2: Groups -> Categories
    l2 = expenses.groupby(["group", "category_name"])["amount"].sum().reset_index()
    l2.rename(columns={"group": "source", "category_name": "target"}, inplace=True)

    links = pd.concat([l1, l2], axis=0)

    # Create nodes
    all_nodes = list(pd.concat([links["source"], links["target"]]).unique())
    node_map = {name: i for i, name in enumerate(all_nodes)}

    fig = go.Figure(
        data=[
            go.Sankey(
                node=dict(
                    pad=15,
                    thickness=20,
                    line=dict(color="black", width=0.5),
                    label=all_nodes,
                ),
                link=dict(
                    source=links["source"].map(node_map),
                    target=links["target"].map(node_map),
                    value=links["amount"],
                ),
            )
        ]
    )

    fig.update_layout(title_text="Cash Flow Visualization", font_size=12, height=500)
    return fig


def create_bullet_chart(category, actual, budget):
    # Avoid division by zero or weird ranges
    max_range = max(budget * 1.2, actual * 1.1) if (budget > 0 or actual > 0) else 100

    fig = go.Figure(
        go.Indicator(
            mode="number+gauge+delta",
            value=actual,
            delta={
                "reference": budget,
                # Invert colors: Increasing (Over budget) is RED, Decreasing (Under budget) is GREEN
                "increasing": {"color": "#FF4B4B"},  # Streamlit Red
                "decreasing": {"color": "#09AB3B"},  # Streamlit Green
            },
            domain={"x": [0, 1], "y": [0, 1]},
            gauge={
                "shape": "bullet",
                "axis": {"range": [None, max_range]},
                "threshold": {
                    "line": {"color": "red", "width": 2},
                    "thickness": 0.75,
                    "value": budget,
                },
                "bar": {"color": "#1f77b4"},  # Standard Blue
            },
        )
    )

    # Title is part of the layout to avoid clipping
    fig.update_layout(
        title={"text": category},
        height=250,
        margin={"t": 50, "b": 20, "l": 30, "r": 30},
    )
    return fig
