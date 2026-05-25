#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/ocr-env/bin/python"
MAIN="$SCRIPT_DIR/pdf_to_text.py"

usage() {
    cat <<'HELP'
Usage: ./run.sh <pdf> [options]

Options:
  -h, --help       Show this help
  -o, --save       Save plain OCR text to output/<pdf>-ocr.txt
  --html           Generate positioned HTML overlay (opens in browser)
  --translate      Translate to English via Gemini
  --all            HTML + translate (full pipeline)

Examples:
  ./run.sh notice.pdf                  Plain OCR to stdout
  ./run.sh notice.pdf --save           Save to output/notice-ocr.txt
  ./run.sh notice.pdf --html           HTML overlay
  ./run.sh notice.pdf --translate      Translate to English
  ./run.sh notice.pdf --all            HTML + translate, opens in browser
HELP
}

OPEN=false
ARGS=()

for arg in "$@"; do
    case "$arg" in
        -h|--help) usage; exit 0 ;;
        --all) ARGS+=(--html --translate); OPEN=true ;;
        --open) OPEN=true ;;
        *) ARGS+=("$arg") ;;
    esac
done

if [ ${#ARGS[@]} -eq 0 ]; then
    usage
    exit 1
fi

"$VENV_PYTHON" "$MAIN" "${ARGS[@]}"

if [ "$OPEN" = true ]; then
    PDF_NAME=$(basename "${ARGS[0]}" .pdf)
    HTML="$SCRIPT_DIR/output/$PDF_NAME.html"
    if [ -f "$HTML" ]; then
        xdg-open "$HTML" 2>/dev/null || open "$HTML" 2>/dev/null || echo "Open $HTML in your browser"
    fi
fi
