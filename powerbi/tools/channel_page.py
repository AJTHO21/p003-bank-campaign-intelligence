"""Native PBIR definitions for the P003 channel and campaign performance page."""
import executive_page as ui

PAGE = ui.identity("channel-performance-page")
TITLE = "Channel & Campaign Performance"
CROSS = "observed_cross_tabs"
FREQUENCY = "campaign_frequency"
WEIGHTS = "comparison_weights"
COMPARISON = ui.COMPARISON
PRIOR_GAP = "Channel prior-outcome-standardized gap"
MONTH_GAP = "Channel calendar-month-standardized gap"
CELLULAR_RATE = "Channel month cellular observed rate"
TELEPHONE_RATE = "Channel month telephone observed rate"
CELLULAR_N = "Channel month cellular observations"
TELEPHONE_N = "Channel month telephone observations"
DECEMBER_N = "Channel excluded December observations"
CROSS_N = "Channel stratum observations"
CROSS_Y = "Channel stratum subscriptions"
FREQUENCY_N = "Campaign frequency observations"
FREQUENCY_Y = "Campaign frequency subscriptions"
FREQUENCY_LIMIT = 15
GAP_FORMAT = '+0.00" pp";-0.00" pp";0.00" pp"'


def report_measures():
    def measure(name, expression, format_string, data_type="Double"):
        return {"name": name, "dataType": data_type, "expression": expression,
                "formatString": format_string, "hidden": True}

    def comparison(name, method):
        return measure(name, (
            f"CALCULATE(IF(COUNTROWS('{COMPARISON}') = 1, SELECTEDVALUE('{COMPARISON}'[gap_pp])), "
            f"KEEPFILTERS('{COMPARISON}'[family] = \"channel\"), "
            f"KEEPFILTERS('{COMPARISON}'[method] = \"{method}\"), "
            f"KEEPFILTERS('{COMPARISON}'[estimate_type] = \"standardized\"))"
        ), GAP_FORMAT)

    def count(name, table, column):
        return measure(name, f"SUM('{table}'[{column}])", "#,0", "Integer")

    def monthly(name, column, *, excluded=False):
        filters = (
            f'KEEPFILTERS(\'{WEIGHTS}\'[family] = "channel"), '
            f'KEEPFILTERS(\'{WEIGHTS}\'[method] = "contact_month"), '
            f"KEEPFILTERS('{WEIGHTS}'[included] = {'FALSE' if excluded else 'TRUE'}())"
        )
        if excluded:
            filters += f', KEEPFILTERS(\'{WEIGHTS}\'[stratum] = "dec")'
        rate = column.endswith("_rate")
        return measure(name, (
            f"CALCULATE(IF(COUNTROWS('{WEIGHTS}') = 1, SELECTEDVALUE('{WEIGHTS}'[{column}])), {filters})"
        ), "0.00%" if rate else "#,0", "Double" if rate else "Integer")

    return {
        COMPARISON: [comparison(PRIOR_GAP, "prior_outcome"), comparison(MONTH_GAP, "contact_month")],
        CROSS: [count(CROSS_N, CROSS, "denominator"), count(CROSS_Y, CROSS, "numerator")],
        FREQUENCY: [count(FREQUENCY_N, FREQUENCY, "denominator"),
                    count(FREQUENCY_Y, FREQUENCY, "numerator")],
        WEIGHTS: [monthly(CELLULAR_RATE, "a_rate"), monthly(TELEPHONE_RATE, "b_rate"),
                  monthly(CELLULAR_N, "a_n"), monthly(TELEPHONE_N, "b_n"),
                  measure(DECEMBER_N, (
                      f"CALCULATE(SUM('{WEIGHTS}'[a_n]) + SUM('{WEIGHTS}'[b_n]), "
                      f"KEEPFILTERS('{WEIGHTS}'[family] = \"channel\"), "
                      f"KEEPFILTERS('{WEIGHTS}'[method] = \"contact_month\"), "
                      f"KEEPFILTERS('{WEIGHTS}'[included] = FALSE()), "
                      f"KEEPFILTERS('{WEIGHTS}'[stratum] = \"dec\"))"
                  ), "#,0", "Integer")],
    }


def fixed_filters(label, table, **columns):
    return {"filters": [{
        "name": ui.identity(f"{label}-{column}-filter"),
        "type": "Categorical",
        "field": ui.field(table, column),
        "filter": {
            "Version": 2,
            "From": [{"Name": "s", "Entity": table, "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "s"}},
                                            "Property": column}}],
                "Values": [[{"Literal": {"Value": value}}] for value in values],
            }}}],
        },
    } for column, values in columns.items()]}


def extension(table, name):
    return ui.field(table, name, measure=True, extension=True)


def chart(label, index, bounds, category, rate, tooltip, title, subtitle, end, *,
          filters=None, series=None, second_rate=None, ink=ui.TEAL, labels=False):
    doc = ui.chart(label, index, bounds, category, rate,
                   "Cellular" if second_rate else "Subscription rate",
                   tooltip, title, subtitle, ink, percentage=True, end=end)
    visual = doc["visual"]
    query = visual["query"]
    query["sortDefinition"]["sort"] = [{"field": category, "direction": "Ascending"}]
    query["queryState"]["Category"]["projections"][0]["displayName"] = {
        "level": "Channel", "stratum": "Comparison group", "calendar_month_label": "Calendar month", "campaign": "Campaign contacts",
    }[category["Column"]["Property"]]
    if filters is not None:
        doc["filterConfig"] = filters
    for fixed in doc.get("filterConfig", {}).get("filters", []):
        fixed.update(isLockedInViewMode=True, isHiddenInViewMode=True)
    if series:
        query["queryState"]["Series"] = {"projections": [ui.project(series, "Channel", active=True)]}
    if second_rate:
        query["queryState"]["Y"]["projections"].append(ui.project(second_rate, "Telephone"))
    if series or second_rate:
        visual["objects"]["legend"] = ui.props(show=ui.literal("true"), position=ui.literal("'Top'"),
                                                showTitle=ui.literal("false"), fontSize=ui.literal("12D"),
                                                labelColor=ui.color(ui.NAVY))
        visual["objects"].pop("dataPoint")
    visual["objects"]["labels"][0]["properties"]["show"] = ui.literal("true" if labels else "false")
    return doc


