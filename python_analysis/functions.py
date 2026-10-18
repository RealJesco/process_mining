import hashlib
import inspect
import multiprocessing as mp
import pickle
import re
from functools import reduce
from pathlib import Path

import pandas as pd
import pm4py
from pm4py.objects.petri_net.utils.check_soundness import check_easy_soundness_net_in_fin_marking

try:
    from IPython.display import display
except ImportError:
    display = print

##Reading
def read_log(path : str):
    return pm4py.read_xes(path)
def show_trace_rows(log, trace_ids, cols, extra_cols=None):
    if extra_cols is None:
        extra_cols = []

    fields = ["case:id"] + list(extra_cols) + list(cols)
    fields = list(dict.fromkeys(fields))

    if trace_ids is None or len(trace_ids) == 0:
        return log.iloc[0:0][fields]

    return (
        log[log["case:id"].isin(trace_ids)][fields]
        .drop_duplicates()
        .reset_index(drop=True)
    )
#Exploration
def distinct_trace_values(logs, columns, sort=True, include_trace_ids=False):
    """Return unique value combinations across one or more columns.

    Parameters
    ----------
    logs : dict[str, pd.DataFrame] | pd.DataFrame
        Either a dict of named logs or a single pandas DataFrame.
    columns : str | list[str]
        One or several column names to aggregate on.
    sort : bool, default=True
        Sort rows by descending trace frequency.
    include_trace_ids : bool, default=False
        If True, add a `trace_ids` column containing a list of the trace IDs
        belonging to each aggregated value combination.

    Returns
    -------
    pd.DataFrame
        A DataFrame with the selected columns and a `traces` count column.
        If a dict is passed, an additional `log` column is included.
        If include_trace_ids=True and the log contains a `case:id` column,
        the result also contains a `trace_ids` list column.
    """
    if isinstance(columns, str):
        columns = [columns]

    if not columns:
        raise ValueError("At least one column name must be provided.")

    def _trace_id_list(series):
        values = pd.Series(series).dropna().astype(str).unique().tolist()
        return sorted(values)

    if isinstance(logs, dict):
        frames = []
        for log_name, log in logs.items():
            if not isinstance(log, pd.DataFrame):
                raise TypeError(f"log '{log_name}' is not a pandas DataFrame.")

            missing = [col for col in columns if col not in log.columns]
            if missing:
                raise KeyError(f"Missing column(s) in log '{log_name}': {missing}")

            if include_trace_ids and "case:id" not in log.columns:
                raise KeyError(f"Missing 'case:id' column in log '{log_name}' required for include_trace_ids=True.")

            group_keys = columns + ["log"]
            if include_trace_ids:
                grouped = (
                    log.loc[:, columns + ["case:id"]]
                    .copy()
                    .assign(log=log_name)
                    .groupby(group_keys, dropna=False, as_index=False)
                    .agg(
                        traces=("case:id", "size"),
                        trace_ids=("case:id", _trace_id_list),
                    )
                )
            else:
                grouped = (
                    log.loc[:, columns]
                    .copy()
                    .assign(log=log_name)
                    .groupby(group_keys, dropna=False)
                    .size()
                    .reset_index(name="traces")
                )
            frames.append(grouped)

        result = pd.concat(frames, ignore_index=True)
        if sort:
            result = result.sort_values(["log", "traces"], ascending=[True, False], ignore_index=True)
        return result

    if isinstance(logs, pd.DataFrame):
        missing = [col for col in columns if col not in logs.columns]
        if missing:
            raise KeyError(f"Missing column(s): {missing}")

        if include_trace_ids and "case:id" not in logs.columns:
            raise KeyError("Missing 'case:id' column required for include_trace_ids=True.")

        if include_trace_ids:
            grouped = (
                logs.loc[:, columns + ["case:id"]]
                .groupby(columns, dropna=False, as_index=False)
                .agg(
                    traces=("case:id", "size"),
                    trace_ids=("case:id", _trace_id_list),
                )
            )
        else:
            grouped = (
                logs.loc[:, columns]
                .groupby(columns, dropna=False)
                .size()
                .reset_index(name="traces")
            )

        result = grouped
        if sort:
            result = result.sort_values("traces", ascending=False, ignore_index=True)
        return result

    raise TypeError("logs must be a dict[str, pd.DataFrame] or a pandas DataFrame.")


def distinct_values(logs, columns, sort=True, include_trace_ids=False):
    """Alias for distinct_trace_values for a nicer naming in notebooks."""
    return distinct_trace_values(logs, columns, sort=sort, include_trace_ids=include_trace_ids)

def unique_analysis(log, cols):
    traces = log.drop_duplicates("case:id")[["case:id"] + cols]
    display(distinct_values(log, cols).head())

    equal = traces[cols].nunique(axis=1, dropna=False).eq(1)
    print(equal.value_counts())

    display(traces[~equal].reset_index(drop=True))
    return traces[~equal].reset_index(drop=True)["case:id"].tolist()

def basic_statistics(logs, years=range(2016, 2021), case_id="case:concept:name"):
    """Basisstatistik ungekürzter Logs; Case-Start = frühester Zeitstempel (UTC).

    Varianten sind exakte Aktivitätsfolgen inklusive Wiederholungen. Bei
    Zeitgleichheit bleibt die Eingabereihenfolge erhalten. Events werden nicht
    dedupliziert. Events je Jahr zählen die Event-Zeitstempel (UTC), unabhängig
    vom Case-Start. Angeforderte und tatsächlich vorkommende Jahre erscheinen
    auch dann, wenn ein einzelnes Log in einem Jahr keine Einträge enthält.
    """
    if not logs:
        raise ValueError("At least one event log is required.")
    start_counts = {}
    event_counts = {}
    statistics = {}
    all_years = set(years)
    for name, log in logs.items():
        events = _analysis_events(log, case_id)
        if "org:resource" not in events.columns:
            raise KeyError(f"Missing 'org:resource' column in log '{name}'.")
        if events["org:resource"].isna().any():
            raise ValueError(f"Resources must not be missing in log '{name}'.")
        cases = events.groupby(case_id, sort=False)
        starts = cases["time:timestamp"].min().dt.year.value_counts()
        start_counts[name] = starts
        event_counts[name] = events["time:timestamp"].dt.year.value_counts()
        all_years.update(event_counts[name].index)
        statistics[name] = {
            "Cases": len(cases),
            "Events": len(events),
            "Aktivitäten": events["concept:name"].nunique(),
            "Varianten (Python)": cases["concept:name"].agg(tuple).nunique(),
            "Ressourcen (org:resource)": ", ".join(sorted(events["org:resource"].unique())),
        }
    for name, values in statistics.items():
        resources = values.pop("Ressourcen (org:resource)")
        for year in sorted(all_years):
            values[f"Case-Start {year}"] = int(start_counts[name].get(year, 0))
        for year in sorted(all_years):
            values[f"Events {year}"] = int(event_counts[name].get(year, 0))
        values["Ressourcen (org:resource)"] = resources
    return pd.DataFrame(statistics).rename_axis("Kennzahl")


