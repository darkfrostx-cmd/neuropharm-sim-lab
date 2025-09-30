"""ChEMBL, IUPHAR and BindingDB ingestion jobs."""

from __future__ import annotations

from typing import Iterable, Iterator, Mapping

try:  # pragma: no cover - optional dependency for live fetches
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from .evidence_quality import (
    normalise_chronicity_label,
    normalise_design_label,
    normalise_species_label,
)
from .ingest_base import BaseIngestionJob
from .models import BiolinkEntity, BiolinkPredicate, Edge, Node


class ChEMBLClient:
    BASE_URL = "https://www.ebi.ac.uk/chembl/api/data/activity.json"

    def __init__(self, session: "requests.Session" | None = None) -> None:
        if requests is None:
            raise ImportError("requests is required for ChEMBLClient")
        self.session = session or requests.Session()

    def iter_interactions(self, limit: int = 100) -> Iterator[dict]:
        params = {"limit": limit}
        response = self.session.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        return iter(response.json().get("activities", []))


class IUPHARClient:
    BASE_URL = "https://www.guidetopharmacology.org/services/targets"

    def __init__(self, session: "requests.Session" | None = None) -> None:
        if requests is None:
            raise ImportError("requests is required for IUPHARClient")
        self.session = session or requests.Session()

    def iter_targets(self, limit: int = 100) -> Iterator[dict]:
        response = self.session.get(self.BASE_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        return iter(data[:limit])


class BindingDBClient:
    BASE_URL = "https://www.bindingdb.org/axis2/services/BDBService/getLigandInteractions"

    def __init__(self, session: "requests.Session" | None = None) -> None:
        if requests is None:
            raise ImportError("requests is required for BindingDBClient")
        self.session = session or requests.Session()

    def iter_interactions(self, ligand: str, limit: int = 50) -> Iterator[dict]:
        params = {"ligand": ligand, "format": "json"}
        response = self.session.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        results = response.json() or []
        return iter(results[:limit])


class ChEMBLIngestion(BaseIngestionJob):
    name = "chembl"
    source = "ChEMBL"

    def __init__(self, client: ChEMBLClient | None = None) -> None:
        self.client = client or ChEMBLClient()

    def fetch(self, limit: int | None = None) -> Iterable[dict]:
        iterator = self.client.iter_interactions(limit=limit or 100)
        if limit is None:
            return iterator
        return (record for i, record in enumerate(iterator) if i < limit)

    def transform(self, record: dict) -> tuple[list[Node], list[Edge]]:
        nodes: list[Node] = []
        edges: list[Edge] = []
        compound_id = record.get("molecule_chembl_id")
        target_id = record.get("target_chembl_id") or record.get("target", {}).get("target_chembl_id")
        if not compound_id or not target_id:
            return nodes, edges
        compound_node = Node(
            id=compound_id,
            name=record.get("molecule_pref_name") or record.get("canonical_smiles", "Compound"),
            category=BiolinkEntity.CHEMICAL_SUBSTANCE,
            provided_by=self.source,
        )
        target_node = Node(
            id=target_id,
            name=record.get("target_pref_name", "Target"),
            category=BiolinkEntity.GENE,
            provided_by=self.source,
        )
        nodes.extend([compound_node, target_node])
        metadata = self._extract_metadata(record)
        evidence_payload = {
            "relation": record.get("standard_relation", "="),
            **{key: value for key, value in metadata.items() if value},
        }
        edges.append(
            Edge(
                subject=compound_node.id,
                predicate=BiolinkPredicate.INTERACTS_WITH,
                object=target_node.id,
                confidence=None,
                evidence=[
                    self.make_evidence(
                        self.source,
                        record.get("document_chembl_id"),
                        float(record.get("pchembl_value")) if record.get("pchembl_value") else None,
                        **evidence_payload,
                    )
                ],
            )
        )
        return nodes, edges

    @staticmethod
    def _extract_metadata(record: Mapping[str, object]) -> dict[str, str | None]:
        species_raw = (
            record.get("target_organism")
            or record.get("assay_organism")
            or record.get("organism")
            or record.get("assay_cell_type")
        )
        species = normalise_species_label(str(species_raw)) if species_raw else None

        description = " ".join(
            str(value)
            for value in (
                record.get("assay_description"),
                record.get("comment"),
                record.get("relationship_description"),
            )
            if value
        )
        chronicity = normalise_chronicity_label(str(record.get("assay_test_type"))) if record.get("assay_test_type") else None
        if not chronicity and description:
            chronicity = normalise_chronicity_label(description)

        design_candidate = (
            record.get("assay_type")
            or record.get("assay_format")
            or record.get("data_validity_comment")
        )
        design = normalise_design_label(str(design_candidate)) if design_candidate else None
        if not design and description:
            design = normalise_design_label(description)

        return {"species": species, "chronicity": chronicity, "design": design}


class IUPHARIngestion(BaseIngestionJob):
    name = "iuphar"
    source = "IUPHAR"

    def __init__(self, client: IUPHARClient | None = None) -> None:
        self.client = client or IUPHARClient()

    def fetch(self, limit: int | None = None) -> Iterable[dict]:
        iterator = self.client.iter_targets(limit=limit or 100)
        if limit is None:
            return iterator
        return (record for i, record in enumerate(iterator) if i < limit)

    def transform(self, record: dict) -> tuple[list[Node], list[Edge]]:
        node = Node(
            id=record.get("targetId") or record.get("iupharId", "unknown"),
            name=record.get("name", "IUPHAR target"),
            category=BiolinkEntity.GENE,
            provided_by=self.source,
            attributes={"family": record.get("family")},
        )
        return [node], []


class BindingDBIngestion(BaseIngestionJob):
    name = "bindingdb"
    source = "BindingDB"

    def __init__(self, client: BindingDBClient | None = None, ligand: str = "CHEMBL25") -> None:
        self.client = client or BindingDBClient()
        self.ligand = ligand

    def fetch(self, limit: int | None = None) -> Iterable[dict]:
        iterator = self.client.iter_interactions(self.ligand, limit=limit or 50)
        if limit is None:
            return iterator
        return (record for i, record in enumerate(iterator) if i < limit)

    def transform(self, record: dict) -> tuple[list[Node], list[Edge]]:
        nodes: list[Node] = []
        edges: list[Edge] = []
        ligand_id = record.get("LigandName") or self.ligand
        target_id = record.get("TargetAccession") or record.get("UniProt")
        if not target_id:
            return nodes, edges
        ligand_node = Node(
            id=ligand_id,
            name=record.get("LigandName", ligand_id),
            category=BiolinkEntity.CHEMICAL_SUBSTANCE,
            provided_by=self.source,
        )
        target_node = Node(
            id=target_id,
            name=record.get("TargetName", target_id),
            category=BiolinkEntity.GENE,
            provided_by=self.source,
        )
        nodes.extend([ligand_node, target_node])
        pmid = record.get("PMID")
        if pmid and not str(pmid).upper().startswith("PMID:"):
            pmid = f"PMID:{pmid}"
        metadata = {
            "species": self._infer_species(record),
            "chronicity": "acute",
            "design": "in_vitro",
        }
        evidence_payload = {
            "measure": str(record.get("Ki")),
            **{key: value for key, value in metadata.items() if value},
        }
        edges.append(
            Edge(
                subject=ligand_node.id,
                predicate=BiolinkPredicate.INTERACTS_WITH,
                object=target_node.id,
                evidence=[
                    self.make_evidence(
                        self.source,
                        pmid,
                        None,
                        **evidence_payload,
                    )
                ],
            )
        )
        return nodes, edges

    @staticmethod
    def _infer_species(record: Mapping[str, object]) -> str | None:
        for key in ("TargetSpecies", "Species", "Organism"):
            value = record.get(key)
            if value:
                return normalise_species_label(str(value))
        return None


__all__ = [
    "ChEMBLClient",
    "IUPHARClient",
    "BindingDBClient",
    "ChEMBLIngestion",
    "IUPHARIngestion",
    "BindingDBIngestion",
]