def visuals():
    return [
        ui.text("channel-performance-header", 1, (48, 36, 1824, 124), (
            (TITLE, 46, ui.WHITE, True),
            ("Term-deposit subscriptions by contact channel, prior outcome, month and contact frequency",
             22, ui.GOLD),
        ), ui.NAVY),
        ui.card("channel-performance-observed", 2, (48, 184, 592, 124), extension(COMPARISON, ui.GAP),
                "Observed channel gap", accent=ui.TEAL, decimals=2),
        ui.card("channel-performance-prior", 3, (664, 184, 592, 124), extension(COMPARISON, PRIOR_GAP),
                "Prior-outcome-standardized gap", decimals=2),
        ui.card("channel-performance-month", 4, (1280, 184, 592, 124), extension(COMPARISON, MONTH_GAP),
                "Calendar-month-standardized gap", decimals=2),
        chart("channel-performance-rates", 5, (48, 332, 900, 264),
              ui.field(ui.SEGMENTS, "level"), ui.field(ui.SEGMENTS, "observed_segments observed rate", measure=True),
              [(extension(ui.SEGMENTS, ui.CHANNEL_Y), "Subscriptions"),
               (extension(ui.SEGMENTS, ui.CHANNEL_N), "Observations")],
              "Observed subscription rate by channel", "Hover for subscriptions and campaign observations",
              "0.22D", labels=True),
        chart("channel-performance-outcomes", 6, (972, 332, 900, 264),
              ui.field(CROSS, "stratum"), ui.field(CROSS, "observed_cross_tabs observed rate", measure=True),
              [(extension(CROSS, CROSS_Y), "Subscriptions"), (extension(CROSS, CROSS_N), "Observations")],
              "Observed rates by previous campaign outcome", "Nonexistent means no recorded prior outcome",
              "0.85D", series=ui.field(CROSS, "level"), labels=True,
              filters=fixed_filters("channel-performance-outcomes", CROSS,
                                    dimension=("'contact'",), stratum_type=("'prior_outcome'",))),
        chart("channel-performance-months", 7, (48, 620, 900, 276),
              ui.field(WEIGHTS, "calendar_month_label"), extension(WEIGHTS, CELLULAR_RATE),
              [(extension(WEIGHTS, CELLULAR_N), "Cellular observations"),
               (extension(WEIGHTS, TELEPHONE_N), "Telephone observations")],
              "Observed rates in supported calendar months",
              "Months pooled across years · chronological order · hover for both sample sizes",
              "0.65D", second_rate=extension(WEIGHTS, TELEPHONE_RATE),
              filters=fixed_filters("channel-performance-months", WEIGHTS,
                                    family=("'channel'",), method=("'contact_month'",), included=("true",))),
        chart("channel-performance-frequency", 8, (972, 620, 900, 276),
              ui.field(FREQUENCY, "campaign"), ui.field(FREQUENCY, "campaign_frequency observed rate", measure=True),
              [(extension(FREQUENCY, FREQUENCY_Y), "Subscriptions"),
               (extension(FREQUENCY, FREQUENCY_N), "Observations")],
              "Observed rates by campaign contact count", "Counts 1–15 shown · hover for the number of observations",
              "0.16D", ink=ui.SLATE,
              filters=fixed_filters("channel-performance-frequency", FREQUENCY,
                                    campaign=tuple(f"{n}L" for n in range(1, FREQUENCY_LIMIT + 1)))),
        ui.text("channel-performance-interpretation", 9, (48, 920, 1362, 124), (
            ("How to read the channel gaps", 24, ui.NAVY, True),
            ("The gaps compare cellular minus telephone. Standardized gaps apply shared prior-outcome or supported-month mixes.", 17, ui.NAVY),
            ("December is excluded from month standardization for both channels: 149 cellular + 33 telephone = 182 observations.", 17, ui.NAVY),
            ("These historical comparisons are descriptive and do not establish causal effects.", 17, ui.NAVY),
        ), ui.WHITE),
        ui.card("channel-performance-december", 10, (1434, 920, 438, 124), extension(WEIGHTS, DECEMBER_N),
                "December excluded (both channels)"),
    ]


def page_documents(report, executive):
    folder = f"{report}/definition/pages/{PAGE}"
    docs = visuals()
    charts = [doc["name"] for doc in docs if doc["visual"]["visualType"] == "clusteredColumnChart"]
    data = [doc["name"] for doc in docs if "query" in doc["visual"]]
    page = dict(executive, name=PAGE, displayName=TITLE, visualInteractions=[
        {"source": source, "target": target, "type": "NoFilter"}
        for source in charts for target in data if source != target
    ])
    return {f"{folder}/page.json": page,
            **{f"{folder}/visuals/{doc['name']}/visual.json": doc for doc in docs}}