def field_summary(logs):
    """Je Log: welche Felder sind Event- und welche Trace-Attribute (Präfix `case:`)."""
    rows = []
    for name, log in logs.items():
        is_trace = log.columns.str.startswith("case:")
        rows.append([name, list(log.columns[~is_trace]), list(log.columns[is_trace])])
    return pd.DataFrame(rows, columns=["Log", "Eventfelder", "Tracefelder"])

def traces_without(log, pattern):
    """Trace-IDs, in denen kein `concept:name` den Teilstring `pattern` enthält (ohne Groß-/Kleinschreibung)."""
    hit = log["concept:name"].str.contains(pattern, case=False).groupby(log["case:id"]).any()
    return set(hit[~hit].index)

def format_share(x, n):
    return f"{x:.0f}/{n} [{x / n:.2%}]"

def style_shares(counts, totals):
    """Zellen als `x/n [y%]` formatieren (n je Spalte aus `totals`), fehlende Werte schwarz ausblenden."""
    formatters = {col: (lambda x, n=n: format_share(x, n)) for col, n in totals.items()}
    return counts.style \
        .format(formatters, na_rep="") \
        .highlight_null(props="background-color: black; color: black")

def trace_share(logs, col):
    """Je Log: Anteil der Traces, die einen Wert von `col` mindestens einmal enthalten."""
    counts = pd.DataFrame({
        name: log.groupby(col)["case:id"].nunique()
        for name, log in logs.items()
    }).sort_index(key=lambda idx: idx.str.lower())
    totals = {name: log["case:id"].nunique() for name, log in logs.items()}
    return style_shares(counts, totals)

def start_end(logs, exclude=()):
    """Je Log: wie oft ist welche Aktivität die erste bzw. letzte einer Trace (optional ohne `exclude`)."""
    counts, totals = {}, {}
    for name, log in logs.items():
        events = (log[~log["concept:name"].isin(exclude)]
                  .sort_values(["case:concept:name", "time:timestamp"], kind="stable"))
        per_trace = events.groupby("case:concept:name")["concept:name"]
        for position, acts in [("first", per_trace.first()), ("last", per_trace.last())]:
            counts[(name, position)] = acts.value_counts()
            totals[(name, position)] = len(acts)
    table = pd.DataFrame(counts).sort_index(key=lambda idx: idx.str.lower())
    table.index.name = "concept:name"
    table.columns.names = ["Log", "Position"]
    return style_shares(table, totals)


#Transformation

# Aktivitätsklassen: Wörter -> Äquivalenzklassen -> Masken -> exakte Überdeckungen
def activity_table(logs):
    """Je Aktivität (mit Resource und Role): Anzahl Events pro Log."""
    names = list(logs)
    return (
        pd.concat([log.assign(**{n: int(n == name) for n in names}) for name, log in logs.items()])
        .groupby(["concept:name", "org:resource", "org:role"])[names]
        .sum()
        .reset_index()
        .rename(columns={"concept:name": "concept_name", "org:resource": "resource", "org:role": "role"})
        .sort_values(["resource", "concept_name"], ignore_index=True)
        .set_index("concept_name", drop=False)
    )

def equivalence_classes(acts, fields=("concept_name", "resource", "role")):
    """Wörter mit identischer Aktivitätsmenge bilden eine Äquivalenzklasse."""
    index = {}
    for name, row in acts.iterrows():
        for w in set(re.findall(r"[A-Z_]+", " ".join(row[list(fields)]).upper())): #Wichtig den unterstrich behalten, weil sonst final_approved von approved vollabgedeckt wird
            index.setdefault(w, set()).add(name)

    classes = {}
    for w, members in sorted(index.items()):
        classes.setdefault(frozenset(members), []).append(w)

    counts = acts.select_dtypes("number").columns
    return pd.DataFrame(
        [{"words": " ".join(ws),
          "n": len(m),
          **acts.loc[list(m), counts].sum().to_dict(),
          "members": sorted(m)}
         for m, ws in classes.items()]
    ).sort_values(["n", "words"], ascending=[False, True], ignore_index=True)

def lcs(a, b):
    """Längste gemeinsame Teilfolge zweier Token-Listen (Lücken erlaubt)."""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            dp[i][j] = dp[i+1][j+1] + 1 if a[i] == b[j] else max(dp[i+1][j], dp[i][j+1])
    i = j = 0
    out = []
    while i < n and j < m:
        if a[i] == b[j]:
            out.append(a[i]); i += 1; j += 1
        elif dp[i+1][j] >= dp[i][j+1]:
            i += 1
        else:
            j += 1
    return out

def gaps(tokens, common):
    """Für jede Lücke vor/zwischen/nach den common-Tokens: steht dort etwas?"""
    g = [False] * (len(common) + 1)
    k = 0
    for t in tokens:
        if k < len(common) and t == common[k]:
            k += 1
        else:
            g[k] = True
    return g

def template(members):
    """Maske, die alle Aktivitätsnamen der Gruppe abdeckt, z. B. `% APPROVED by %`."""
    seqs = [m.split() for m in sorted(members)]
    common = reduce(lcs, seqs)
    if not common:
        return "%"
    g = [any(col) for col in zip(*(gaps(s, common) for s in seqs))]
    parts = []
    for i, tok in enumerate(common):
        if g[i]:
            parts.append("%")
        parts.append(tok)
    if g[-1]:
        parts.append("%")
    return " ".join(parts)

def exact_covers(universe, subsets):
    """Knuth's Algorithm X: liefert alle Teilmengen-Kombinationen,
    die jedes Element aus universe genau einmal abdecken."""
    X = {x: set() for x in universe}
    for key, items in subsets.items():
        for x in items:
            X[x].add(key)

    def select(r):
        cols = []
        for j in subsets[r]:
            for i in X[j]:
                for k in subsets[i]:
                    if k != j:
                        X[k].remove(i)
            cols.append(X.pop(j))
        return cols

    def deselect(r, cols):
        for j in reversed(subsets[r]):
            X[j] = cols.pop()
            for i in X[j]:
                for k in subsets[i]:
                    if k != j:
                        X[k].add(i)

    def solve(solution):
        if not X:
            yield sorted(solution)
            return
        c = min(X, key=lambda c: (len(X[c]), c))   # am schwersten abzudeckendes Element zuerst
        for r in sorted(X[c]):
            solution.append(r)
            cols = select(r)
            yield from solve(solution)
            deselect(r, cols)
            solution.pop()

    yield from solve([])

def cover_table(groups, universe):
    """Alle Kombinationen von Gruppen, die jede Aktivität aus `universe` genau einmal abdecken."""
    subsets = {i: list(m) for i, m in groups["members"].items()}
    solutions = list(exact_covers(universe, subsets))
    return pd.DataFrame({
        "n_groups": [len(s) for s in solutions],
        "groups":   [[groups.at[i, "words"] for i in s] for s in solutions],
        "ids":      solutions,
    }).sort_values("n_groups", kind="stable", ignore_index=True)

