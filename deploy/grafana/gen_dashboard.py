"""Generates the Grafana dashboard for the GPU node and llama-swap."""
import json
import sys

PROM = {"type": "prometheus", "uid": "${ds_prometheus}"}
LLM = {"type": "yesoreyeram-infinity-datasource", "uid": "${ds_llamaswap}"}

GPU_SEL = 'node=~"$node", gpu=~"$gpu"'


def g(metric):
    """One series per GPU: dcgm-exporter also labels series with the pod using
    the GPU, so a pod restart would otherwise duplicate them for a while."""
    return f'max by (node, gpu) ({metric}{{{GPU_SEL}}})'
ACTIVITY_PARAMS = [
    {"key": "limit", "value": "999"},
    {"key": "start", "value": "${__from:date:iso}"},
    {"key": "end", "value": "${__to:date:iso}"},
    {"key": "model", "value": "${model}"},
]

_id = [0]


def pid():
    _id[0] += 1
    return _id[0]


def prom(expr, legend="", ref="A", instant=False):
    t = {"refId": ref, "datasource": PROM, "expr": expr, "legendFormat": legend}
    if instant:
        t.update({"instant": True, "range": False})
    return t


def infinity(url, root, columns, params=None, ref="A"):
    return {
        "refId": ref,
        "datasource": LLM,
        "type": "json",
        "source": "url",
        "parser": "backend",
        "format": "table",
        "url": url,
        "url_options": {"method": "GET", "params": params or []},
        "root_selector": root,
        "columns": [
            {"selector": s, "text": t, "type": ty} for s, t, ty in columns
        ],
    }


ACTIVITY_COLUMNS = [
    ("timestamp", "Ora", "timestamp"),
    ("model", "Modello", "string"),
    ("resp_status_code", "HTTP", "number"),
    ("tokens.input_tokens", "Token input", "number"),
    ("tokens.output_tokens", "Token output", "number"),
    ("tokens.cache_tokens", "Token in cache", "number"),
    ("tokens.prompt_per_second", "Prompt tok/s", "number"),
    ("tokens.tokens_per_second", "Generazione tok/s", "number"),
    ("duration_ms", "Durata", "number"),
]


def activity(ref="A"):
    return infinity("/api/metrics/activity", "data", ACTIVITY_COLUMNS, ACTIVITY_PARAMS, ref)


