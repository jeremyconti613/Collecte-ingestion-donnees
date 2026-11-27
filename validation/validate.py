import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "validation" / "schemas" / "schema.json"
INPUT_PATH = PROJECT_ROOT / "data" / "output" / "spotify_artist_tracks_since_2026.jsonl"


def main() -> int:
    if not INPUT_PATH.exists():
        print(f"Fichier absent: {INPUT_PATH}")
        return 1

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    valid = 0
    invalid = 0

    with INPUT_PATH.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            message = json.loads(line)
            errors = sorted(
                validator.iter_errors(message),
                key=lambda error: list(error.path),
            )
            if errors:
                invalid += 1
                print(f"Ligne {line_number}:")
                for error in errors:
                    print(f"  - {'.'.join(map(str, error.path)) or '$'}: {error.message}")
            else:
                valid += 1

    print(f"Validation terminée: {valid} valide(s), {invalid} invalide(s)")
    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())