def assign_classes(acts, groups, group_ids, label="template"):
    """Ordnet jeder Aktivität das Label (`template` oder `words`) ihrer Gruppe aus der gewählten Überdeckung zu."""
    mapping = {act: groups.at[g, label]
               for g in group_ids for act in groups.at[g, "members"]}
    return acts.index.map(mapping)

# Ablauf-Repräsentation: Aktivität -> Kurzcode (Entität + Aktivität + Akteur)
ENTITY = {"Declaration": "D", "Permit": "P", "trip": "T", "Payment": "🪙", "Reminder": "📨"}
ACTIVITY = {"Start": "⬆️", "End": "⬇️", "Request": "❓", "Handled": "❗",
            "SUBMITTED": "1", "SAVED": "2", "APPROVED": "3", "FOR_APPROVAL": "4",
            "REJECTED": "5❌", "FINAL_APPROVED": "5✅"}
ACTOR = {"MISSING": "_", "UNDEFINED": "?", "EMPLOYEE": "0", "BUDGET OWNER": "1",
         "PRE_APPROVER": "2", "SUPERVISOR": "5", "ADMINISTRATION": "6", "DIRECTOR": "7"}
NO_ACTOR = {"T", "🪙", "📨"}

def event_code(name):
    action, _, actor = name.partition(" by ")
    words = action.split()
    entity = next((code for key, code in ENTITY.items() if key in words), "?")
    activity = next((code for key, code in ACTIVITY.items() if key in words), "")
    if entity in NO_ACTOR:
        return entity + activity
    return entity + activity + ACTOR.get(actor, "?")

def event_code_legend(logs):
    """Alle Aktivitäten der Logs mit ihrem Kurzcode."""
    legend = pd.Series(sorted(pd.concat(logs.values())["concept:name"].unique()), name="concept:name").to_frame()
    legend["Code"] = legend["concept:name"].map(event_code)
    return legend

def variants(log):
    """Abläufe (Kurzcodes mit ` > ` verbunden) und wie viele Traces genau so ablaufen."""
    events = log.sort_values(["case:concept:name", "time:timestamp"], kind="stable")
    paths = (events["concept:name"].map(event_code)
             .groupby(events["case:concept:name"], sort=False)
             .agg(" > ".join))
    n = len(paths)
    counts = paths.value_counts().rename_axis("Ablauf").reset_index(name="Traces")
    counts["Anteil"] = counts["Traces"].map(lambda x: format_share(x, n))
    durations = _duration_cases(events, "case:concept:name")
    durations["Ablauf"] = paths
    stats = durations.groupby("Ablauf")["duration_days"].agg(["median", "mean"])

    counts["Median (Tage)"] = counts["Ablauf"].map(stats["median"])
    counts["Durchschnitt (Tage)"] = counts["Ablauf"].map(stats["mean"])
    return counts


#Filtering


#Discovery

def as_petri_net(model):
    """Petri-Netze (net, im, fm) direkt durchreichen, andere Modelle (z. B. BPMN) für die Bewertung umwandeln."""
    return model if isinstance(model, tuple) else pm4py.convert_to_petri_net(model)

# Benannte Varianten statt partial/lambda, damit der Cache-Key (Quelltext) stabil bleibt
def discover_inductive_noise_tenth(log):
    """Inductive Miner infrequent (IMf) mit 10 % Rauschfilter."""
    return pm4py.discover_petri_net_inductive(log, noise_threshold=0.1)

def discover_inductive_noise_twentieth(log):
    """Inductive Miner infrequent (IMf) mit 0.05  Rauschfilter."""
    return pm4py.discover_petri_net_inductive(log, noise_threshold=0.05)

def discover_ilp(log):
    """ILP Miner (regionenbasiert) mit Rauschfilter alpha=0.9 (1.0 = ungefiltert, dauert bei international >15 min)."""
    return pm4py.discover_petri_net_ilp(log, alpha=0.9)

def discover_powl(log):
    """POWL-Modell (Partially Ordered Workflow Language); Bewertung über Umwandlung in ein Petri-Netz."""
    return pm4py.discover_powl(log)


#Evaluation

# Cache unter python_analysis/models: Modelle je Log + Verfahren, Kennzahlen einzeln
CACHE_DIR = Path(__file__).resolve().parent / "models"
CACHE_FIELDS = ["case:concept:name", "concept:name", "time:timestamp"]

def log_hash(log):
    """Fingerprint über die für Discovery/Replay relevanten Felder des Logs."""
    return hashlib.sha256(pd.util.hash_pandas_object(log[CACHE_FIELDS], index=False).values).hexdigest()[:16]

def code_hash(*funcs):
    """Fingerprint über den Quelltext der übergebenen Funktionen."""
    return hashlib.sha256("".join(inspect.getsource(f) for f in funcs).encode()).hexdigest()[:16]

def load(path):
    if path.exists():
        with open(path, "rb") as f:
            return pickle.load(f)

def save(path, entry):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(entry, f)

def _is_sound(net, im, fm):
    return pm4py.check_soundness(net, im, fm)[0]

def check_sound(net, im, fm, timeout=30):
    """Woflan-Soundness-Check mit Timeout; None = Abbruch nach `timeout` Sekunden."""
    with mp.get_context("fork").Pool(1) as pool:
        try:
            return pool.apply_async(_is_sound, (net, im, fm)).get(timeout)
        except mp.TimeoutError:
            return None

# Kennzahlen: Cache-Schlüssel = Quelltext der Funktion + der angegebenen Abhängigkeiten
METRICS = {}

def metric(*deps, name=None, needs=()):
    """Registriert eine Kennzahl. `deps`: genutzte Hilfsfunktionen, `needs`: zuvor berechnete Kennzahlen (in ctx["values"])."""
    def register(func):
        code = code_hash(func, *deps)
        if needs:
            code = hashlib.sha256("".join([code, *(METRICS[n][1] for n in needs)]).encode()).hexdigest()[:16]
        METRICS[name or func.__name__] = (func, code, needs)
        return func
    return register

def replay(ctx):
    """Token-Based Replay, wird pro Modell höchstens einmal berechnet."""
    if "replay" not in ctx:
        ctx["replay"] = pm4py.conformance_diagnostics_token_based_replay(ctx["log"], *ctx["model"])
    return ctx["replay"]

def tokens(ctx, kind):
    return sum(r[f"{kind}_tokens"] for r in replay(ctx))

@metric()
def places(ctx):
    return len(ctx["net"].places)

@metric()
def transitions(ctx):
    return len(ctx["net"].transitions)

@metric()
def silent_transitions(ctx):
    return sum(t.label is None for t in ctx["net"].transitions)

@metric()
def arcs(ctx):
    return len(ctx["net"].arcs)

@metric(replay)
def fitting_traces(ctx):
    fit, n = sum(r["trace_is_fit"] for r in replay(ctx)), len(replay(ctx))
    return f"{fit}/{n} [{fit / n:.2%}]"