def grid(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


def row(title, y):
    return {"type": "row", "id": pid(), "title": title, "collapsed": False,
            "gridPos": grid(0, y, 24, 1), "panels": []}


def stat(title, targets, pos, unit="none", decimals=None, calcs=("lastNotNull",),
         fields="", mappings=None, thresholds=None, color_mode="value",
         no_value=None, text_mode="auto", description=""):
    defaults = {"unit": unit, "mappings": mappings or [],
                "thresholds": thresholds or {"mode": "absolute", "steps": [
                    {"color": "green", "value": None}]},
                "color": {"mode": "thresholds"}}
    if decimals is not None:
        defaults["decimals"] = decimals
    if no_value is not None:
        defaults["noValue"] = no_value
    return {"type": "stat", "id": pid(), "title": title, "description": description,
            "gridPos": pos, "targets": targets,
            "fieldConfig": {"defaults": defaults, "overrides": []},
            "options": {"reduceOptions": {"values": False, "calcs": list(calcs), "fields": fields},
                        "colorMode": color_mode, "graphMode": "none", "textMode": text_mode,
                        "justifyMode": "center", "orientation": "auto",
                        "wideLayout": True, "showPercentChange": False}}


def gauge(title, targets, pos, unit, maxv, steps):
    return {"type": "gauge", "id": pid(), "title": title, "gridPos": pos, "targets": targets,
            "fieldConfig": {"defaults": {"unit": unit, "min": 0, "max": maxv,
                                         "thresholds": {"mode": "absolute", "steps": steps},
                                         "color": {"mode": "thresholds"}}, "overrides": []},
            "options": {"reduceOptions": {"values": False, "calcs": ["lastNotNull"], "fields": ""},
                        "showThresholdMarkers": True, "showThresholdLabels": False}}


def timeseries(title, targets, pos, unit="none", draw="line", decimals=None,
               overrides=None, fill=10, stack=False, minv=None, description=""):
    custom = {"drawStyle": draw, "lineWidth": 2, "fillOpacity": fill,
              "pointSize": 6, "showPoints": "auto" if draw == "line" else "always",
              "spanNulls": False,
              "stacking": {"mode": "normal" if stack else "none"}}
    defaults = {"unit": unit, "custom": custom, "color": {"mode": "palette-classic"}}
    if decimals is not None:
        defaults["decimals"] = decimals
    if minv is not None:
        defaults["min"] = minv
    return {"type": "timeseries", "id": pid(), "title": title, "description": description,
            "gridPos": pos, "targets": targets,
            "fieldConfig": {"defaults": defaults, "overrides": overrides or []},
            "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                        "tooltip": {"mode": "multi", "sort": "none"}}}


GREEN = {"color": "green", "value": None}

panels = []
y = 0

# --- Stato --------------------------------------------------------------------
panels.append(row("Stato del modello", y)); y += 1
panels.append(stat(
    "Modello caricato",
    [infinity("/running", "running", [("model", "Modello", "string"), ("state", "Stato", "string"),
                                      ("ttl", "TTL", "number")])],
    grid(0, y, 6, 4), fields="/^Modello$/", no_value="Nessun modello in VRAM",
    color_mode="background", text_mode="value",
    thresholds={"mode": "absolute", "steps": [{"color": "blue", "value": None}]},
    description="Modello attualmente avviato da llama-swap (/running). Viene scaricato dopo il TTL di inattività."))
panels.append(stat(
    "Stato",
    [infinity("/running", "running", [("model", "Modello", "string"), ("state", "Stato", "string")])],
    grid(6, y, 3, 4), fields="/^Stato$/", no_value="scarico", text_mode="value",
    mappings=[{"type": "value", "options": {
        "ready": {"text": "pronto", "color": "green"},
        "starting": {"text": "in caricamento", "color": "orange"},
        "stopping": {"text": "in arresto", "color": "orange"}}}],
    color_mode="background"))
panels.append({
    "type": "state-timeline", "id": pid(), "title": "Modello in VRAM",
    "description": "Ricavato dalla VRAM occupata (oltre 1 GiB = modello caricato).",
    "gridPos": grid(9, y, 15, 4),
    "targets": [prom(f'max by (gpu) ({g("DCGM_FI_DEV_FB_USED")}) > bool 1024', "GPU {{gpu}}")],
    "fieldConfig": {"defaults": {
        "mappings": [{"type": "value", "options": {
            "0": {"text": "Scarico", "color": "transparent"},
            "1": {"text": "Caricato", "color": "green"}}}],
        "color": {"mode": "thresholds"},
        "thresholds": {"mode": "absolute", "steps": [GREEN]},
        "custom": {"fillOpacity": 80, "lineWidth": 0}}, "overrides": []},
    "options": {"showValue": "never", "mergeValues": True, "rowHeight": 0.8,
                "legend": {"showLegend": False}, "alignValue": "center"}})
y += 4

# --- Richieste nel periodo -------------------------------------------------------
panels.append(row("Richieste nel periodo selezionato", y)); y += 1
panels.append(stat("Richieste", [activity()], grid(0, y, 4, 4), calcs=("count",),
                   fields="/^Ora$/", decimals=0, no_value="0"))
panels.append(stat("Token generati", [activity()], grid(4, y, 4, 4), calcs=("sum",),
                   fields="/^Token output$/", unit="short", no_value="0"))
panels.append(stat("Token in input", [activity()], grid(8, y, 4, 4), calcs=("sum",),
                   fields="/^Token input$/", unit="short", no_value="0"))
panels.append(stat("Velocità media generazione", [activity()], grid(12, y, 4, 4), calcs=("mean",),
                   fields="/^Generazione tok\\/s$/", unit="none", decimals=1, no_value="-",
                   description="Token al secondo in generazione, media delle richieste nel periodo."))
panels.append(stat("Velocità media prompt", [activity()], grid(16, y, 4, 4), calcs=("mean",),
                   fields="/^Prompt tok\\/s$/", unit="none", decimals=1, no_value="-"))
panels.append(stat("Durata media", [activity()], grid(20, y, 4, 4), calcs=("mean",),
                   fields="/^Durata$/", unit="ms", no_value="-",
                   description="Include l'eventuale caricamento a freddo del modello."))
y += 4
panels.append(timeseries(
    "Velocità per richiesta", [activity()], grid(0, y, 12, 8), unit="none", draw="points",
    decimals=1, fill=0,
    overrides=[{"matcher": {"id": "byRegexp", "options": "^(HTTP|Token .*|Durata)$"},
                "properties": [{"id": "custom.hideFrom",
                                "value": {"legend": True, "tooltip": True, "viz": True}}]}],
    description="Token/s di prompt e generazione di ogni richiesta."))
panels.append(timeseries(
    "Token per richiesta", [activity()], grid(12, y, 12, 8), unit="short", draw="bars", fill=80,
    stack=True,
    overrides=[{"matcher": {"id": "byRegexp", "options": "^(HTTP|Token in cache|.*tok/s|Durata)$"},
                "properties": [{"id": "custom.hideFrom",
                                "value": {"legend": True, "tooltip": True, "viz": True}}]}]))
y += 8
panels.append({
    "type": "table", "id": pid(), "title": "Ultime richieste", "gridPos": grid(0, y, 24, 8),
    "targets": [activity()],
    "fieldConfig": {"defaults": {"custom": {"align": "auto"}}, "overrides": [
        {"matcher": {"id": "byName", "options": "Durata"},
         "properties": [{"id": "unit", "value": "ms"}]},
        {"matcher": {"id": "byRegexp", "options": ".*tok/s"},
         "properties": [{"id": "decimals", "value": 1}]},
        {"matcher": {"id": "byName", "options": "HTTP"},
         "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}},
                        {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                            {"color": "green", "value": None}, {"color": "red", "value": 400}]}}]}]},
    "options": {"showHeader": True, "sortBy": [{"displayName": "Ora", "desc": True}],
                "footer": {"show": False}}})
