"""Shared chart style: one fixed colour per strategy, used by tools/plots.py and written into
results/summary.json (meta.strategy_colors) by tools/aggregate.py for the React dashboard.
Change a colour here and both the PNG charts and the dashboard follow.
"""
STRATEGY_COLORS = {
    "random": "#8A8F98",    # grey
    "noshare": "#1B2A4A",   # navy
    "global": "#C0392B",    # red
    "sharded": "#E0A030",   # amber
    "rwlock": "#0E8A8A",    # teal
    "snapshot": "#7D3C98",  # purple
}