@metric(replay)
def trace_fitness_avg(ctx):
    return sum(r["trace_fitness"] for r in replay(ctx)) / len(replay(ctx))

@metric(replay, tokens)
def log_fitness(ctx):
    return (0.5 * (1 - tokens(ctx, "missing") / tokens(ctx, "consumed"))
            + 0.5 * (1 - tokens(ctx, "remaining") / tokens(ctx, "produced")))

for kind in ("produced", "consumed", "missing", "remaining"):
    metric(replay, tokens, name=f"{kind}_tokens")(lambda ctx, kind=kind: tokens(ctx, kind))

@metric()
def precision(ctx):
    return pm4py.precision_token_based_replay(ctx["log"], *ctx["model"])

@metric()
def generalization(ctx):
    return pm4py.generalization_tbr(ctx["log"], *ctx["model"])

@metric()
def simplicity(ctx):
    return pm4py.simplicity_petri_net(*ctx["model"])

@metric()
def workflow_net(ctx):
    return pm4py.check_is_workflow_net(ctx["net"])

@metric()
def easy_sound(ctx):
    with mp.get_context("fork").Pool(1) as pool:
        try:
            return pool.apply_async(
                check_easy_soundness_net_in_fin_marking,
                ctx["model"],
            ).get(timeout=30)
        except mp.TimeoutError:
            print(
                "easy_sound: Timeout nach 30 s; Ergebnis unbekannt.",
                flush=True,
            )
            return None

@metric(check_sound, _is_sound)
def sound(ctx):
    return pm4py.check_is_workflow_net(ctx["net"]) and check_sound(*ctx["model"])

# Zusammenfassende Kennzahlen
@metric(needs=("log_fitness", "precision"))
def f1(ctx):
    """Harmonisches Mittel aus Fitness und Precision."""
    f, p = ctx["values"]["log_fitness"], ctx["values"]["precision"]
    return 2 * f * p / (f + p) if f + p else 0.0

@metric(needs=("log_fitness", "precision", "generalization", "simplicity", "easy_sound"))
def quality(ctx):
    """Gewichteter Mittelwert der vier Qualitätsdimensionen; 0, falls das Netz nicht easy sound ist."""
    weights = {"log_fitness": 2, "precision": 2, "generalization": 1, "simplicity": 1}
    v = ctx["values"]
    if v["easy_sound"] is None:
        return float("nan")
    if not v["easy_sound"]:
        return 0.0
    return sum(v[k] * w for k, w in weights.items()) / sum(weights.values())

def cached_model(path, key, discover, log):
    entry = load(path)
    if entry is not None and entry["key"] == key:
        print(f"{path.name}: aus Cache geladen")
        return entry["model"]
    print(f"{path.name}: wird neu berechnet")
    model = discover(log)
    save(path, {"key": key, "model": model})
    return model

def evaluate(path, key, log, model, force=()):
    """Berechnet nur Kennzahlen, die neu sind, deren Quelltext sich geändert hat oder die in `force` stehen."""
    entry = load(path)
    if entry is None or entry["key"] != key:
        entry = {"key": key, "metrics": {}}
    entry["metrics"] = {m: v for m, v in entry["metrics"].items() if m in METRICS}
    todo = []
    for m, (_, code, needs) in METRICS.items():
        if m in force or entry["metrics"].get(m, {}).get("code") != code or any(n in todo for n in needs):
            todo.append(m)
    if todo:
        pn = as_petri_net(model)
        values = {m: v["value"] for m, v in entry["metrics"].items()}
        ctx = {"log": log, "model": pn, "net": pn[0], "values": values}
        for m in todo:
            func, code, _ = METRICS[m]
            print(f"{path.name}: starte {m}", flush=True)
            values[m] = func(ctx)
            entry["metrics"][m] = {"code": code, "value": values[m]}
            save(path, entry)
            print(f"{path.name}: {m} fertig und gespeichert", flush=True)
    print(f"{path.name}: {len(METRICS) - len(todo)} aus Cache, neu berechnet: {', '.join(todo) or '–'}")
    return {m: entry["metrics"][m]["value"] for m in METRICS}

def discover_and_evaluate(name, miner, discover, log, force=()):
    """Modell entdecken und bewerten – beides gecacht unter `models/<name>_<miner>_{model,stats}.pkl`."""
    key = f"{log_hash(log)}-{code_hash(discover)}"
    model = cached_model(CACHE_DIR / f"{name}_{miner}_model.pkl", key, discover, log)
    return model, evaluate(CACHE_DIR / f"{name}_{miner}_stats.pkl", key, log, model, force)


#Visualization

# Richtung je Kennzahl für das Hervorheben in der Stats-Tabelle; nicht aufgeführte Zeilen bleiben neutral
HIGHER_BETTER = ["f1", "quality", "fitting_traces", "trace_fitness_avg", "log_fitness", "precision", "generalization", "simplicity"]
LOWER_BETTER = ["places", "transitions", "silent_transitions", "arcs", "missing_tokens", "remaining_tokens"]
BOOL_METRICS = ["workflow_net", "easy_sound", "sound"]

def share_value(v):
    """`x/n [y%]` -> x/n als Zahl, alles andere unverändert."""
    if isinstance(v, str) and "/" in v:
        x, n = v.split()[0].split("/")
        return int(x) / int(n)
    return v

def compare(table, metrics=("f1", "quality")):
    """Direkte Gegenüberstellung: Zeilen = (Kennzahl, Log) plus Mittelwert "Ø" je Kennzahl, Spalten = Verfahren."""
    rows = {}
    for m in metrics:
        block = table.loc[m].unstack("Verfahren").astype(float)
        block.loc["Ø"] = block.mean()
        rows[m] = block
    return pd.concat(rows, names=["Kennzahl", "Log"])

SUM_METRICS = ["places", "transitions", "silent_transitions", "arcs",
               "produced_tokens", "consumed_tokens", "missing_tokens", "remaining_tokens"]

def combine_partitions(table, logs, partitions):
    """Kennzahlen je Verfahren über Log-Aufteilungen zusammenfassen, die gemeinsam alle Traces abdecken.

    Größen/Tokens werden summiert, fitting_traces gezählt, log_fitness aus den summierten Tokens neu berechnet,
    precision nach Events und alles andere nach Traces gewichtet; Bools nur True, wenn alle Teilmodelle True sind.
    f1/quality werden mit ihrer Implementierung aus den kombinierten Werten neu berechnet.
    """
    def combine_bool(v):
        if any(x is False for x in v):
            return False
        return None if any(x is None for x in v) else True

    out = {}
    for miner in table.columns.unique("Verfahren"):
        for part, names in partitions.items():
            t = table[[(n, miner) for n in names]].set_axis(names, axis=1)
            traces = pd.Series({n: logs[n]["case:concept:name"].nunique() for n in names})
            events = pd.Series({n: len(logs[n]) for n in names})
            r = {}
            for m, v in t.iterrows():
                if m in SUM_METRICS:
                    r[m] = v.sum()
                elif m == "fitting_traces":
                    r[m] = format_share(sum(share_value(x) * traces[n] for n, x in v.items()), traces.sum())
                elif m in BOOL_METRICS:
                    r[m] = combine_bool(list(v))
                else:
                    w = events if m == "precision" else traces
                    r[m] = (v.astype(float) * w).sum() / w.sum()
            r["log_fitness"] = (0.5 * (1 - r["missing_tokens"] / r["consumed_tokens"])
                                + 0.5 * (1 - r["remaining_tokens"] / r["produced_tokens"]))
            values = {**r, "easy_sound": bool(r["easy_sound"])}
            for m in ("f1", "quality"):
                r[m] = METRICS[m][0]({"values": values})
                values[m] = r[m]
            out[(miner, part)] = r
    combined = pd.DataFrame(out).reindex(table.index)
    combined.columns.names = ["Verfahren", "Aufteilung"]
    return combined

