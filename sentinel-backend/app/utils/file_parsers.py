import pandas as pd
import xmltodict
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from loguru import logger


class FileParser:
    """Unified parser for bank export files: CSV, XML, XLSX, LOG."""

    @staticmethod
    def parse(file_path: str, source_system: str) -> List[Dict]:
        """Auto-detect file type and parse."""
        path = Path(file_path)
        suffix = path.suffix.lower()

        parsers = {
            ".csv": FileParser.parse_csv,
            ".xlsx": FileParser.parse_excel,
            ".xls": FileParser.parse_excel,
            ".xml": FileParser.parse_xml,
            ".log": FileParser.parse_log,
            ".txt": FileParser.parse_log,
        }

        parser_fn = parsers.get(suffix)
        if not parser_fn:
            raise ValueError(f"Unsupported file type: {suffix}")

        records = parser_fn(file_path)
        return FileParser._normalize(records, source_system)

    @staticmethod
    def parse_csv(file_path: str) -> List[Dict]:
        """Parse CSV transaction export."""
        try:
            df = pd.read_csv(file_path, dtype=str)
            df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
            return df.to_dict(orient="records")
        except Exception as e:
            logger.error(f"CSV parse error: {e}")
            raise

    @staticmethod
    def parse_excel(file_path: str) -> List[Dict]:
        """Parse Excel transaction export."""
        try:
            df = pd.read_excel(file_path, dtype=str, engine="openpyxl")
            df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
            return df.to_dict(orient="records")
        except Exception as e:
            logger.error(f"Excel parse error: {e}")
            raise

    @staticmethod
    def parse_xml(file_path: str) -> List[Dict]:
        """Parse Oracle XML payload files."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            parsed = xmltodict.parse(content)

            # Handle different XML structures
            # Try common Oracle XML patterns
            records = []
            root = parsed.get("transactions") or parsed.get("batch") or parsed

            if isinstance(root, dict):
                # Look for transaction list
                for key in ["transaction", "record", "item", "entry"]:
                    items = root.get(key)
                    if items:
                        if isinstance(items, list):
                            records = items
                        else:
                            records = [items]
                        break

            if not records:
                # Flatten top-level dict as single record
                records = [root]

            return records
        except Exception as e:
            logger.error(f"XML parse error: {e}")
            raise

    @staticmethod
    def parse_log(file_path: str) -> List[Dict]:
        """Parse structured log files (RAAST session logs, etc.)."""
        records = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    # Try JSON log format
                    if line.startswith("{"):
                        try:
                            record = json.loads(line)
                            records.append(record)
                            continue
                        except json.JSONDecodeError:
                            pass

                    # Try pipe-delimited format
                    if "|" in line:
                        parts = line.split("|")
                        record = {f"field_{i}": p.strip() for i, p in enumerate(parts)}
                        records.append(record)
                        continue

                    # Try CSV-like format
                    if "," in line:
                        parts = line.split(",")
                        record = {f"col_{i}": p.strip() for i, p in enumerate(parts)}
                        records.append(record)
                        continue

                    # Store as raw line
                    records.append({"raw_line": line, "line_num": line_num})

        except Exception as e:
            logger.error(f"Log parse error: {e}")
            raise

        return records

    @staticmethod
    def _normalize(records: List[Dict], source_system: str) -> List[Dict]:
        """
        Normalize diverse field names to Sentinel's canonical schema.
        Maps source-specific field names to standard names.
        """
        normalized = []

        # Field name mapping (source field → canonical field)
        field_map = {
            # Transaction IDs
            "txn_id": "source_transaction_id",
            "transaction_id": "source_transaction_id",
            "ref_id": "source_transaction_id",
            "reference": "source_transaction_id",
            "raast_ref": "source_transaction_id",
            "raast_reference": "source_transaction_id",
            "settlement_ref": "source_transaction_id",
            "batch_ref": "source_transaction_id",

            # Amounts
            "txn_amount": "amount",
            "transaction_amount": "amount",
            "amt": "amount",
            "value": "amount",
            "net_amount": "amount",

            # Timestamps
            "txn_timestamp": "transaction_timestamp",
            "txn_date": "transaction_timestamp",
            "created_at": "transaction_timestamp",
            "timestamp": "transaction_timestamp",
            "date_time": "transaction_timestamp",
            "transaction_date": "transaction_timestamp",

            # Accounts
            "from_account": "account_from",
            "debit_account": "account_from",
            "sender": "account_from",
            "to_account": "account_to",
            "credit_account": "account_to",
            "beneficiary": "account_to",
            "receiver": "account_to",

            # Status
            "txn_status": "status",
            "state": "status",
        }

        for record in records:
            normalized_record = {}

            for key, value in record.items():
                clean_key = key.strip().lower().replace(" ", "_").replace("-", "_")
                canonical_key = field_map.get(clean_key, clean_key)
                normalized_record[canonical_key] = value

            # Ensure required fields exist
            normalized_record.setdefault("source_transaction_id",
                                          normalized_record.get("id", f"UNKNOWN-{len(normalized)}"))
            normalized_record.setdefault("amount", "0")
            normalized_record.setdefault("currency", "PKR")
            normalized_record.setdefault("status", "unknown")
            normalized_record["source_system"] = source_system
            normalized_record["raw_data"] = record  # Keep original

            # Normalize amount to float
            try:
                amt = str(normalized_record["amount"]).replace(",", "").replace("PKR", "").strip()
                normalized_record["amount"] = float(amt) if amt else 0.0
            except (ValueError, TypeError):
                normalized_record["amount"] = 0.0

            # Normalize timestamp
            ts = normalized_record.get("transaction_timestamp")
            if ts:
                try:
                    if isinstance(ts, datetime):
                        normalized_record["transaction_timestamp"] = ts
                    else:
                        normalized_record["transaction_timestamp"] = pd.to_datetime(ts).to_pydatetime()
                except Exception:
                    normalized_record["transaction_timestamp"] = datetime.utcnow()
            else:
                normalized_record["transaction_timestamp"] = datetime.utcnow()

            normalized.append(normalized_record)

        logger.info(f"Normalized {len(normalized)} records for {source_system}")
        return normalized