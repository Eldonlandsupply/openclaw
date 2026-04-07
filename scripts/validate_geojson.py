#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_feature(feature: dict, index: int, required_fields: list[str]) -> list[str]:
    errors: list[str] = []
    props = feature.get("properties")
    if not isinstance(props, dict):
        errors.append(f"[feature[{index}] id=unknown]: properties must be an object")
        return errors

    feature_id = props.get("id")
    feature_label = feature_id if feature_id else f"feature-{index}"
    for field in required_fields:
        value = props.get(field)
        if value is None:
            errors.append(
                f"[feature[{index}] id={feature_label}]: required field '{field}' is missing"
            )
            continue

        if isinstance(value, str) and not value.strip():
            errors.append(
                f"[feature[{index}] id={feature_label}]: required field '{field}' is empty"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate parcel GeoJSON records")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    args = parser.parse_args()

    geojson = load_json(args.input)
    schema = load_json(args.schema)

    errors: list[str] = []
    warnings: list[str] = []

    expected_geojson_type = schema.get("geojson_type", "FeatureCollection")
    if geojson.get("type") != expected_geojson_type:
        errors.append(f"GeoJSON root type must be {expected_geojson_type}")

    features = geojson.get("features")
    if not isinstance(features, list):
        errors.append("GeoJSON features must be an array")
        features = []

    required_fields = schema.get("required_fields", ["id"])
    if (
        not isinstance(required_fields, list)
        or len(required_fields) == 0
        or any(
            not isinstance(field, str) or not field.strip() for field in required_fields
        )
    ):
        errors.append("schema required_fields must be a non-empty list of non-empty strings")
        required_fields = ["id"]
    elif "id" not in required_fields:
        warnings.append("schema does not list id as required_fields entry")

    for idx, feature in enumerate(features):
        if not isinstance(feature, dict):
            errors.append(f"[feature[{idx}] id=unknown]: feature must be an object")
            continue
        errors.extend(validate_feature(feature, idx, required_fields))

    report = {
        "input": str(args.input),
        "schema": str(args.schema),
        "features": len(features),
        "errors": errors,
        "warnings": warnings,
        "valid": len(errors) == 0,
    }

    report_path = args.input.parent / "validation_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== GeoJSON Validation Summary ===")
    print(f"  Input:    {args.input}")
    print(f"  Schema:   {args.schema}")
    print(f"  Features: {len(features)}")
    print(f"  Errors:   {len(errors)}")
    print(f"  Warnings: {len(warnings)}")
    print(f"  Valid:    {len(errors) == 0}\n")

    if errors:
        print("  Errors (up to 10):")
        for err in errors[:10]:
            print(f"    - {err}")
        print()

    print(f"  Report: {report_path}")

    if errors:
        print(f"FAILED: {len(errors)} validation error(s).")
        return 1

    print("PASSED: validation successful.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