def style_stats(table, cmap="cividis", precision=3, per_log=True):
    """Stats-Tabelle mit Farbverlauf je Zeile (hell = besser) und fett/unterstrichenem Bestwert.

    `per_log=True` vergleicht die Verfahren innerhalb eines Logs (erste Spaltenebene), sonst über alle Spalten.
    `cividis` ist auch bei Rot-Grün-Schwäche eindeutig, da es nur von Dunkelblau nach Gelb verläuft.
    """
    from matplotlib import colormaps, colors

    values = table.map(share_value)
    good, bad = (colors.to_hex(colormaps[cmap](x)) for x in (1.0, 0.0))
    idx = pd.IndexSlice
    multi = per_log and isinstance(table.columns, pd.MultiIndex)
    groups = [[c for c in table.columns if c[0] == g] for g in table.columns.unique(0)] if multi else [list(table.columns)]

    def is_missing(v):
        return v is None or (isinstance(v, float) and pd.isna(v))

    def bool_style(v):
        if is_missing(v):
            return "color: gray; font-style: italic"
        return f"background-color: {good}; color: black" if v else f"background-color: {bad}; color: white"

    def metric_name(r):
        return r[0] if isinstance(r, tuple) else r

    def best(row, higher):
        nums = pd.to_numeric(values.loc[row.name, row.index], errors="coerce")
        target = nums.max() if higher else nums.min()
        return ["font-weight: bold; text-decoration: underline" if v == target else "" for v in nums]

    styler = table.style.format(precision=precision)
    for rows, higher in ((HIGHER_BETTER, True), (LOWER_BETTER, False)):
        for r in (r for r in table.index if metric_name(r) in rows):
            for cols in groups:
                nums = pd.to_numeric(values.loc[r, cols], errors="coerce")
                if nums.nunique() < 2:
                    continue
                styler = styler.background_gradient(cmap=cmap if higher else f"{cmap}_r", axis=1,
                                                    subset=idx[[r], cols], gmap=nums.astype(float).values) \
                               .apply(best, higher=higher, axis=1, subset=idx[[r], cols])

    bools = [r for r in table.index if metric_name(r) in BOOL_METRICS]
    if bools:
        styler = styler.map(bool_style, subset=idx[bools, :]) \
                       .format(lambda v: "Timeout" if is_missing(v) else v, subset=idx[bools, :])
    if multi:
        styler = styler.set_properties(subset=idx[:, [cols[0] for cols in groups]], **{"border-left": "3px solid #888"})
    scope = f"je {table.columns.names[0] or 'Gruppe'}" if multi else "je Zeile"
    return styler.set_caption(f"hell/gelb = besser, dunkelblau = schlechter, fett + unterstrichen = Bestwert {scope}")


#Task analyses
def _analysis_events(log, case_id):
    required = [case_id, "concept:name", "time:timestamp"]
    missing = [col for col in required if col not in log.columns]
    if missing:
        raise KeyError(f"Missing analysis columns: {missing}")
    if log.empty:
        raise ValueError("Analysis requires a non-empty event log.")
    if log[required].isna().any().any():
        raise ValueError("Case IDs, activities and timestamps must not be missing.")
    events = log.copy()
    events["time:timestamp"] = pd.to_datetime(events["time:timestamp"], utc=True, errors="raise")
    if events["time:timestamp"].isna().any():
        raise ValueError("Timestamps must not be missing.")
    return events.sort_values([case_id, "time:timestamp"], kind="stable").reset_index(drop=True)

def direct_neighborhood(log, case_id="case:concept:name"):
    """Direkt beobachtete Vor- und Nachaktivitäten je Aktivitätscode."""
    events = _analysis_events(log, case_id)
    events["Code"] = events["concept:name"].map(event_code)

    traces = events.groupby(case_id, sort=False)["Code"]
    events["Vorbereich"] = traces.shift(1)
    events["Nachbereich"] = traces.shift(-1)

    return (
        events.groupby("Code")[["Vorbereich", "Nachbereich"]]
        .agg(lambda values: set(values.dropna()))
        .sort_index()
    )

def rejection_triples(log, case_id="case:concept:name"):
    """Formatierte Rejection-Triples mit Prozenten je Mittelaktivitaet.

    Nachbarn stammen aus dem uebergebenen Log, inklusive Trace-Grenzen.
    Jedes Rejection-Vorkommen zaehlt; Linien trennen Mittelaktivitaeten.
    """
    events = _analysis_events(log, case_id)
    events["Aktivitaet"] = events["concept:name"].map(event_code)
    grouped = events.groupby(case_id, sort=False)["Aktivitaet"]
    events["Voraktivitaet"] = grouped.shift(1).fillna("<Trace-Anfang>")
    events["Nachaktivitaet"] = grouped.shift(-1).fillna("<Trace-Ende>")
    rejections = events.loc[
        events["Aktivitaet"].str.startswith(("D5❌", "P5❌"))
    ]
    result = (
        rejections.groupby(["Aktivitaet", "Voraktivitaet", "Nachaktivitaet"])
        .agg(Anzahl=(case_id, "size"), Traces=(case_id, "nunique"))
        .reset_index()
    )
    result["Prozent"] = (
        100 * result["Anzahl"]
        / result.groupby("Aktivitaet")["Anzahl"].transform("sum")
    )
    result = result.sort_values(
        ["Aktivitaet", "Anzahl"], ascending=[True, False], kind="stable",
        ignore_index=True,
    )
    result["Triple"] = (
        result["Voraktivitaet"] + " → " + result["Aktivitaet"]
        + " → " + result["Nachaktivitaet"]
    )
    change = result["Aktivitaet"].ne(result["Aktivitaet"].shift())
    if not change.empty:
        change.iloc[0] = False
    columns = ["Triple", "Anzahl", "Traces", "Prozent"]
    borders = pd.DataFrame("", index=result.index, columns=columns)
    borders.loc[change, :] = "border-top: 3px solid #888;"
    return (
        result[columns].style
        .apply(lambda _: borders, axis=None)
        .hide(axis="index")
        .format({"Prozent": "{:.2f} %"}, escape="html")
    )