y += 8

# --- GPU ------------------------------------------------------------------------
panels.append(row("GPU", y)); y += 1
vram_pct = (f'100 * sum by (gpu) ({g("DCGM_FI_DEV_FB_USED")}) / '
            f'sum by (gpu) ({g("DCGM_FI_DEV_FB_USED")} + {g("DCGM_FI_DEV_FB_FREE")} '
            f'+ {g("DCGM_FI_DEV_FB_RESERVED")})')
panels.append(gauge("Utilizzo GPU", [prom(f'avg({g("DCGM_FI_DEV_GPU_UTIL")})', instant=True)],
                    grid(0, y, 4, 5), "percent", 100,
                    [GREEN, {"color": "orange", "value": 80}, {"color": "red", "value": 95}]))
panels.append(gauge("VRAM occupata", [prom(vram_pct, instant=True)], grid(4, y, 4, 5), "percent", 100,
                    [GREEN, {"color": "orange", "value": 85}, {"color": "red", "value": 95}]))
panels.append(stat("Temperatura", [prom(f'max({g("DCGM_FI_DEV_GPU_TEMP")})', instant=True)],
                   grid(8, y, 4, 5), unit="celsius", decimals=0,
                   thresholds={"mode": "absolute", "steps": [
                       GREEN, {"color": "orange", "value": 70}, {"color": "red", "value": 80}]}))
panels.append(stat("Potenza", [prom(f'sum({g("DCGM_FI_DEV_POWER_USAGE")})', instant=True)],
                   grid(12, y, 4, 5), unit="watt", decimals=0))
panels.append(stat(
    "Energia nel periodo",
    [prom(f'sum(increase(({g("DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION")})[$__range:1m])) / 3.6e9',
          instant=True)],
    grid(16, y, 4, 5), unit="kwatth", decimals=3,
    description="Energia consumata dalla GPU nel periodo selezionato (contatore DCGM in mJ)."))
