"""Deterministic native PBIR definitions for the approved P003 executive page."""
from hashlib import sha256
from itertools import combinations

PAGE = "f341cbf0ccd34750a031"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
NAVY, TEAL, GOLD, CORAL, SLATE, PEARL = (
    "#14283F", "#177F78", "#D5A34A", "#C76B63", "#71889B", "#F5F7FA"
)
WHITE = "#FFFFFF"
GAP = "Executive crude channel gap"
CHANNEL_N = "Executive channel observations"
CHANNEL_Y = "Executive channel subscriptions"
OUTCOME_N = "Executive previous outcome observations"
OUTCOME_Y = "Executive previous outcome subscriptions"
BASE = "executive_baseline"
SEGMENTS = "observed_segments"
OUTCOME = "previous_outcome"
COMPARISON = "comparison_estimates"


def identity(label):
    return sha256(f"p003-executive:{label}".encode()).hexdigest()[:20]


def literal(value):
    return {"expr": {"Literal": {"Value": value}}}


def color(value):
    return {"solid": {"color": literal(f"'{value}'")}}


def props(**values):
    return [{"properties": values}]


def font(value, size, ink, bold=False):
    return {"value": value, "textStyle": {
        "fontFamily": "Segoe UI", "fontSize": f"{size}px", "color": ink,
        **({"fontWeight": "bold"} if bold else {}),
    }}


def container(label, index, bounds, kind, **visual):
    return {
        "$schema": f"{SCHEMA}/visualContainer/2.9.0/schema.json",
        "name": identity(label),
        "position": {**dict(zip(("x", "y", "width", "height"), bounds)),
                     "z": index * 1000, "tabOrder": index * 1000},
        "visual": {"visualType": kind, **visual},
    }


def text(label, index, bounds, lines, fill=None):
    paragraphs = [{"textRuns": [font(*line)], "horizontalTextAlignment": "left"} for line in lines]
    return container(label, index, bounds, "textbox",
                     objects={"general": props(paragraphs=paragraphs)},
                     visualContainerObjects={"background": props(show=literal("true"), color=color(fill),
                                                                 transparency=literal("0D"))}
                     if fill else {"background": props(show=literal("false"))})


def field(table, property_name, *, measure=False, extension=False):
    source = {"Entity": table}
    if extension:
        source["Schema"] = "extension"
    return {"Measure" if measure else "Column": {
        "Expression": {"SourceRef": source}, "Property": property_name}}


def project(binding, caption, *, active=False):
    entry = next(iter(binding.values()))
    table = entry["Expression"]["SourceRef"]["Entity"]
    name = entry["Property"]
    return {"field": binding, "queryRef": f"{table}.{name}", "nativeQueryRef": name,
            "displayName": caption, **({"active": True} if active else {})}


def card(label, index, bounds, binding, caption, *, accent=NAVY, decimals=0):
    return container(label, index, bounds, "cardVisual",
                     query={"queryState": {"Data": {"projections": [project(binding, caption)]}}},
                     objects={
                         "value": [{"properties": {
                             "fontSize": literal("39D"), "fontColor": color(accent),
                             "labelDisplayUnits": literal("1D"), "labelPrecision": literal(f"{decimals}L"),
                         }, "selector": {"id": "default"}}],
                         "label": [{"properties": {"fontSize": literal("15D"), "fontColor": color(NAVY)},
                                    "selector": {"id": "default"}}],
                     },
                     visualContainerObjects={"background": props(show=literal("true"), color=color(WHITE),
                                                                 transparency=literal("0D"))})


def channel_filter(label):
    table = SEGMENTS
    return {"filters": [{
        "name": identity(label + "-contact-filter"), "type": "Categorical", "field": field(table, "dimension"),
        "filter": {"Version": 2, "From": [{"Name": "s", "Entity": table, "Type": 0}],
                   "Where": [{"Condition": {"In": {
                       "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "s"}},
                                                   "Property": "dimension"}}],
                       "Values": [[{"Literal": {"Value": "'contact'"}}]],
                   }}}]},
    }]}