def rejections_without_employee_followup(log, case_id="case:concept:name"):
    """Traces und Rejections ohne direkten Employee-Rejection-Nachfolger.

    Start/End trip werden entfernt; alle anderen Events bleiben erhalten.
    D-Rejections erwarten D5❌0, P-Rejections P5❌0. Trace-Enden zaehlen
    ebenfalls als Treffer. Akteurscodes _ und ? gelten als ungleich 0.
    """
    events = _analysis_events(log, case_id)
    events = events.loc[
        ~events["concept:name"].isin({"Start trip", "End trip"})
    ].copy()
    events["Aktivitaet"] = events["concept:name"].map(event_code)
    events["Nachaktivitaet"] = (
        events.groupby(case_id, sort=False)["Aktivitaet"]
        .shift(-1).fillna("<Trace-Ende>")
    )
    events["Erwartet"] = events["Aktivitaet"].str[:1] + "5❌0"
    rejected_by_other = (
        events["Aktivitaet"].str.startswith(("D5❌", "P5❌"))
        & ~events["Aktivitaet"].isin({"D5❌0", "P5❌0"})
    )
    details = events.loc[
        rejected_by_other & events["Nachaktivitaet"].ne(events["Erwartet"]),
        [case_id, "time:timestamp", "Aktivitaet", "Nachaktivitaet", "Erwartet"],
    ].reset_index(drop=True)
    cases = details.groupby(case_id).size().to_frame("Treffer")
    return {"cases": cases, "events": details}


def _duration_cases(events, case_id):
    cases = events.groupby(case_id).agg(
        start=("time:timestamp", "min"), end=("time:timestamp", "max"),
        events=("concept:name", "size"), activities=("concept:name", "nunique"),
    )
    cases["duration_days"] = (cases["end"] - cases["start"]).dt.total_seconds() / 86400
    return cases


def _duration_summary(cases, groups=None):
    durations = cases["duration_days"] if groups is None else cases.groupby(groups, dropna=False)["duration_days"]
    result = durations.agg(["count", "mean", "median", "min", "max"])
    if groups is None:
        result = result.to_frame().T
        result.index = pd.Index(["all"], name="group")
    result["p90"] = durations.quantile(0.9)
    return result.rename(columns={"count": "cases", **{k: f"{k}_days" for k in ("mean", "median", "min", "max", "p90")}})


def _case_attributes(events, cases, columns, case_id):
    if isinstance(columns, str):
        columns = [columns]
    columns = list(columns)
    missing = [col for col in columns if col not in events.columns]
    if missing:
        raise KeyError(f"Missing case attributes: {missing}")
    if columns:
        if events.groupby(case_id)[columns].nunique(dropna=False).gt(1).any().any():
            raise ValueError("Grouping attributes must be constant within each case.")
        cases = cases.join(events.drop_duplicates(case_id).set_index(case_id)[columns])
    return cases, columns


def process_durations(log, group_by=(), case_id="case:concept:name"):
    """Frage 2: beobachtete Zeit vom ersten bis letzten Event, in Tagen.

    Keine Aussage ueber abgeschlossene Faelle oder reine Bearbeitungszeit.
    Monatsgruppen beziehen sich auf den ersten beobachteten Zeitstempel (UTC).
    """
    events = _analysis_events(log, case_id)
    cases, columns = _case_attributes(events, _duration_cases(events, case_id), group_by, case_id)
    cases["start_month"] = cases["start"].dt.strftime("%Y-%m")
    result = {
        "summary": _duration_summary(cases),
        "by_start_month": _duration_summary(cases, "start_month"),
        "cases": cases.sort_values("duration_days", ascending=False),
    }
    if columns:
        result["by_group"] = _duration_summary(cases, columns)
    return result


def bottleneck_analysis(log, min_occurrences=1, case_id="case:concept:name"):
    """Frage 3: Zeitabstaende direkt aufeinanderfolgender Events, keine Servicezeiten.

    Lange Abstaende sind Engpass-Kandidaten, kein Beleg fuer Warten oder Ursachen.
    Gesamtzeiten summieren Abstaende ueber Faelle, nicht eindeutige Kalenderzeit.
    """
    if min_occurrences < 1:
        raise ValueError("min_occurrences must be at least 1.")
    events = _analysis_events(log, case_id)
    following = events.groupby(case_id)[["concept:name", "time:timestamp"]].shift(-1)
    intervals = events[[case_id, "concept:name", "time:timestamp"]].rename(
        columns={"concept:name": "from_activity", "time:timestamp": "start"}
    )
    intervals["to_activity"] = following["concept:name"]
    intervals["end"] = following["time:timestamp"]
    intervals = intervals.loc[intervals["end"].notna()].copy()
    intervals["elapsed_days"] = (intervals["end"] - intervals["start"]).dt.total_seconds() / 86400
    summary = intervals.groupby(["from_activity", "to_activity"]).agg(
        occurrences=("elapsed_days", "size"), cases=(case_id, "nunique"),
        mean_days=("elapsed_days", "mean"), median_days=("elapsed_days", "median"),
        p90_days=("elapsed_days", lambda x: x.quantile(0.9)),
        max_days=("elapsed_days", "max"), total_days=("elapsed_days", "sum"),
    )
    summary["case_share"] = summary["cases"] / events[case_id].nunique()
    summary = summary.loc[summary["occurrences"].ge(min_occurrences)]
    return {
        "transitions": summary.sort_values(["median_days", "occurrences"], ascending=False),
        "intervals": intervals.sort_values("elapsed_days", ascending=False),
    }


def rejection_analysis(log, entity="Declaration", group_by=(), case_id="case:concept:name"):
    """Frage 4: Ablehnungen je Trace mit Events der gewaehlten Entitaet.

    'rejected' bedeutet mindestens ein REJECTED-Event, nicht endgueltige Ablehnung.
    Eine finale Freigabe nach der letzten Ablehnung wird separat ausgewiesen.
    Gruppen und ablehnende Aktivitaeten beschreiben Zusammenhaenge, keine Ursachen.
    """
    events = _analysis_events(log, case_id)
    selected = events.loc[events["concept:name"].str.startswith(f"{entity} ")].copy()
    if selected.empty:
        raise ValueError(f"No events for entity {entity!r}.")
    selected["rejected"] = selected["concept:name"].str.startswith(f"{entity} REJECTED")
    cases = selected.groupby(case_id).agg(
        rejection_events=("rejected", "sum"), last_entity_activity=("concept:name", "last"),
    )
    cases["rejected"] = cases["rejection_events"].gt(0)
    # Stable row positions distinguish repeated decisions, including timestamp ties.
    last_rejection = selected.loc[selected["rejected"]].reset_index().groupby(case_id)["index"].max()
    last_approval = selected.loc[
        selected["concept:name"].str.startswith(f"{entity} FINAL_APPROVED")
    ].reset_index().groupby(case_id)["index"].max()
    cases["final_approval_after_last_rejection"] = (
        last_approval.reindex(cases.index).gt(last_rejection.reindex(cases.index))
    )
    cases["last_entity_event_rejected"] = cases["last_entity_activity"].str.startswith(f"{entity} REJECTED")
    cases, columns = _case_attributes(events, cases, group_by, case_id)
    summary = pd.DataFrame([{
        "cases": len(cases), "rejection_events": int(cases["rejection_events"].sum()),
        "rejected_cases": int(cases["rejected"].sum()), "rejected_share": cases["rejected"].mean(),
        "final_approval_after_last_rejection": int(cases["final_approval_after_last_rejection"].sum()),
        "last_entity_event_rejected": int(cases["last_entity_event_rejected"].sum()),
    }], index=pd.Index([entity], name="entity"))
    by_activity = selected.loc[selected["rejected"]].groupby("concept:name").agg(
        rejection_events=(case_id, "size"), rejected_cases=(case_id, "nunique"),
    )
    by_activity["case_share"] = by_activity["rejected_cases"] / len(cases)
    result = {"summary": summary, "by_activity": by_activity, "cases": cases}
    if columns:
        result["by_group"] = cases.groupby(columns, dropna=False).agg(
            cases=("rejected", "size"), rejected_cases=("rejected", "sum"),
            rejected_share=("rejected", "mean"),
        ).sort_values("cases", ascending=False)
    return result


