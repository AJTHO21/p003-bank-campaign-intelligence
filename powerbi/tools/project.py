"""Build and validate the P003 Power BI project from the pinned Task 006 exports."""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from jsonschema import Draft7Validator
from referencing import Registry
from referencing.jsonschema import DRAFT7

import channel_page
import executive_page
from atomic_io import (
    atomic_write, check_path, fsync_directory, mkdir_durable, read_existing, scratch_directory, staging_area,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUNDLE = ROOT.parent / "data/reporting/task006/fcb2cc6d497320de81ec9cec47a9457fa74b8765c204bc4adadf66e0d50c6e42"
BUNDLE_SHA = SOURCE_BUNDLE.name
SNAPSHOT_SHA = "74adfc578bf77a7ff4bb1ba4a9f8709d9e3c6907342959c2c8416847e0afb4d8"
NAME = "P003_Bank_Campaign_Intelligence"
REPORT = f"{NAME}.Report"
MODEL = f"{NAME}.SemanticModel"
PBIP = f"{NAME}.pbip"
CSV_FOLDER_PLACEHOLDER = "SET_P003_CSV_FOLDER"
DATA = "private_csv"
COUNTS = {
    "executive_baseline": 1, "observed_segments": 48, "observed_cross_tabs": 119,
    "previous_outcome": 3, "campaign_frequency": 42, "prior_contact_history": 4,
    "non_sentinel_days": 72, "prior_failure_strata": 16, "comparison_estimates": 7,
    "comparison_weights": 37, "segment_estimates": 31, "segment_weights": 3,
}
TYPES = {
    "text": ("string", "type text"),
    "int64": ("int64", "Int64.Type"),
    "decimal": ("double", "type number"),
    "logical": ("boolean", "type logical"),
}
SCHEMA_BASE = "https://developer.microsoft.com/json-schemas/fabric"
THEME_NAME = "MidnightEmerald"
PALETTE = ("#14283F", "#177F78", "#D5A34A", "#C76B63", "#71889B", "#F5F7FA")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(document):
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files_under(root):
    require(not root.is_symlink(), f"Symlink refused: {root}")
    if not root.exists():
        return []
    require(root.is_dir(), f"Expected directory: {root}")
    files = []
    for path in sorted(root.iterdir()):
        if path.name == ".pbi":
            require(not path.is_symlink() and path.is_dir(), f"Invalid Desktop local directory: {path}")
            continue
        require(not path.is_symlink(), f"Symlink refused: {path}")
        if path.is_dir():
            files.extend(files_under(path))
        else:
            require(path.is_file(), f"Invalid managed file: {path}")
            files.append(path)
    return files


def csv_rows(path, spec):
    with path.open(encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle, strict=True)
        require(rows.fieldnames == [item["name"] for item in spec["columns"]], f"Wrong headers: {path.name}")
        result = []
        keys = set()
        for row in rows:
            require(None not in row and None not in row.values(), f"Wrong field count: {path.name}")
            typed = {}
            for item in spec["columns"]:
                name, kind = item["name"], item["type"]
                value = row[name]
                if value == "":
                    require(item["nullable"], f"Unexpected null: {path.name}.{name}")
                    typed[name] = None
                elif kind == "int64":
                    typed[name] = int(value)
                    require(str(typed[name]) == value and -(2**63) <= typed[name] < 2**63,
                            f"Invalid integer: {path.name}.{name}")
                elif kind == "decimal":
                    typed[name] = Decimal(value)
                    require(typed[name].is_finite(), f"Non-finite decimal: {path.name}.{name}")
                elif kind == "logical":
                    require(value in {"true", "false"}, f"Invalid logical: {path.name}.{name}")
                    typed[name] = value == "true"
                else:
                    require(kind == "text", f"Unknown type: {kind}")
                    typed[name] = value
            key = tuple(typed[name] for name in spec["grain"])
            require(key not in keys, f"Duplicate grain: {path.name}: {key}")
            require(typed["source_sha256"] == SNAPSHOT_SHA, f"Wrong source fingerprint: {path.name}")
            keys.add(key)
            result.append(typed)
        return result


def validate_bundle(folder, *, private=True):
    check_path(folder)
    require(folder.is_dir(), f"Expected private bundle directory: {folder}")
    if private:
        require(folder.stat().st_mode & 0o077 == 0, "Local CSV directory must be private")
    manifest_file = folder / "manifest.json"
    require(manifest_file.is_file() and not manifest_file.is_symlink() and digest(manifest_file) == BUNDLE_SHA,
            "Task 006 manifest does not match the approved bundle")
    manifest = load(manifest_file)
    require(manifest["source_sha256"] == SNAPSHOT_SHA, "Unexpected snapshot")
    require({path.name for path in folder.iterdir()} == {"manifest.json", *manifest["tables"]},
            "Unexpected private CSV inventory")
    tables = {}
    for filename, spec in manifest["tables"].items():
        stem = Path(filename).stem
        path = folder / filename
        require(path.is_file() and not path.is_symlink() and digest(path) == spec["sha256"],
                f"CSV hash mismatch: {filename}")
        if private:
            require(path.stat().st_mode & 0o077 == 0, f"CSV permissions: {filename}")
        rows = csv_rows(path, spec)
        require(len(rows) == COUNTS[stem] == spec["rows"], f"CSV row count mismatch: {filename}")
        tables[stem] = rows
    require(set(tables) == set(COUNTS) and sum(map(len, tables.values())) == 383, "Aggregate inventory mismatch")
    if private:
        require(manifest_file.stat().st_mode & 0o077 == 0, "Manifest permissions")
    reconcile(tables)
    return manifest


def rounded(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def reconcile(tables):
    base, = tables["executive_baseline"]
    require((base["numerator"], base["denominator"], rounded(base["rate"] * 100)) ==
            (4640, 41188, Decimal("11.27")), "Baseline reconciliation failed")
    channels = {row["level"]: (row["numerator"], row["denominator"], rounded(row["rate"] * 100))
                for row in tables["observed_segments"] if row["dimension"] == "contact"}
    require(channels == {"cellular": (3853, 26144, Decimal("14.74")),
                         "telephone": (787, 15044, Decimal("5.23"))}, "Channel reconciliation failed")
    for row in [base, *tables["previous_outcome"],
                *(item for item in tables["observed_segments"] if item["dimension"] == "contact")]:
        check_ratio(row["rate"], row["numerator"], row["denominator"])
    prior = {row["poutcome"]: (row["numerator"], row["denominator"], rounded(row["rate"] * 100))
             for row in tables["previous_outcome"]}
    require(prior == {"success": (894, 1373, Decimal("65.11")),
                      "failure": (605, 4252, Decimal("14.23")),
                      "nonexistent": (3141, 35563, Decimal("8.83"))}, "Prior outcome reconciliation failed")
    gaps = {(row["family"], row["method"]): rounded(row["gap_pp"])
            for row in tables["comparison_estimates"]}
    expected = {
        ("channel", "crude"): "9.51", ("channel", "prior_outcome"): "6.43",
        ("channel", "contact_month"): "8.04", ("prior_failure", "crude"): "38.46",
        ("prior_failure", "month_standardized"): "31.10",
        ("prior_failure", "seven_month_sensitivity"): "34.26",
        ("prior_failure", "frequency_standardized"): "37.97",
    }
    require(gaps == {key: Decimal(value) for key, value in expected.items()}, "Gap reconciliation failed")
    for row in tables["comparison_estimates"]:
        if row["estimate_type"] == "standardized":
            for prefix in ("a", "b"):
                check_ratio(row[f"{prefix}_rate"], row[f"weighted_{prefix}_numerator"],
                            row["weighted_denominator"])
    for row in tables["segment_estimates"]:
        if row["sparse_strata"]:
            require(all(row[field] is None for field in ("adjusted_rate", "weighted_numerator",
                                                        "weighted_denominator")), "Unsupported segment estimate")
        else:
            check_ratio(row["adjusted_rate"], row["weighted_numerator"], row["weighted_denominator"])


def check_ratio(rate, numerator, denominator):
    require(abs(rate - Decimal(numerator) / denominator) < Decimal("1e-15"), "Weighted estimate reconciliation failed")


def lineage(label):
    return uuid5(NAMESPACE_URL, f"urn:p003-bank-campaign-intelligence:{label}")


def measures(name):
    guards = {"observed_segments": ("dimension",), "observed_cross_tabs": ("dimension", "stratum_type"),
              "non_sentinel_days": ("scope",), "previous_outcome": (), "campaign_frequency": (),
              "prior_contact_history": (), "executive_baseline": ()}
    if name in guards:
        numerator = f"SUM({name}[numerator])"
        denominator = f"SUM({name}[denominator])"
        condition = " && ".join(f"HASONEVALUE({name}[{field}])" for field in guards[name])
        rate = f"DIVIDE({numerator}, {denominator})"
        if name == "executive_baseline":
            yield "Observations", denominator, "#,0"
            yield "Subscriptions", numerator, "#,0"
        yield f"{name} observed rate", f"IF({condition}, {rate})" if condition else rate, "0.00%"
    elif name in {"comparison_estimates", "segment_estimates"}:
        fields = ("a_rate", "b_rate") if name == "comparison_estimates" else ("adjusted_rate",)
        for field in fields:
            yield f"{name} {field}", f"IF(COUNTROWS({name}) = 1, SELECTEDVALUE({name}[{field}]))", "0.00%"


def table_tmdl(name, spec):
    columns = spec["columns"]
    lines = [f"table {name}", f"\tlineageTag: {lineage(name)}", ""]
    for label, dax, fmt in measures(name):
        lines += [f"\tmeasure '{label}' = {dax}", f"\t\tformatString: {fmt}",
                  f"\t\tlineageTag: {lineage(name + ':measure:' + label)}", ""]
    for col in columns:
        field = col["name"]
        lines += [f"\tcolumn {field}", f"\t\tdataType: {TYPES[col['type']][0]}",
                  f"\t\tlineageTag: {lineage(name + ':column:' + field)}",
                  "\t\tsummarizeBy: none", f"\t\tsourceColumn: {field}"]
        if name == "comparison_weights" and field == "stratum":
            lines.append("\t\tsortByColumn: calendar_month_order")
        lines.append("")
    if name == "comparison_weights":
        lines += [
            "\tcolumn calendar_month_label",
            "\t\tdataType: string",
            f"\t\tlineageTag: {lineage(name + ':column:calendar_month_label')}",
            "\t\tsummarizeBy: none",
            "\t\tsourceColumn: calendar_month_label",
            "\t\tsortByColumn: calendar_month_order",
            "",
            "\tcolumn calendar_month_order",
            "\t\tdataType: int64",
            f"\t\tlineageTag: {lineage(name + ':column:calendar_month_order')}",
            "\t\tsummarizeBy: none",
            "\t\tsourceColumn: calendar_month_order",
            "\t\tformatString: 0",
            "\t\tisHidden",
            "",
        ]
    quoted_fields = "{" + ", ".join(f'"{col["name"]}"' for col in columns) + "}"
    nullable = "{" + ", ".join(f'"{col["name"]}"' for col in columns if col["nullable"]) + "}"
    types = "{" + ", ".join(f'{{"{col["name"]}", {TYPES[col["type"]][1]}}}' for col in columns) + "}"
    lines += [f"\tpartition {name} = m", "\t\tmode: import", "\t\tsource =",
              "\t\t\t\tlet",
              f'\t\t\t\t    Parsed = Csv.Document(File.Contents(P003CsvFolder & "\\{name}.csv"), '
              '[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
              "\t\t\t\t    Headers = Table.PromoteHeaders(Parsed, [PromoteAllScalars=true]),",
              f"\t\t\t\t    Expected = {quoted_fields},",
              '\t\t\t\t    Checked = if Table.ColumnNames(Headers) = Expected then Headers else error "Unexpected P003 CSV headers",',
              f"\t\t\t\t    Nullable = {nullable},",
              '\t\t\t\t    Blanks = if List.IsEmpty(Nullable) then Checked else Table.ReplaceValue(Checked, "", null, Replacer.ReplaceValue, Nullable),',
              f'\t\t\t\t    Typed = Table.TransformColumnTypes(Blanks, {types}, "en-US"),',
              f'\t\t\t\t    Verified = if Table.RowCount(Typed) = {spec["rows"]} '
              'then Typed else error "Unexpected P003 CSV row count"']
    result = "Verified"
    if name == "comparison_weights":
        lines[-1] += ","
        lines += [
            "\t\t\t\t    MonthOrder = [jan = 1, feb = 2, mar = 3, apr = 4, may = 5, jun = 6, "
            "jul = 7, aug = 8, sep = 9, oct = 10, nov = 11, dec = 12],",
            '\t\t\t\t    WithMonthOrder = Table.AddColumn(Verified, "calendar_month_order", '
            "each Record.FieldOrDefault(MonthOrder, [stratum], null), Int64.Type),",
            '\t\t\t\t    MonthLabels = [mar = "Mar", apr = "Apr", may = "May", jun = "Jun", '
            'jul = "Jul", aug = "Aug", sep = "Sep", oct = "Oct", nov = "Nov"],',
            '\t\t\t\t    WithMonthLabel = Table.AddColumn(WithMonthOrder, "calendar_month_label", '
            "each Record.FieldOrDefault(MonthLabels, [stratum], [stratum]), type text)",
        ]
        result = "WithMonthLabel"
    lines += ["\t\t\t\tin", f"\t\t\t\t    {result}", "",
              "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(lines)


def model_files(manifest):
    parent = f"{MODEL}/definition"
    tables = sorted(Path(filename).stem for filename in manifest["tables"])
    model = ("model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
             "\tsourceQueryCulture: en-US\n\tvalueFilterBehavior: independent\n\tdiscourageImplicitMeasures\n\n"
             'annotation PBI_ProTooling = ["DevMode"]\n\nannotation __PBI_TimeIntelligenceEnabled = 0\n\n'
             f'annotation PBI_QueryOrder = {json.dumps(["P003CsvFolder", *tables])}\n\n'
             + "\n".join(f"ref table {name}" for name in tables) + "\n")
    source = (f'expression P003CsvFolder = "{CSV_FOLDER_PLACEHOLDER}" meta '
              '[IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n\n'
              '\tannotation PBI_ResultType = Text\n')
    files = {f"{parent}/database.tmdl": "database\n\tcompatibilityLevel: 1606\n",
             f"{parent}/model.tmdl": model, f"{parent}/expressions.tmdl": source}
    files.update({f"{parent}/tables/{Path(filename).stem}.tmdl": table_tmdl(Path(filename).stem, spec)
                  for filename, spec in manifest["tables"].items()})
    return files


def report_files():
    def schema(path):
        return f"{SCHEMA_BASE}/item/report/definition/{path}/schema.json"

    page = executive_page.PAGE
    navy, teal, gold, coral, slate, pearl = PALETTE
    theme = {"name": "Midnight & Emerald", "dataColors": [teal, navy, slate, gold, coral],
             "background": pearl, "foreground": navy, "tableAccent": teal,
             "good": teal, "neutral": gold, "bad": coral}
    return {
        PBIP: {"$schema": f"{SCHEMA_BASE}/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
               "artifacts": [{"report": {"path": REPORT}}], "settings": {"enableAutoRecovery": True}},
        f"{REPORT}/definition.pbir": {"$schema": f"{SCHEMA_BASE}/item/report/definitionProperties/2.0.0/schema.json",
                                      "version": "4.0", "datasetReference": {"byPath": {"path": f"../{MODEL}"}}},
        f"{MODEL}/definition.pbism": {
            "$schema": f"{SCHEMA_BASE}/item/semanticModel/definitionProperties/1.0.0/schema.json",
            "version": "4.2", "settings": {}},
        f"{REPORT}/definition/version.json": {"$schema": schema("versionMetadata/1.0.0"), "version": "2.0.0"},
        f"{REPORT}/definition/report.json": {
            "$schema": schema("report/3.3.0"),
            "themeCollection": {"customTheme": {"name": THEME_NAME,
                                "reportVersionAtImport": {"visual": "2.9.0", "report": "3.3.0", "page": "2.1.0"},
                                "type": "RegisteredResources"}},
            "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                                  "items": [{"name": THEME_NAME, "path": f"{THEME_NAME}.json",
                                             "type": "CustomTheme"}]}]},
        f"{REPORT}/definition/pages/pages.json": {"$schema": schema("pagesMetadata/1.1.0"), "pageOrder": [page],
                                                 "activePageName": page},
        f"{REPORT}/definition/pages/{page}/page.json": {"$schema": schema("page/2.1.0"),
                    "name": page, "displayName": "Executive Performance", "displayOption": "FitToPage",
                    "width": 1920, "height": 1080},
        f"{REPORT}/StaticResources/RegisteredResources/{THEME_NAME}.json": theme,
    }


