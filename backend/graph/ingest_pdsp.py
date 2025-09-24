"""PDSP Ki database ingestion job with local fallback sample."""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

try:  # pragma: no cover - optional dependency for live fetches
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from .ingest_base import BaseIngestionJob
from .models import BiolinkEntity, BiolinkPredicate, Edge, Node

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PDSPRecord:
    ligand: str
    uniprot: str
    target: str
    ki_nm: float | None
    reference: str | None


class PDSPKiClient:
    """Small helper to stream PDSP Ki interaction records."""

    BASE_URL = "https://pdsp.unc.edu/databases/kidb_download.php"

    def __init__(
        self,
        *,
        session: "requests.Session" | None = None,
        dataset_path: Path | None = None,
    ) -> None:
        self.session = session
        self.dataset_path = dataset_path or Path(__file__).with_name("data").joinpath("pdsp_ki_sample.tsv")
        if self.session is None and requests is not None:
            self.session = requests.Session()

    def iter_affinities(self, limit: int | None = None) -> Iterator[PDSPRecord]:
        """Yield :class:`PDSPRecord` entries from PDSP Ki."""

        if self.dataset_path.exists():
            LOGGER.debug("Reading PDSP Ki sample from %s", self.dataset_path)
            yield from self._read_local(limit)
            return
        if requests is None:
            raise ImportError("requests is required to fetch PDSP Ki dataset")
        LOGGER.debug("Fetching PDSP Ki dataset from %s", self.BASE_URL)
        response = self.session.post(  # type: ignore[union-attr]
            self.BASE_URL,
            data={"download": "Download Ki Dataset"},
            timeout=60,
        )
        response.raise_for_status()
        yield from self._parse_stream(io.StringIO(response.text), limit)

    def _read_local(self, limit: int | None) -> Iterator[PDSPRecord]:
        with self.dataset_path.open("r", encoding="utf-8") as handle:
            yield from self._parse_stream(handle, limit)

    @staticmethod
    def _parse_stream(handle: io.TextIOBase, limit: int | None) -> Iterator[PDSPRecord]:
        reader = csv.DictReader(handle, delimiter="\t")
        for index, row in enumerate(reader):
            ligand = (row.get("LigandName") or row.get("Ligand") or "").strip()
            target = (row.get("TargetName") or row.get("Target") or "").strip()
            uniprot = (row.get("UniProt") or row.get("UniProtID") or "").strip()
            reference = (row.get("Reference") or row.get("PMID") or "").strip() or None
            ki_raw = (row.get("Ki_nM") or row.get("Ki (nM)") or "").strip()
            ki_nm: float | None
            try:
                ki_nm = float(ki_raw) if ki_raw else None
            except ValueError:
                ki_nm = None
            yield PDSPRecord(ligand=ligand, uniprot=uniprot, target=target, ki_nm=ki_nm, reference=reference)
            if limit is not None and index + 1 >= limit:
                break


class PDSPKiIngestion(BaseIngestionJob):
    """Persist PDSP Ki ligand-receptor affinities into the knowledge graph."""

    name = "pdsp_ki"
    source = "PDSP Ki"

    def __init__(self, client: PDSPKiClient | None = None) -> None:
        self.client = client or PDSPKiClient()

    def fetch(self, limit: int | None = None) -> Iterable[PDSPRecord]:
        return self.client.iter_affinities(limit=limit)

    def transform(self, record: PDSPRecord) -> tuple[list[Node], list[Edge]]:
        nodes: list[Node] = []
        edges: list[Edge] = []
        ligand_id = record.ligand.strip()
        target_id = record.target.strip() or record.uniprot.strip()
        if not ligand_id or not target_id:
            return nodes, edges
        ligand_node = Node(
            id=f"PDSP:{ligand_id}",
            name=record.ligand or ligand_id,
            category=BiolinkEntity.CHEMICAL_SUBSTANCE,
            provided_by=self.source,
            attributes={"dataset": "pdsp_ki"},
        )
        target_node = Node(
            id=f"UniProt:{record.uniprot}" if record.uniprot else target_id,
            name=record.target or record.uniprot or target_id,
            category=BiolinkEntity.GENE,
            provided_by=self.source,
            attributes={"uniprot": record.uniprot} if record.uniprot else {},
        )
        nodes.extend([ligand_node, target_node])
        annotations = {"assay": "binding", "unit": "nM"}
        if record.ki_nm is not None:
            confidence = float(max(0.05, min(0.99, 1.0 / (1.0 + record.ki_nm / 10.0))))
            annotations["ki"] = record.ki_nm
        else:
            confidence = None
        edges.append(
            Edge(
                subject=ligand_node.id,
                predicate=BiolinkPredicate.INTERACTS_WITH,
                object=target_node.id,
                evidence=[
                    self.make_evidence(
                        self.source,
                        record.reference,
                        confidence,
                        **annotations,
                    )
                ],
                confidence=confidence,
            )
        )
        return nodes, edges


__all__ = ["PDSPKiIngestion", "PDSPKiClient", "PDSPRecord"]
