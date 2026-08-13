"""cidmap: font-scoped CID -> Devanagari mapping tool.

For a PDF whose Type0/Identity-H fonts drop CIDs from their ToUnicode CMaps,
builds a robust, versioned mapping file that other projects can consume.
Pipeline: decode the text layer, OCR cross-check the unknown glyphs, review
the candidates in an HTML sheet, and commit decisions to a canonical JSON.

The canonical file keys mappings by raw integer CID with optional per-font-subset
scopes (a CID that renders differently in KLMNGO+Kalimati-1 vs -2 keeps both).
"""

__version__ = "0.1.0"