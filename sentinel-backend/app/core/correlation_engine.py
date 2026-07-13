from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import networkx as nx
from rapidfuzz import fuzz, process
from loguru import logger
from app.config import settings


class CorrelationEngine:
    """
    Core engine that stitches transaction IDs across 4 source systems
    (Oracle Core Banking, RAAST, Wallet APIs, Settlement Files)
    into unified Payment Lifecycle Objects.
    
    Matching criteria:
    - Amount within ±CORRELATION_AMOUNT_TOLERANCE_PKR
    - Timestamp within ±CORRELATION_TIME_TOLERANCE_SECONDS
    - Account number fuzzy match >= CORRELATION_FUZZY_THRESHOLD
    """

    def __init__(self):
        self.time_tolerance = timedelta(
            seconds=settings.correlation_time_tolerance_seconds
        )
        self.amount_tolerance = Decimal(str(settings.correlation_amount_tolerance_pkr))
        self.fuzzy_threshold = settings.correlation_fuzzy_threshold

    def correlate(self, transactions: List[Dict]) -> List[Dict]:
        """
        Main correlation method.
        Takes list of raw transaction dicts, returns correlated groups.
        
        Each transaction dict expected to have:
        {
            "id": str,
            "source_system": str,  # oracle|raast|wallet|settlement
            "source_transaction_id": str,
            "amount": Decimal,
            "currency": str,
            "account_from": str,
            "account_to": str,
            "transaction_timestamp": datetime,
            "status": str,
            "raw_data": dict
        }
        """
        logger.info(f"Starting correlation for {len(transactions)} transactions")

        correlated_groups = []
        unmatched = list(transactions)
        processed_ids = set()

        for anchor in transactions:
            if anchor["id"] in processed_ids:
                continue

            group = [anchor]
            processed_ids.add(anchor["id"])

            # Find matches for this anchor
            candidates = [
                t for t in unmatched
                if t["id"] not in processed_ids
                and t["source_system"] != anchor["source_system"]
            ]

            for candidate in candidates:
                if self._is_match(anchor, candidate):
                    group.append(candidate)
                    processed_ids.add(candidate["id"])

            if len(group) > 0:
                lifecycle = self._build_lifecycle(group)
                correlated_groups.append(lifecycle)

        logger.info(f"Correlation complete: {len(correlated_groups)} payment lifecycles built")
        return correlated_groups

    def _is_match(self, t1: Dict, t2: Dict) -> bool:
        """Check if two transactions belong to the same payment lifecycle."""

        # Amount match (within tolerance)
        try:
            amount1 = Decimal(str(t1["amount"]))
            amount2 = Decimal(str(t2["amount"]))
            if abs(amount1 - amount2) > self.amount_tolerance:
                return False
        except Exception:
            return False

        # Timestamp match (within tolerance)
        try:
            ts1 = t1["transaction_timestamp"]
            ts2 = t2["transaction_timestamp"]
            if isinstance(ts1, str):
                ts1 = datetime.fromisoformat(ts1)
            if isinstance(ts2, str):
                ts2 = datetime.fromisoformat(ts2)
            if abs(ts1 - ts2) > self.time_tolerance:
                return False
        except Exception:
            return False

        # Account fuzzy match (if available)
        account_match = False
        for field in ["account_from", "account_to"]:
            a1 = t1.get(field, "") or ""
            a2 = t2.get(field, "") or ""
            if a1 and a2:
                score = fuzz.ratio(a1, a2)
                if score >= self.fuzzy_threshold:
                    account_match = True
                    break

        # If no account fields available, rely on amount + timestamp only
        if not (t1.get("account_from") or t1.get("account_to")):
            account_match = True

        return account_match

    def _build_lifecycle(self, group: List[Dict]) -> Dict:
        """Build a Payment Lifecycle Object from correlated transactions."""

        # Sort by timestamp
        sorted_group = sorted(
            group,
            key=lambda x: x.get("transaction_timestamp", datetime.min)
            if isinstance(x.get("transaction_timestamp"), datetime)
            else datetime.min
        )

        # Build identifier map
        identifier_map = {}
        for t in group:
            src = t["source_system"]
            identifier_map[src] = t["source_transaction_id"]

        # Calculate confidence score
        confidence = self._calculate_confidence(group)

        # Build networkx graph
        G = nx.DiGraph()

        # Add nodes
        for t in sorted_group:
            G.add_node(
                t["source_transaction_id"],
                source_system=t["source_system"],
                timestamp=str(t.get("transaction_timestamp", "")),
                status=t.get("status", "unknown"),
                amount=str(t.get("amount", 0)),
            )

        # Add edges (timeline connections)
        for i in range(len(sorted_group) - 1):
            src = sorted_group[i]["source_transaction_id"]
            dst = sorted_group[i + 1]["source_transaction_id"]
            G.add_edge(src, dst, relationship="follows")

        # Serialize graph for storage
        graph_data = {
            "nodes": [
                {"id": n, **G.nodes[n]}
                for n in G.nodes()
            ],
            "edges": [
                {"source": u, "target": v, **G.edges[u, v]}
                for u, v in G.edges()
            ],
        }

        # Build timeline events
        timeline_events = []
        for t in sorted_group:
            timeline_events.append({
                "timestamp": str(t.get("transaction_timestamp", "")),
                "source_system": t["source_system"],
                "transaction_id": t["source_transaction_id"],
                "status": t.get("status", "unknown"),
                "event": self._infer_event(t),
            })

        # Detect anomalies
        anomalies = self._detect_anomalies(sorted_group)

        # Determine canonical status
        canonical_status = self._determine_status(group)

        return {
            "canonical_id": f"PLO-{str(uuid.uuid4())[:8].upper()}",
            "amount": sorted_group[0].get("amount") if sorted_group else 0,
            "currency": sorted_group[0].get("currency", "PKR") if sorted_group else "PKR",
            "account_from": sorted_group[0].get("account_from") if sorted_group else None,
            "account_to": sorted_group[0].get("account_to") if sorted_group else None,
            "initiated_at": str(sorted_group[0].get("transaction_timestamp", "")),
            "status": canonical_status,
            "identifier_map": identifier_map,
            "lifecycle_graph": graph_data,
            "timeline_events": timeline_events,
            "correlation_confidence": confidence,
            "source_count": len(group),
            "anomalies": anomalies,
            "source_transactions": [t["id"] for t in group],
        }

    def _calculate_confidence(self, group: List[Dict]) -> float:
        """Calculate correlation confidence score (0-100)."""
        score = 50.0

        # More sources = higher confidence
        source_count = len(set(t["source_system"] for t in group))
        score += source_count * 10

        # All amounts exactly equal = higher confidence
        amounts = [Decimal(str(t.get("amount", 0))) for t in group]
        if len(set(amounts)) == 1:
            score += 15

        # Account fields match = higher confidence
        accounts = [t.get("account_from") for t in group if t.get("account_from")]
        if len(accounts) > 1 and len(set(accounts)) == 1:
            score += 15

        return min(100.0, score)

    def _infer_event(self, transaction: Dict) -> str:
        """Infer human-readable event description."""
        source = transaction.get("source_system", "")
        status = transaction.get("status", "").lower()

        events = {
            "core_banking": "Created in Core Banking (Oracle)",
            "raast": "Submitted to RAAST Gateway",
            "wallet": "Wallet API processed",
            "settlement": "Settlement file matched",
        }
        base = events.get(source, f"Processed by {source}")

        if "timeout" in status or "failed" in status:
            return f"{base} — FAILED"
        elif "reversed" in status:
            return f"{base} — REVERSED"
        return base

    def _detect_anomalies(self, sorted_group: List[Dict]) -> List[Dict]:
        """Detect anomalies in payment timeline."""
        anomalies = []

        # Check for retries (multiple wallet transactions)
        wallet_txns = [t for t in sorted_group if t["source_system"] == "wallet"]
        if len(wallet_txns) > 1:
            anomalies.append({
                "type": "retry_storm",
                "severity": "high",
                "description": f"Wallet retry detected: {len(wallet_txns)} attempts",
                "count": len(wallet_txns),
            })

        # Check for reversal
        reversed_txns = [
            t for t in sorted_group
            if "revers" in str(t.get("status", "")).lower()
        ]
        if reversed_txns:
            anomalies.append({
                "type": "reversal",
                "severity": "medium",
                "description": "Transaction was reversed",
            })

        # Check timestamp gaps between systems
        if len(sorted_group) >= 2:
            for i in range(len(sorted_group) - 1):
                t1 = sorted_group[i]
                t2 = sorted_group[i + 1]
                try:
                    ts1 = t1["transaction_timestamp"]
                    ts2 = t2["transaction_timestamp"]
                    if isinstance(ts1, str):
                        ts1 = datetime.fromisoformat(ts1)
                    if isinstance(ts2, str):
                        ts2 = datetime.fromisoformat(ts2)
                    gap = abs((ts2 - ts1).total_seconds())
                    if gap > 5:
                        anomalies.append({
                            "type": "latency_gap",
                            "severity": "medium" if gap < 30 else "high",
                            "description": f"Latency gap: {gap:.1f}s between {t1['source_system']} → {t2['source_system']}",
                            "gap_seconds": gap,
                        })
                except Exception:
                    pass

        return anomalies

    def _determine_status(self, group: List[Dict]) -> str:
        """Determine canonical status from all transaction statuses."""
        statuses = [str(t.get("status", "")).lower() for t in group]

        if any("revers" in s for s in statuses):
            return "reversed"
        if any("failed" in s for s in statuses):
            return "failed"
        if any("complet" in s or "settled" in s for s in statuses):
            return "completed"
        if any("process" in s for s in statuses):
            return "processing"
        return "pending_reconciliation"