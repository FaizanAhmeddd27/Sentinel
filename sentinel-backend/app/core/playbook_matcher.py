from typing import List, Optional, Tuple
from rapidfuzz import fuzz
from app.models.playbook import Playbook
from app.models.incident import Incident
from loguru import logger


class PlaybookMatcher:
    """
    Matches incidents to the most appropriate operational playbook
    using a multi-signal scoring system:

    Signal 1: Exact incident type match (50 points)
    Signal 2: Keyword match in incident title/description (10 points per keyword)
    Signal 3: Source system match (20 points)
    Signal 4: Fuzzy title similarity (0-20 points)
    Signal 5: Historical usage weight (0-10 points)

    Max possible score: 100+
    Minimum threshold for a match: 30 points
    """

    MIN_MATCH_THRESHOLD = 30

    def match(
        self, incident: Incident, playbooks: List[Playbook]
    ) -> Tuple[Optional[Playbook], int, List[str]]:
        """
        Returns: (best_playbook, score, matched_signals)
        Returns (None, 0, []) if no playbook meets threshold.
        """
        if not playbooks:
            return None, 0, []

        incident_type_str = (
            incident.incident_type.value if incident.incident_type else ""
        )
        incident_text = f"{incident.title or ''} {incident.description or ''}".lower()
        source_system = (incident.source_system or "").lower()

        scored: List[Tuple[Playbook, int, List[str]]] = []

        for pb in playbooks:
            score = 0
            matched_signals = []

            # Signal 1: Exact incident type match
            triggers = pb.trigger_incident_types or []
            if incident_type_str and incident_type_str in triggers:
                score += 50
                matched_signals.append(f"incident_type:{incident_type_str}")

            # Signal 2: Keyword match
            keywords = pb.trigger_keywords or []
            for kw in keywords:
                if kw.lower() in incident_text:
                    score += 10
                    matched_signals.append(f"keyword:{kw}")

            # Signal 3: Source system match
            if source_system and source_system in str(triggers).lower():
                score += 20
                matched_signals.append(f"source_system:{source_system}")

            # Signal 4: Fuzzy title similarity
            fuzzy_score = fuzz.partial_ratio(
                pb.title.lower(), incident_text
            )
            fuzzy_points = int(fuzzy_score / 100 * 20)
            if fuzzy_points > 5:
                score += fuzzy_points
                matched_signals.append(f"fuzzy_title:{fuzzy_score}%")

            # Signal 5: Usage weight (popular playbooks get slight boost)
            usage = pb.usage_count or 0
            if usage > 50:
                score += 10
                matched_signals.append("high_usage_playbook")
            elif usage > 20:
                score += 5
                matched_signals.append("moderate_usage_playbook")

            if score >= self.MIN_MATCH_THRESHOLD:
                scored.append((pb, score, matched_signals))
                logger.debug(
                    f"Playbook {pb.playbook_code} scored {score} "
                    f"for incident type {incident_type_str}"
                )

        if not scored:
            logger.info(f"No playbook matched incident {incident.id} (type: {incident_type_str})")
            return None, 0, []

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        best_playbook, best_score, best_signals = scored[0]

        logger.info(
            f"Best playbook match: {best_playbook.playbook_code} "
            f"score={best_score} signals={best_signals}"
        )
        return best_playbook, best_score, best_signals