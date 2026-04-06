"""
Semantic legal section segmentation and coastal entity extraction.
"""

from __future__ import annotations

import re

from .config import COASTAL_PATTERN
from .models import LegalBlock

# ---------------------------------------------------------------------------
# Section classification patterns
# ---------------------------------------------------------------------------

_SECTION_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "metadata": [
        re.compile(
            r"(?i)^(república|republica|tribunal|juzgado|sala|radicación|radicacion|expediente)"
        ),
        re.compile(r"(?i)^(magistrado|magistrada|ponente|secretario|secretaria)"),
        re.compile(r"(?i)^(demandante|demandado|actor|accionante|accionado)"),
    ],
    "facts": [
        re.compile(r"(?i)\b(hechos|antecedentes|síntesis|sintesis|resumen)\b"),
        re.compile(r"(?i)\b(situación fáctica|situacion factica|contexto)\b"),
    ],
    "claims": [
        re.compile(r"(?i)\b(pretensión|pretension|pretensiones|solicita|solicitud)\b"),
        re.compile(r"(?i)\b(pide|petición|peticion|demanda)\b"),
    ],
    "legal_basis": [
        re.compile(r"(?i)\b(ley|decreto|artículo|articulo|constitución|constitucion)\b"),
        re.compile(r"(?i)\b(norma|código|codigo|reglamento|resolución|resolucion)\b"),
        re.compile(r"(?i)\b(fundamento|fundamentos|marco jurídico|marco juridico)\b"),
    ],
    "evidence": [
        re.compile(r"(?i)\b(prueba|pruebas|peritaje|dictamen|testimonio)\b"),
        re.compile(r"(?i)\b(documento|documentos|acervo probatorio)\b"),
        re.compile(r"(?i)\b(inspección|inspeccion|reconocimiento)\b"),
    ],
    "analysis": [
        re.compile(r"(?i)\b(considera|considerando|consideraciones|análisis|analisis)\b"),
        re.compile(r"(?i)\b(problema jurídico|problema juridico|estudio|valoración|valoracion)\b"),
    ],
    "decision": [
        re.compile(r"(?i)\b(resuelve|falla|decide|niega|concede|ordena)\b"),
        re.compile(r"(?i)\b(declara|condena|absuelve|accede|deniega)\b"),
    ],
    "citations": [
        re.compile(r"(?i)\b(sentencia\s+[TC]-\d+|corte\s+constitucional)\b"),
        re.compile(r"(?i)\b(consejo\s+de\s+estado|jurisprudencia)\b"),
    ],
}

# ---------------------------------------------------------------------------
# Coastal entity patterns
# ---------------------------------------------------------------------------

_COASTAL_ENTITY_PATTERNS: dict[str, re.Pattern[str]] = {
    "playa": re.compile(r"(?i)\b(playa|playas)\b"),
    "bahia": re.compile(r"(?i)\b(bahía|bahia|bahías|bahias)\b"),
    "bajamar": re.compile(r"(?i)\b(bajamar|zona de bajamar|terrenos de bajamar)\b"),
    "litoral": re.compile(r"(?i)\b(litoral|línea de costa|linea de costa|zona costera)\b"),
    "erosion": re.compile(r"(?i)\b(erosión|erosion|erosión costera|erosion costera)\b"),
    "ocupacion": re.compile(r"(?i)\b(ocupación|ocupacion|ocupación indebida|ocupacion indebida)\b"),
    "espacio_publico": re.compile(
        r"(?i)\b(espacio público|espacio publico|bien público|bien publico)\b"
    ),
    "dimar": re.compile(r"(?i)\b(dimar|dirección general marítima|direccion general maritima)\b"),
    "concesion_maritima": re.compile(
        r"(?i)\b(concesión marítima|concesion maritima|permiso marítimo|permiso maritimo)\b"
    ),
    "bienes_uso_publico": re.compile(
        r"(?i)\b(bienes de uso público|bienes de uso publico|dominio público|dominio publico)\b"
    ),
    "recuperacion_costera": re.compile(
        r"(?i)\b(recuperación costera|recuperacion costera|restauración costera|restauracion costera)\b"
    ),
    "servidumbre": re.compile(
        r"(?i)\b(servidumbre|servidumbre de tránsito|servidumbre de transito)\b"
    ),
    "proteccion_litoral": re.compile(
        r"(?i)\b(protección litoral|proteccion litoral|protección costera|proteccion costera)\b"
    ),
    "pleamar": re.compile(r"(?i)\b(pleamar|marea alta|nivel de pleamar)\b"),
    "manglar": re.compile(r"(?i)\b(manglar|manglares|zona de manglar)\b"),
    "puerto": re.compile(
        r"(?i)\b(puerto|muelle|embarcadero|terminal portuario|terminal portuaria)\b"
    ),
    "estuario": re.compile(r"(?i)\b(estuario|estuarios|desembocadura)\b"),
    "restinga": re.compile(r"(?i)\b(restinga|restingas)\b"),
    "acantilado": re.compile(r"(?i)\b(acantilado|acantilados|risco|riscos)\b"),
    "vertimiento": re.compile(
        r"(?i)\b(vertimiento|vertimientos|aguas residuales|aguas servidas)\b"
    ),
    "emisario": re.compile(r"(?i)\b(emisario submarino|emisario|emisarios)\b"),
    "arrecife": re.compile(
        r"(?i)\b(arrecife|arrecifes|formación arrecifal|formacion arrecifal|coral|corales)\b"
    ),
    "colector_pluvial": re.compile(
        r"(?i)\b(colector pluvial|colector|colectores|sistema de drenaje pluvial)\b"
    ),
    "contaminacion_marina": re.compile(
        r"(?i)\b(contaminación marina|contaminacion marina"
        r"|contaminación del mar|contaminacion del mar|contaminación costera)\b"
    ),
    "pradera_marina": re.compile(
        r"(?i)\b(pradera marina|praderas marinas|pastos marinos|algas marinas)\b"
    ),
    "capitania": re.compile(r"(?i)\b(capitanía de puerto|capitania de puerto|capitanía)\b"),
    "corpamag": re.compile(
        r"(?i)\b(corpamag|corporación autónoma regional del magdalena"
        r"|corporacion autonoma regional del magdalena)\b"
    ),
}