def definition_files(manifest):
    report = report_files()
    page = f"{REPORT}/definition/pages/{executive_page.PAGE}/page.json"
    report.update(executive_page.page_documents(REPORT, report[page]))
    report.update(channel_page.page_documents(REPORT, report[page]))
    report[f"{REPORT}/definition/pages/pages.json"]["pageOrder"].append(channel_page.PAGE)
    entities = report[f"{REPORT}/definition/reportExtensions.json"]["entities"]
    for table, measures_ in channel_page.report_measures().items():
        entity = next((item for item in entities if item["name"] == table), None)
        if entity is None:
            entities.append({"name": table, "measures": measures_})
        else:
            entity["measures"].extend(measures_)
    return {**model_files(manifest), **{path: dump(doc) for path, doc in report.items()}}


def validate_model_bindings(root, manifest):
    definition = root / MODEL / "definition"
    settings = (definition / "model.tmdl").read_text(encoding="utf-8")
    refs = re.findall(r"^ref table (\w+)$", settings, flags=re.MULTILINE)
    require(sorted(refs) == sorted(COUNTS), "Model table reference mismatch")
    require(not (definition / "relationships.tmdl").exists(), "Overlapping aggregates must be disconnected")
    expression = (definition / "expressions.tmdl").read_text(encoding="utf-8")
    path = re.search(r'^expression P003CsvFolder = "([^"]+)" meta ', expression)
    require(path is not None, "Missing Power Query folder parameter")
    require(path[1] == CSV_FOLDER_PLACEHOLDER, "Expected the portable Power Query folder placeholder")
    for filename, spec in manifest["tables"].items():
        name = Path(filename).stem
        table = (definition / "tables" / f"{name}.tmdl").read_text(encoding="utf-8")
        declared = re.findall(
            r"^\tcolumn (\w+)\n\t\tdataType: (\w+)\n\t\tlineageTag: [0-9a-f-]+"
            r"\n\t\tsummarizeBy: none\n\t\tsourceColumn: (\w+)$", table, re.MULTILINE)
        expected = [(column["name"], TYPES[column["type"]][0], column["name"])
                    for column in spec["columns"]]
        if name == "comparison_weights":
            expected.extend([
                ("calendar_month_label", "string", "calendar_month_label"),
                ("calendar_month_order", "int64", "calendar_month_order"),
            ])
        require(declared == expected, f"Model column bindings differ: {name}")
        if name == "comparison_weights":
            require(re.search(
                        r"(?m)^\tcolumn calendar_month_label\n\t{2}dataType: string\n"
                        r"\t{2}lineageTag: [0-9a-f-]+\n\t{2}summarizeBy: none\n"
                        r"\t{2}sourceColumn: calendar_month_label\n"
                        r"\t{2}sortByColumn: calendar_month_order$",
                        table,
                    ) is not None,
                    "Calendar month display label must be imported and sorted by the numeric key")
            require(re.findall(r"^\t*column calendar_month_order[^\n]*$", table, re.MULTILINE) ==
                    ["\tcolumn calendar_month_order"],
                    "Calendar month sort key must be an imported column")
            require(
                'WithMonthOrder = Table.AddColumn(Verified, "calendar_month_order", ' in table
                and 'MonthLabels = [mar = "Mar", apr = "Apr", may = "May", jun = "Jun", ' in table
                and 'WithMonthLabel = Table.AddColumn(WithMonthOrder, "calendar_month_label", ' in table
                and "WithMonthLabel" in table,
                "Calendar month display label and sort key are missing from the M partition output",
            )
        m_source = re.search(r'File.Contents\(P003CsvFolder & "\\([^"]+)"\)', table)
        require(m_source is not None and m_source[1] == filename and (root / DATA / filename).is_file(),
                f"M partition source differs: {name}")
        m_columns = re.findall(r'\{"(\w+)", (type \w+|Int64\.Type)\}', table)
        require(m_columns == [(column["name"], TYPES[column["type"]][1]) for column in spec["columns"]],
                f"M type bindings differ: {name}")
        for source, field in re.findall(r"\b(\w+)\[(\w+)\]", table):
            require(source == name and field in {column["name"] for column in spec["columns"]},
                    f"Unresolved DAX column reference: {source}[{field}]")


