"""Verbruik van de AI: hoeveel tekst, foto's en iconen er gemaakt zijn, waarvoor, en wat dat ongeveer kost."""

from datetime import date, timedelta

KEEP_DAYS = 120
KINDS = ("foto", "icoon", "tekst")


class UsageMixin:
    def log_ai_usage(self, entry):
        """Bewaar één verzoek: {kind, purpose, auto, provider, model, free, cost}."""
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO ai_usage (kind, purpose, auto, provider, model, free, cost)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (entry["kind"], str(entry.get("purpose") or "")[:80], int(bool(entry.get("auto"))),
                 str(entry.get("provider") or "")[:20], str(entry.get("model") or "")[:60],
                 int(bool(entry.get("free"))), entry.get("cost")),
            )
            conn.execute("DELETE FROM ai_usage WHERE created_at < datetime('now', ?)", (f"-{KEEP_DAYS} days",))

    def ai_usage_report(self, days=30, today=None):
        """Per dag (de nieuwste eerst) en per doel wat er de laatste `days` dagen gemaakt is, met totalen."""
        today = today or date.today()
        start = (today - timedelta(days=days - 1)).isoformat()
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT date(created_at, 'localtime') AS day, kind, purpose, auto, free, COUNT(*) AS n,
                          SUM(COALESCE(cost, 0)) AS cost
                   FROM ai_usage WHERE date(created_at, 'localtime') >= ?
                   GROUP BY day, kind, purpose, auto, free""",
                (start,),
            ).fetchall()
        per_day, purposes = {}, {}
        totals = {kind: 0 for kind in KINDS} | {"cost": 0.0, "auto": 0, "free_text": 0}
        for r in rows:
            day = per_day.setdefault(r["day"], {"date": r["day"], **{k: 0 for k in KINDS}, "auto": 0, "cost": 0.0})
            day[r["kind"]] += r["n"]
            day["cost"] += r["cost"]
            day["auto"] += r["n"] if r["auto"] else 0
            key = (r["kind"], r["purpose"], bool(r["auto"]))
            purpose = purposes.setdefault(key, {"kind": r["kind"], "purpose": r["purpose"], "auto": bool(r["auto"]),
                                               "count": 0, "free": 0, "cost": 0.0})
            purpose["count"] += r["n"]
            purpose["free"] += r["n"] if r["free"] else 0
            purpose["cost"] += r["cost"]
            totals[r["kind"]] += r["n"]
            totals["cost"] += r["cost"]
            totals["auto"] += r["n"] if r["auto"] else 0
            totals["free_text"] += r["n"] if r["free"] and r["kind"] == "tekst" else 0
        return {
            "days": days,
            "per_day": sorted(per_day.values(), key=lambda d: d["date"], reverse=True),
            "purposes": sorted(purposes.values(), key=lambda p: (-p["cost"], -p["count"])),
            "totals": totals,
        }