panels.append(stat("Processo sulla GPU",
                   # most recently scraped pod, so a just-replaced pod is not shown
                   [prom(f'topk(1, max by (pod) (timestamp(DCGM_FI_DEV_GPU_TEMP{{{GPU_SEL}, pod!=""}})))',
                         legend="{{pod}}", instant=True)],
                   grid(20, y, 4, 5), text_mode="name", no_value="nessuno",
                   thresholds={"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                   description="Pod che ha la GPU assegnata (etichetta di dcgm-exporter)."))
y += 5
panels.append(timeseries("Utilizzo GPU e memoria",
                         [prom(f'{g("DCGM_FI_DEV_GPU_UTIL")}', "GPU {{gpu}} calcolo"),
                          prom(f'{g("DCGM_FI_DEV_MEM_COPY_UTIL")}', "GPU {{gpu}} banda memoria", "B")],
                         grid(0, y, 12, 8), unit="percent", minv=0))
panels.append(timeseries("VRAM",
                         [prom(f'{g("DCGM_FI_DEV_FB_USED")} * 1048576', "GPU {{gpu}} usata"),
                          prom(f'({g("DCGM_FI_DEV_FB_USED")} + {g("DCGM_FI_DEV_FB_FREE")} '
                               f'+ {g("DCGM_FI_DEV_FB_RESERVED")}) * 1048576', "GPU {{gpu}} totale", "B")],
                         grid(12, y, 12, 8), unit="bytes", minv=0,
                         overrides=[{"matcher": {"id": "byRegexp", "options": ".*totale"},
                                     "properties": [{"id": "custom.lineStyle",
                                                     "value": {"fill": "dash", "dash": [10, 10]}},
                                                    {"id": "custom.fillOpacity", "value": 0}]}]))
y += 8
panels.append(timeseries("Temperatura",
                         [prom(f'{g("DCGM_FI_DEV_GPU_TEMP")}', "GPU {{gpu}}")],
                         grid(0, y, 8, 8), unit="celsius", fill=0))
panels.append(timeseries("Potenza",
                         [prom(f'{g("DCGM_FI_DEV_POWER_USAGE")}', "GPU {{gpu}}")],
                         grid(8, y, 8, 8), unit="watt", minv=0))
panels.append(timeseries("Frequenze",
                         [prom(f'{g("DCGM_FI_DEV_SM_CLOCK")}', "GPU {{gpu}} SM"),
                          prom(f'{g("DCGM_FI_DEV_MEM_CLOCK")}', "GPU {{gpu}} memoria", "B")],
                         grid(16, y, 8, 8), unit="rotmhz", fill=0))
y += 8

# --- Nodo -----------------------------------------------------------------------
panels.append(row("Nodo GPU", y)); y += 1
panels.append(timeseries("CPU del nodo",
                         [prom('avg by (node) (llamaswap_cpu_util_percent{node=~"$node"})', "{{node}}")],
                         grid(0, y, 8, 8), unit="percent", minv=0))
panels.append(timeseries("RAM del nodo",
                         [prom('llamaswap_memory_used_bytes{node=~"$node"}', "{{node}} usata"),
                          prom('llamaswap_memory_total_bytes{node=~"$node"}', "{{node}} totale", "B")],
                         grid(8, y, 8, 8), unit="bytes", minv=0,
                         overrides=[{"matcher": {"id": "byRegexp", "options": ".*totale"},
                                     "properties": [{"id": "custom.lineStyle",
                                                     "value": {"fill": "dash", "dash": [10, 10]}},
                                                    {"id": "custom.fillOpacity", "value": 0}]}]))
panels.append(timeseries(
    "Memoria del processo GPU",
    [prom('sum by (pod) (container_memory_working_set_bytes{pod=~"$gpu_pod", container!="", container!="POD"})',
          "{{pod}}")],
    grid(16, y, 8, 8), unit="bytes", minv=0,
    description="Memoria di sistema del pod che usa la GPU (include la cache del file del modello)."))
y += 8


def ds_var(name, label, ds_type, default_uid):
    return {"name": name, "label": label, "type": "datasource", "query": ds_type,
            "current": {"text": default_uid, "value": default_uid}, "hide": 0,
            "refresh": 1, "regex": "", "includeAll": False, "multi": False}


def query_var(name, label, query, include_all=True, multi=True, hide=0, all_value=".*"):
    v = {"name": name, "label": label, "type": "query", "datasource": PROM,
         "query": {"query": query, "refId": name}, "definition": query,
         "refresh": 2, "includeAll": include_all, "multi": multi,
         "current": {}, "hide": hide, "sort": 1, "regex": ""}
    if all_value is not None:
        v["allValue"] = all_value
    return v


templating = [
    ds_var("ds_prometheus", "Prometheus", "prometheus", "prometheus"),
    ds_var("ds_llamaswap", "llama-swap", "yesoreyeram-infinity-datasource", "llama-swap"),
    query_var("node", "Nodo", "label_values(DCGM_FI_DEV_GPU_TEMP, node)"),
    query_var("gpu", "GPU", 'label_values(DCGM_FI_DEV_GPU_TEMP{node=~"$node"}, gpu)'),
    query_var("gpu_pod", "Pod GPU", 'label_values(DCGM_FI_DEV_GPU_TEMP{node=~"$node"}, pod)', hide=2,
              # "All" = regex of the listed pods only, not every pod in the cluster
              all_value=None),
    {"name": "model", "label": "Modello", "type": "query", "datasource": LLM,
     "query": {"refId": "model", "queryType": "infinity", "infinityQuery": {
         "refId": "model", "type": "json", "source": "url", "parser": "backend", "format": "table",
         "url": "/v1/models", "url_options": {"method": "GET", "params": []},
         "root_selector": "data", "columns": [{"selector": "id", "text": "id", "type": "string"}]}},
     "refresh": 1, "includeAll": True, "multi": False, "allValue": "", "current": {},
     "hide": 0, "sort": 1, "regex": ""},
]

dashboard = {
    "title": "LLM e GPU",
    "uid": "llm-gpu",
    "description": "Stato del modello, richieste e token di llama-swap, uso della GPU (DCGM).",
    "tags": ["gpu", "llm", "llama-swap"],
    "timezone": "browser",
    "editable": True,
    "graphTooltip": 1,
    "refresh": "30s",
    "time": {"from": "now-6h", "to": "now"},
    "schemaVersion": 39,
    "templating": {"list": templating},
    "annotations": {"list": []},
    "panels": panels,
}

json.dump(dashboard, open(sys.argv[1], "w"), indent=2, ensure_ascii=False)
print(f"{len(panels)} panels")