def validate(root=ROOT, *, private=True):
    manifest = validate_bundle(root / DATA, private=private)
    generated = definition_files(manifest)
    actual = {path.relative_to(root).as_posix() for folder in (root / REPORT, root / MODEL)
              for path in files_under(folder)}
    actual.add(PBIP)
    require(actual == set(generated), "PBIP inventory differs from the generated P003 project")
    schemas = load(ROOT / "tools/microsoft-schemas.json")
    registry = Registry().with_resources((uri, DRAFT7.create_resource(schema)) for uri, schema in schemas.items())
    checked = 0
    for path in generated:
        file = root / path
        require(not file.is_symlink() and file.read_bytes() == generated[path].encode("utf-8"),
                f"Definition differs from generated P003 foundation: {path}")
        if not path.endswith(".tmdl"):
            doc = load(file)
            if "$schema" in doc:
                Draft7Validator(schemas[doc["$schema"]], registry=registry).validate(doc)
                checked += 1
    validate_model_bindings(root, manifest)
    validate_report(root, manifest)
    return checked


def validate_report(root, manifest):
    report = root / REPORT / "definition"
    page_ids = [executive_page.PAGE, channel_page.PAGE]
    page_order = load(report / "pages" / "pages.json")
    require(page_order["pageOrder"] == page_ids and page_order["activePageName"] == page_ids[0],
            "Unexpected page order or active page")
    theme = load(report / "report.json")["themeCollection"]["customTheme"]
    assets = load(report / "report.json")["resourcePackages"]
    items = [item for package in assets if package["type"] == "RegisteredResources"
             for item in package["items"] if item["name"] == theme["name"]]
    require(len(items) == 1, "Theme reference is unresolved")
    colors = load(root / REPORT / "StaticResources" / "RegisteredResources" / items[0]["path"])
    require(set(PALETTE) <= {colors["background"], colors["foreground"], *colors["dataColors"]},
            "Missing approved theme colors")

    extension = load(report / "reportExtensions.json")
    extension_measures = {(entity["name"], row["name"]): row["expression"]
                          for entity in extension["entities"] for row in entity["measures"]}
    columns = {Path(filename).stem: {entry["name"] for entry in table["columns"]}
               for filename, table in manifest["tables"].items()}
    columns["comparison_weights"].add("calendar_month_label")
    model = root / MODEL / "definition" / "tables"
    model_measures = {table: set(re.findall(r"^\tmeasure '([^']+)' =", (model / f"{table}.tmdl")
                                           .read_text(encoding="utf-8"), flags=re.MULTILINE))
                      for table in columns}
    for (table, name), expression in extension_measures.items():
        refs = re.findall(r"'(\w+)'\[(\w+)\]", expression)
        require(refs and all(entity == table and column in columns[table] for entity, column in refs),
                f"Unsafe or unresolved report DAX references: {name}")
    seen = set(page_ids)
    for page_id in page_ids:
        page_folder = report / "pages" / page_id
        page = load(page_folder / "page.json")
        require(page["name"] == page_id and (page["width"], page["height"]) == (1920, 1080),
                f"Page identifier or canvas differs: {page_id}")
        docs = []
        for path in sorted((page_folder / "visuals").glob("*/visual.json")):
            doc = load(path)
            require(doc["name"] == path.parent.name and doc["name"] not in seen,
                    f"Duplicate or mismatched visual identifier: {path}")
            seen.add(doc["name"])
            docs.append(doc)
        require(len(docs) == 10, f"Visual inventory differs: {page_id}")
        errors = executive_page.bounding_errors(page, docs)
        require(not errors, "; ".join(errors))
        validate_visual_bindings(page, docs, columns, model_measures, extension_measures)