# ---------------------------------------------------------------------------
# Section segmentation
# ---------------------------------------------------------------------------


def _classify_paragraph(paragraph: str) -> tuple[str, float]:
    """Classify a paragraph into a legal section type with confidence score."""
    scores: dict[str, float] = {section: 0.0 for section in _SECTION_PATTERNS}
    para_lower = paragraph.lower()

    for section, patterns in _SECTION_PATTERNS.items():
        for pattern in patterns:
            scores[section] += len(pattern.findall(para_lower))

    if paragraph.startswith(
        ("República", "REPÚBLICA", "Tribunal", "TRIBUNAL", "Juzgado", "JUZGADO")
    ):
        scores["metadata"] += 2

    best_section = max(scores, key=scores.get)  # type: ignore[arg-type]
    best_score = scores[best_section]

    if best_score < 1:
        return "analysis", 0.0

    return best_section, min(1.0, best_score / 5.0)


def _calculate_coastal_relevance(paragraph: str) -> float:
    """Calculate coastal/beach-law relevance score for a paragraph (0–1)."""
    matches = len(COASTAL_PATTERN.findall(paragraph))
    words = len(paragraph.split())
    if words == 0:
        return 0.0
    return min(1.0, (matches * 100) / words)


def segment_legal_sections(md_text: str) -> list[LegalBlock]:
    """Segment a legal document into semantic sections.

    Section types: metadata, facts, claims, legal_basis, evidence,
    analysis, decision, citations.
    """
    paragraphs = [p.strip() for p in md_text.split("\n\n") if p.strip()]
    blocks: list[LegalBlock] = []

    for para in paragraphs:
        section_type, score = _classify_paragraph(para)
        coastal_relevance = _calculate_coastal_relevance(para)
        blocks.append(
            LegalBlock(
                section_type=section_type,
                text=para,
                score=score,
                coastal_relevance=coastal_relevance,
            )
        )

    return blocks


# ---------------------------------------------------------------------------
# Coastal entity extraction
# ---------------------------------------------------------------------------


def _normalize_entity(entity: str) -> str:
    """Normalize an entity string for consistent representation."""
    return re.sub(r"\s+", " ", entity.lower().strip())


def extract_coastal_legal_entities(md_text: str) -> dict[str, list[str]]:
    """Extract and normalize coastal legal entities from document text.

    Returns a dict mapping entity types to sorted lists of unique normalized
    values found.
    """
    entities: dict[str, set[str]] = {key: set() for key in _COASTAL_ENTITY_PATTERNS}

    for entity_type, pattern in _COASTAL_ENTITY_PATTERNS.items():
        for match in pattern.findall(md_text):
            if isinstance(match, tuple):
                match = match[0]
            entities[entity_type].add(_normalize_entity(match))

    return {k: sorted(v) for k, v in entities.items() if v}