def chart(label, index, bounds, category, value, value_label, tooltip, title, subtitle, ink,
          *, percentage, end):
    doc = container(label, index, bounds, "clusteredColumnChart",
                    query={
                        "queryState": {
                            "Category": {"projections": [project(category, "Group", active=True)]},
                            "Y": {"projections": [project(value, value_label)]},
                            "Tooltips": {"projections": [project(binding, name) for binding, name in tooltip]},
                        },
                        "sortDefinition": {"sort": [{"field": value, "direction": "Descending"}]},
                    },
                    objects={
                        "dataPoint": props(defaultColor=color(ink)),
                        "categoryAxis": props(showAxisTitle=literal("false"), fontSize=literal("13D"),
                                              labelColor=color(NAVY)),
                        "valueAxis": props(showAxisTitle=literal("false"), fontSize=literal("12D"),
                                           labelColor=color(NAVY), start=literal("0D"), end=literal(end)),
                        "labels": props(show=literal("true"), color=color(NAVY), fontSize=literal("14D"),
                                        labelDisplayUnits=literal("1D"),
                                        labelPrecision=literal("2L" if percentage else "0L"),
                                        labelPosition=literal("'OutsideEnd'")),
                        "legend": props(show=literal("false")),
                    },
                    visualContainerObjects={
                        "title": props(show=literal("true"), text=literal(f"'{title}'"),
                                       fontColor=color(NAVY), fontSize=literal("17D")),
                        "subTitle": props(show=literal("true"), text=literal(f"'{subtitle}'"),
                                          fontColor=color(NAVY), fontSize=literal("12D")),
                        "background": props(show=literal("true"), color=color(WHITE),
                                            transparency=literal("0D")),
                    })
    if category["Column"]["Expression"]["SourceRef"]["Entity"] == SEGMENTS:
        doc["filterConfig"] = channel_filter(label)
    return doc


def report_extension():
    channel_gap = (
        f"CALCULATE(IF(COUNTROWS('{COMPARISON}') = 1, SELECTEDVALUE('{COMPARISON}'[gap_pp])), "
        f"KEEPFILTERS('{COMPARISON}'[family] = \"channel\"), "
        f"KEEPFILTERS('{COMPARISON}'[method] = \"crude\"), "
        f"KEEPFILTERS('{COMPARISON}'[estimate_type] = \"observed\"))"
    )
    groups = []
    for table, names in ((SEGMENTS, (CHANNEL_N, CHANNEL_Y)), (OUTCOME, (OUTCOME_N, OUTCOME_Y))):
        measures = []
        for name, col in zip(names, ("denominator", "numerator")):
            expression = f"SUM('{table}'[{col}])"
            if table == SEGMENTS:
                expression = f'CALCULATE({expression}, KEEPFILTERS(\'{table}\'[dimension] = "contact"))'
            measures.append({"name": name, "dataType": "Integer", "expression": expression,
                             "formatString": "#,0", "hidden": True})
        groups.append({"name": table, "measures": measures})
    groups.append({"name": COMPARISON, "measures": [{
        "name": GAP, "dataType": "Double", "expression": channel_gap,
        "formatString": '+0.00" pp";-0.00" pp";0.00" pp"', "hidden": True,
    }]})
    return {"$schema": f"{SCHEMA}/reportExtension/1.0.0/schema.json", "name": "extension", "entities": groups}