def validate_visual_bindings(page, docs, columns, model_measures, extension_measures):
    chart_tables = {}
    for doc in docs:
        query = doc["visual"].get("query")
        if query is None:
            continue
        projections = [column for role in query["queryState"].values() for column in role["projections"]]
        bound = set()
        for projection in projections:
            kind, binding = next(iter(projection["field"].items()))
            reference = binding["Expression"]["SourceRef"]
            entity, name = reference["Entity"], binding["Property"]
            bound.add(entity)
            valid = (name in columns[entity] if kind == "Column" else
                     (entity, name) in extension_measures if reference.get("Schema") == "extension"
                     else name in model_measures[entity])
            require(valid and projection["queryRef"] == f"{entity}.{name}", f"Unresolved projection: {projection}")
        require(len(bound) == 1, "A single visual crosses aggregate tables")
        if "sortDefinition" in query:
            require(all(sort["field"] in [column["field"] for column in projections]
                        for sort in query["sortDefinition"]["sort"]), "Sort is not bound to a projection")
            table, = bound
            chart_tables[doc["name"]] = table
            if table == "observed_segments":
                fixed = doc["filterConfig"]["filters"]
                require(len(fixed) == 1 and fixed[0]["field"]["Column"]["Property"] == "dimension" and
                        fixed[0]["filter"]["Where"][0]["Condition"]["In"]["Values"] ==
                        [[{"Literal": {"Value": "'contact'"}}]], "Channel chart lost its grain filter")
    data = {d["name"] for d in docs if "query" in d["visual"]}
    interactions = {(item["source"], item["target"], item["type"]) for item in page["visualInteractions"]}
    require(interactions == {(source, target, "NoFilter") for source in chart_tables for target in data
                             if source != target}, "Page interactions differ")


