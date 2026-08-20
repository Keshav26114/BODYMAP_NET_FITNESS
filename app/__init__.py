"""
app/ — the Flask web application package.

app.py       Flask routes (auth, test submission, results, history, settings).
inference.py Loads the trained checkpoints and runs predictions for the web app.
charts.py    Renders server-side Matplotlib charts as base64 PNGs.
insights.py  Turns raw results into plain-English tips and the goal-verdict banner.
outcomes.py  Single source of truth for "is this result good or bad for this goal?" —
             shared by insights.py and streaks.py so they never disagree.
streaks.py   Computes consecutive-week positive/negative streaks from test history.
"""