def visuals(*, prior_color=GOLD):
    channel = field(SEGMENTS, "level")
    channel_rate = field(SEGMENTS, "observed_segments observed rate", measure=True)
    channel_n = field(SEGMENTS, CHANNEL_N, measure=True, extension=True)
    channel_y = field(SEGMENTS, CHANNEL_Y, measure=True, extension=True)
    previous = field(OUTCOME, "poutcome")
    previous_rate = field(OUTCOME, "previous_outcome observed rate", measure=True)
    previous_n = field(OUTCOME, OUTCOME_N, measure=True, extension=True)
    previous_y = field(OUTCOME, OUTCOME_Y, measure=True, extension=True)
    return [
        text("header", 1, (48, 36, 1824, 124), (
            ("Executive Campaign Overview", 46, WHITE, True),
            ("Term-deposit subscriptions  |  UCI Bank Marketing · May 2008–November 2010", 22, GOLD),
        ), NAVY),
        card("observations", 2, (48, 188, 438, 156), field(BASE, "Observations", measure=True),
             "Campaign observations"),
        card("subscriptions", 3, (510, 188, 438, 156), field(BASE, "Subscriptions", measure=True),
             "Recorded subscriptions"),
        card("baseline-rate", 4, (972, 188, 438, 156), field(BASE, "executive_baseline observed rate", measure=True),
             "Subscription rate", accent=TEAL, decimals=2),
        card("gap", 5, (1434, 188, 438, 156), field(COMPARISON, GAP, measure=True, extension=True),
             "Cellular vs telephone · unadjusted", accent=TEAL, decimals=2),
        chart("channel-rate", 6, (48, 376, 592, 396), channel, channel_rate, "Subscription rate",
              [(channel_y, "Subscriptions"), (channel_n, "Observations")],
              "Subscription rate by contact channel", "Cellular 26,144 · Telephone 15,044 observations",
              TEAL, percentage=True, end="0.20D"),
        chart("prior-rate", 7, (664, 376, 592, 396), previous, previous_rate, "Subscription rate",
              [(previous_y, "Subscriptions"), (previous_n, "Observations")],
              "Subscription rate by previous outcome", "Success 1,373 · Failure 4,252 · Nonexistent 35,563",
              prior_color, percentage=True, end="0.80D"),
        chart("channel-volume", 8, (1280, 376, 592, 396), channel, channel_n, "Campaign observations",
              [(channel_rate, "Subscription rate"), (channel_y, "Subscriptions")],
              "Campaign observations by channel", "Volume by realized last-contact channel",
              SLATE, percentage=False, end="32000D"),
        text("interpretation", 9, (48, 804, 1824, 166), (
            ("Executive interpretation", 29, NAVY, True),
            ("Cellular had both higher volume and a higher observed subscription rate. Previous success had the highest observed rate, across 1,373 observations.", 21, NAVY),
            ("Nonexistent means no recorded prior outcome. Observed differences do not establish causation.", 21, NAVY),
        ), WHITE),
        text("source-note", 10, (48, 1000, 1824, 44), (
            ("Source: UCI Bank Marketing  ·  Counts refer to campaign observations; repeat customers cannot be identified.", 17, NAVY),
        )),
    ]


def page_documents(report, blank):
    folder = f"{report}/definition/pages/{PAGE}"
    visuals_ = visuals()
    chart_names = [doc["name"] for doc in visuals_ if doc["visual"]["visualType"] == "clusteredColumnChart"]
    data_names = [doc["name"] for doc in visuals_ if "query" in doc["visual"]]
    page = dict(blank, displayName="Executive Campaign Overview", visualInteractions=[
        {"source": src, "target": target, "type": "NoFilter"}
        for src in chart_names for target in data_names if src != target
    ])
    return {f"{folder}/page.json": page,
            f"{report}/definition/reportExtensions.json": report_extension(),
            **{f"{folder}/visuals/{doc['name']}/visual.json": doc for doc in visuals_}}


def bounding_errors(page, visual_docs):
    errors = []
    for doc in visual_docs:
        pos = doc["position"]
        x, y, w, h = (pos[p] for p in ("x", "y", "width", "height"))
        if min(x, y) < 0 or min(w, h) <= 0 or x+w > page["width"] or y+h > page["height"]:
            errors.append(f"Out of canvas: {doc['name']}")
    for left, right in combinations(visual_docs, 2):
        a, b = left["position"], right["position"]
        if (a["x"] < b["x"]+b["width"] and b["x"] < a["x"]+a["width"] and
                a["y"] < b["y"]+b["height"] and b["y"] < a["y"]+a["height"]):
            errors.append(f"Visual overlap: {left['name']} / {right['name']}")
    return errors