def install_bundle(root, manifest):
    destination = root / DATA
    check_path(destination)
    if destination.exists():
        validate_bundle(destination)
    staging_name = ".p003-csv-stage"
    staging_path = root / staging_name
    check_path(staging_path)
    if destination.exists() and not staging_path.exists():
        return
    names = {"manifest.json", *manifest["tables"]}
    with scratch_directory(root, staging_name, names.__contains__) as target:
        if destination.exists():
            return
        require(target.stat().st_mode & 0o077 == 0, "CSV staging directory must be private")
        for file in sorted(names):
            with (SOURCE_BUNDLE / file).open("rb") as source, \
                    os.fdopen(os.open(target / file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as staged:
                shutil.copyfileobj(source, staged)
                staged.flush()
                os.fsync(staged.fileno())
        validate_bundle(target)
        fsync_directory(target)
        check_path(destination)
        require(not destination.exists(), "Private CSV directory appeared during build")
        target.rename(destination)
        fsync_directory(root)


def build(root=ROOT):
    root = root.absolute()
    manifest = validate_bundle(SOURCE_BUNDLE)
    files = definition_files(manifest)
    page = f"{REPORT}/definition/pages/{executive_page.PAGE}/page.json"
    old_page = dump(report_files()[page]).encode("utf-8")
    # Exact current generated definitions authorized for the Page 2 refinements.
    approved_previous = {
        f"{REPORT}/definition/pages/pages.json":
            "746036d7a4142cfe3f0c9e74148abe389ef8649b98340db27234c9330ca1f20c",
        f"{REPORT}/definition/reportExtensions.json":
            "1b0bf3a9d36f25f62583de52d587732827121ccd92e7fb06e36ee66c8825d993",
        f"{REPORT}/definition/pages/{executive_page.PAGE}/visuals/{executive_page.identity('prior-rate')}/visual.json":
            "2a88725f94bd4973a81bbff42a0c737f1e145f2645cfbe33b7be412a4d69812e",
        f"{MODEL}/definition/tables/comparison_weights.tmdl": (
            "2a6f41311997085c6fccc591cfec3499f5627f1131614c98d922a2f334d97f05",
            "1d1660a3c9d83dcc3e3744a5271cbbdfd782e2e6ba1ca691b597a6aa00c7cfe5",
            "1c5dd5ebbb7bb47e0b3a0dfda05c8a8d79e8bd5fbe710148cb8fdd272f0a4a81",
            "eff9812a1220c4fda980c80f17c18c02fd13c7e3fee80627154496d2d457f610",
        ),
        f"{REPORT}/definition/reportExtensions.json": (
            "d4195866e19701e9bb16709ba68e98f2885ca2bd855352313a575b711751c9e4",
            "1b0bf3a9d36f25f62583de52d587732827121ccd92e7fb06e36ee66c8825d993",
        ),
        f"{REPORT}/definition/pages/{channel_page.PAGE}/visuals/{executive_page.identity('channel-performance-months')}/visual.json":
            ("0e3f229cc1e47a953515a300a43326a9cc84b045e14adf4a665c447cf7767280",
             "9fe01e4b7721c62b137303523b44f5df3cf8520482650f450941dfd117cc6517"),
        f"{REPORT}/definition/pages/{channel_page.PAGE}/visuals/{executive_page.identity('channel-performance-interpretation')}/visual.json": (
            "219822616c4bb97eb4a1e6e0331b6aee018f6e6e6b413caf405e4df38df73b75",
            "8b870382e5c8cf133f7a3fb3bbe242d8347ce0cd05fa1836ca1db66b2b255f9f",
        ),
        f"{REPORT}/definition/pages/{channel_page.PAGE}/visuals/{executive_page.identity('channel-performance-december')}/visual.json":
            ("0563fdd00382a7bbadd5dfdf56f1579921d25d6118b15a793fcb3fe20cfd6b61",
             "d37ea9118233aee271f52109e9fdb09506b5dc36b631d5592589005272f7e5d8"),
    }
    with staging_area(root, ".p003-build-stage") as stage:
        changes = []
        # Preflight every definition before installing data or changing the page.
        for rel, contents in files.items():
            path = root / rel
            payload = contents.encode("utf-8")
            actual = read_existing(path)
            prior = approved_previous.get(rel)
            approved = rel in approved_previous and actual is not None and (
                hashlib.sha256(actual).hexdigest() in (prior if isinstance(prior, tuple) else (prior,))
            )
            require(actual in (None, payload) or approved or (rel == page and actual == old_page),
                    f"Existing definition differs: {rel}")
            if actual != payload:
                changes.append((path, payload, actual))
        install_bundle(root, manifest)
        for path, payload, actual in changes:
            mkdir_durable(path.parent)
            atomic_write(path, payload, expected=actual, stage=stage)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "validate"))
    args = parser.parse_args()
    try:
        if args.command == "build":
            build()
        print(f"Validated 12 tables, 383 rows, {validate()} Microsoft-schema documents and generated TMDL/M bindings.")
    except (ValueError, OSError) as error:
        raise SystemExit(f"Stopped: {error}")