def unexpected_behavior(log, rules, case_id="case:concept:name"):
    """Frage 5: explizite Praezedenzregeln auf vollstaendigen Traces pruefen.

    rules = {Name: (erlaubte Vorgaenger-Aktivitaeten, Ausloeser-Aktivitaeten)}.
    Mindestens ein Vorgaenger muss zeitlich vor dem ersten Ausloeser liegen.
    Gleiche Zeitstempel gelten als unklar, nicht als bewiesener Verstoss.
    Regeln sind fachliche Hypothesen; ohne Ausloeser ist ein Fall nicht bewertbar.
    """
    if not rules:
        raise ValueError("Provide at least one explicit precedence rule.")
    events = _analysis_events(log, case_id)
    ids = pd.Index(events[case_id].unique(), name=case_id)
    summaries, details = {}, []
    for name, (required, triggers) in rules.items():
        if isinstance(required, str) or isinstance(triggers, str) or not required or not triggers:
            raise ValueError("Each rule needs two non-empty collections of activity names.")
        first_required = events.loc[events["concept:name"].isin(required)].groupby(case_id)["time:timestamp"].min()
        first_trigger = events.loc[events["concept:name"].isin(triggers)].groupby(case_id)["time:timestamp"].min()
        cases = pd.DataFrame(index=ids)
        cases["required_time"] = first_required
        cases["trigger_time"] = first_trigger
        eligible = cases["trigger_time"].notna()
        cases["status"] = "no_trigger"
        cases.loc[eligible, "status"] = "ok"
        cases.loc[eligible & cases["required_time"].isna(), "status"] = "missing_required"
        cases.loc[eligible & cases["required_time"].gt(cases["trigger_time"]), "status"] = "required_after_trigger"
        cases.loc[eligible & cases["required_time"].eq(cases["trigger_time"]), "status"] = "same_timestamp"
        violation = cases["status"].isin(["missing_required", "required_after_trigger"])
        summaries[name] = {
            "cases": len(cases), "eligible_cases": int(eligible.sum()),
            "violations": int(violation.sum()),
            "violation_share": violation.sum() / eligible.sum() if eligible.any() else float("nan"),
            "missing_required": int(cases["status"].eq("missing_required").sum()),
            "required_after_trigger": int(cases["status"].eq("required_after_trigger").sum()),
            "same_timestamp": int(cases["status"].eq("same_timestamp").sum()),
            "no_trigger": int((~eligible).sum()),
        }
        details.append(cases.assign(rule=name).reset_index())
    return {"summary": pd.DataFrame.from_dict(summaries, orient="index"),
            "cases": pd.concat(details, ignore_index=True)}


def conformance_analysis(log, model, case_id="case:concept:name"):
    """Frage 6: Token-Replay gegen ein explizit uebergebenes Modell.

    Liefert Fall-Diagnosen und exakte Varianten mit Abweichungen. Ein entdecktes
    Modell ist kein fachliches Sollmodell; Token-Fitness ist keine Compliance.
    """
    events = _analysis_events(log, case_id)
    pn = as_petri_net(model)
    event_log = pm4py.convert_to_event_log(events, case_id_key=case_id)
    # Check unknown activities per case below; PM4Py's flag can affect other traces.
    diagnostics = pm4py.conformance_diagnostics_token_based_replay(
        event_log, *pn, return_diagnostics_dataframe=False,
        opt_parameters={"consider_activities_not_in_model_in_fitness": False, "show_progress_bar": False},
    )
    ids = [trace.attributes["concept:name"] for trace in event_log]
    fields = ["trace_is_fit", "trace_fitness", "missing_tokens", "remaining_tokens",
              "consumed_tokens", "produced_tokens"]
    cases = pd.DataFrame(
        [{field: row[field] for field in fields} for row in diagnostics],
        index=pd.Index(ids, name=case_id),
    )
    labels = {t.label for t in pn[0].transitions if t.label is not None}
    cases["unknown_activities"] = events.loc[~events["concept:name"].isin(labels)].groupby(case_id)[
        "concept:name"
    ].agg(lambda x: tuple(sorted(set(x)))).reindex(cases.index).apply(
        lambda x: x if isinstance(x, tuple) else ()
    )
    cases["trace_is_fit"] = cases["trace_is_fit"] & cases["unknown_activities"].map(len).eq(0)
    cases["variant"] = events.groupby(case_id)["concept:name"].agg(tuple).reindex(cases.index)
    patterns = cases.groupby("variant", sort=False).agg(
        cases=("trace_is_fit", "size"), fitting_cases=("trace_is_fit", "sum"),
        mean_fitness=("trace_fitness", "mean"),
        missing_tokens=("missing_tokens", "sum"), remaining_tokens=("remaining_tokens", "sum"),
    )
    patterns["non_fitting_cases"] = patterns["cases"] - patterns["fitting_cases"]
    patterns["non_fitting_share"] = patterns["non_fitting_cases"] / patterns["cases"]
    summary = pd.DataFrame([{
        "cases": len(cases), "fitting_cases": int(cases["trace_is_fit"].sum()),
        "non_fitting_cases": int((~cases["trace_is_fit"]).sum()),
        "fitting_share": cases["trace_is_fit"].mean(), "mean_fitness": cases["trace_fitness"].mean(),
        "cases_with_unknown_activities": int(cases["unknown_activities"].map(len).gt(0).sum()),
    }])
    return {"summary": summary, "cases": cases,
            "patterns": patterns.sort_values("non_fitting_cases", ascending=False)}


def compare_declarations(domestic, international, case_id="case:concept:name"):
    """Frage 7: deskriptiver Vergleich; keine Kausalitaet oder Signifikanzbehauptung.

    Volle beobachtete Trace-Dauer und Declaration-Spanne werden getrennt gezeigt.
    Die Declaration-Spanne ist nicht die Dauer bis zur Zahlung. Faelle ohne
    Declaration-Events werden ausgewiesen und aus Declaration-Kennzahlen entfernt.
    """
    overview, shares, monthly = {}, {}, {}
    for name, log in {"domestic": domestic, "international": international}.items():
        events = _analysis_events(log, case_id)
        full = _duration_cases(events, case_id)
        decl = events.loc[events["concept:name"].str.startswith("Declaration ")]
        if decl.empty:
            raise ValueError(f"No Declaration events in {name}.")
        cases = _duration_cases(decl, case_id)
        rejected = rejection_analysis(events, case_id=case_id)["summary"].iloc[0]
        paths = decl.groupby(case_id)["concept:name"].agg(tuple)
        counts = paths.value_counts()
        overview[name] = {
            "all_cases": len(full), "declaration_cases": len(cases),
            "cases_without_declaration": len(full) - len(cases),
            "full_median_days": full["duration_days"].median(),
            "full_p90_days": full["duration_days"].quantile(0.9),
            "declaration_median_days": cases["duration_days"].median(),
            "declaration_p90_days": cases["duration_days"].quantile(0.9),
            "declaration_mean_events": cases["events"].mean(),
            "declaration_variants": len(counts), "most_common_variant_share": counts.iloc[0] / len(cases),
            "cases_with_repeated_declaration_activity_share": cases["events"].gt(cases["activities"]).mean(),
            "rejected_cases": rejected["rejected_cases"], "rejected_share": rejected["rejected_share"],
        }
        shares[name] = decl.groupby("concept:name")[case_id].nunique() / len(cases)
        cases["start_month"] = cases["start"].dt.strftime("%Y-%m")
        monthly[name] = _duration_summary(cases, "start_month")
    activity_shares = pd.DataFrame(shares).fillna(0)
    activity_shares["international_minus_domestic"] = activity_shares["international"] - activity_shares["domestic"]
    return {"overview": pd.DataFrame(overview),
            "declaration_activity_shares": activity_shares,
            "declaration_by_start_month": pd.concat(monthly, names=["log"])}

def predecessor_times(log, target="D5❌0", case_id="case:concept:name"):
    """Zeitabstand vom direkten Vorgaenger zum Ziel, in Tagen."""
    intervals = bottleneck_analysis(log, case_id=case_id)["intervals"]

    selected = intervals.loc[
        intervals["to_activity"].map(event_code).eq(target)
    ].copy()
    selected["Voraktivitaet"] = selected["from_activity"].map(event_code)

    return (
        selected.groupby("Voraktivitaet")
        .agg(
            Anzahl=("elapsed_days", "size"),
            Traces=(case_id, "nunique"),
            Min_Tage=("elapsed_days", "min"),
            Max_Tage=("elapsed_days", "max"),
            Median_Tage=("elapsed_days", "median"),
            Durchschnitt_Tage=("elapsed_days", "mean"),
        )
        .sort_values("Anzahl", ascending=False)
    )

def successor_times(log, target="D5❌0", case_id="case:concept:name"):
    """Zeitabstand vom Ziel zum direkten Nachfolger, in Tagen."""
    intervals = bottleneck_analysis(log, case_id=case_id)["intervals"]

    selected = intervals.loc[
        intervals["from_activity"].map(event_code).eq(target)
    ].copy()
    selected["Nachaktivitaet"] = selected["to_activity"].map(event_code)

    return (
        selected.groupby("Nachaktivitaet")
        .agg(
            Anzahl=("elapsed_days", "size"),
            Traces=(case_id, "nunique"),
            Min_Tage=("elapsed_days", "min"),
            Max_Tage=("elapsed_days", "max"),
            Median_Tage=("elapsed_days", "median"),
            Durchschnitt_Tage=("elapsed_days", "mean"),
        )
        .sort_values("Anzahl", ascending=False)
    )

def rejection_timeline(log, entity="Declaration",
                       case_id="case:concept:name", freq="M"):
    """Direkte Umgebung von Employee-Rejections nach Kalendermonat."""
    if entity not in {"Declaration", "Permit"}:
        raise ValueError("entity must be 'Declaration' or 'Permit'.")

    events = _analysis_events(log, case_id)
    grouped = events.groupby(case_id, sort=False)

    previous = grouped[["concept:name", "time:timestamp"]].shift(1)
    following = grouped[["concept:name", "time:timestamp"]].shift(-1)

    events["Voraktivitaet"] = (
        previous["concept:name"].dropna().map(event_code)
        .reindex(events.index).fillna("<Trace-Anfang>")
    )
    events["Nachaktivitaet"] = (
        following["concept:name"].dropna().map(event_code)
        .reindex(events.index).fillna("<Trace-Ende>")
    )
    events["Abstand_vor_Tage"] = (
        events["time:timestamp"] - previous["time:timestamp"]
    ).dt.total_seconds() / 86400
    events["Abstand_nach_Tage"] = (
        following["time:timestamp"] - events["time:timestamp"]
    ).dt.total_seconds() / 86400

    selected = events.loc[
        events["concept:name"].eq(f"{entity} REJECTED by EMPLOYEE")
    ].copy()

    if selected.empty:
        raise ValueError(f"No Employee-Rejections for {entity}.")

    selected["Monat"] = (
        selected["time:timestamp"]
        .dt.tz_localize(None).dt.to_period(freq)
    )

    for direction in ("vor", "nach"):
        gap = selected[f"Abstand_{direction}_Tage"]
        selected[f"Null_{direction}"] = gap.eq(0).where(gap.notna())

    summary = selected.groupby(
        ["Monat", "Voraktivitaet", "Nachaktivitaet"]
    ).agg(
        Anzahl=(case_id, "size"),
        Traces=(case_id, "nunique"),
        Median_vor_Tage=("Abstand_vor_Tage", "median"),
        Median_nach_Tage=("Abstand_nach_Tage", "median"),
        Null_vor_Anteil=("Null_vor", "mean"),
        Null_nach_Anteil=("Null_nach", "mean"),
    )

    summary["Anteil_im_Monat"] = (
        summary["Anzahl"]
        / summary.groupby(level="Monat")["Anzahl"].transform("sum")
    )

    return {"summary": summary, "events": selected}
#Tasks
#1: 'Describe and visualize the general underlying process flow (reasonable level of abstraction, BPMN / Petri nets).',
#2: 'How long do the different process instances take? Are there any notable patterns?',
#3: 'Are there any bottlenecks? If yes, where? If yes, can you think of any reasons?',
#4: 'How many applications get rejected? Can you find any reasons?',
#5: 'Can you find any unexpected behavior, e.g. missing permits?',
#6: 'Are there any patterns that would suggest non-conformance?',
#7: 'Are there notable differences between international and domestic declarations?',
#8: 'What is missing to provide more detailed insights into the processes?',
#9: 'Reflect on where supervised / unsupervised machine learning techniques could help to obtain further insights.',
#10: 'Can you think of useful KPIs for the processes?',
#11: 'Make specific recommendations for improving the processes.',