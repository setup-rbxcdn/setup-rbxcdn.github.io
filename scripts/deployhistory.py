import re, json, os, requests
from datetime import datetime, timezone, timedelta

# --- CONFIG ---
BASE_DIR = "."
PATHS = {
    "output": os.path.join(BASE_DIR, "version-history"),
    "inverted": os.path.join(BASE_DIR, "version-history-inverted"),
    "mac": os.path.join(BASE_DIR, "mac"),
}
PATH_METADATA = os.path.join(BASE_DIR, "hash-metadata.json")

DEPLOY_HISTORY_URLS = {
    "Windows": "https://setup.rbxcdn.com/DeployHistory.txt",
    "Mac": "https://setup.rbxcdn.com/mac/DeployHistory.txt",
}
GH_WINSTUDIO64_URL = "https://raw.githubusercontent.com/Roblox/creator-docs/refs/heads/main/content/en-us/reference/engine/STUDIO_VERSION"
CLIENTSETTINGS_BASE = "https://clientsettingscdn.roblox.com/v2/client-version"

CLIENT_CHANNELS = [
    "",  # default
    "/channel/zbeta",
    "/channel/zliveforbeta",
]

DEPLOY_PATTERN = re.compile(
    r"New (\w+) (version-[a-f0-9]+|version-hidden) at ([\d/]+ [\d:]+ [AP]M),.*?file ver(?:s)?ion:\s*([0-9,\s]+)",
    re.I,
)
RECENT_VERSION_WINDOW = 10
DEPLOY_HISTORY_TZ_OFFSET = timedelta(hours=-5)

# --- GLOBAL STATE ---
inverted_data = {}  # platform -> binary -> { hash: version }
resolver_cache = {}  # (platform, bt) -> { hash: version }
hash_metadata = {}  # platform -> binary -> { hash: "ISO8601_timestamp" }


def ensure_dirs():
    for p in list(PATHS.values()) + [os.path.dirname(PATH_METADATA)]:
        if p:
            os.makedirs(p, exist_ok=True)


def fetch(url, as_text=False):
    try:
        r = requests.get(url, timeout=10)
        return r.text if as_text else r.json()
    except Exception as e:
        print(f"Fetch error {url}: {e}")
        return None


def normalize_binary(bt, platform):
    if bt.startswith("Studio"):
        return platform + bt
    if platform == "Mac" and bt == "Client":
        return "MacPlayer"
    return bt


def normalize_version(v):
    parts = [x.strip() for x in v.split(",") if x.strip()]
    # * In ~25 years 2000 might be a problem (this is here because of mac dh)
    if parts and parts[0].isdigit() and int(parts[0]) > 2000:
        parts[0] = "0"
    return ".".join(parts)


def version_key(v):
    return tuple(int(x) if x.isdigit() else 0 for x in v.split("."))


def get_minor(v):
    try:
        return int(v.split(".")[1])
    except:
        return 0


def parse_date_utc(date_str):
    try:
        dt = datetime.strptime(date_str.strip(), "%m/%d/%Y %I:%M:%S %p")
        return dt.replace(tzinfo=timezone(DEPLOY_HISTORY_TZ_OFFSET)).astimezone(timezone.utc)
    except:
        return None


def load_metadata():
    global hash_metadata
    if os.path.exists(PATH_METADATA):
        try:
            with open(PATH_METADATA, "r") as f:
                hash_metadata = json.load(f)
        except:
            hash_metadata = {}


def save_metadata():
    with open(PATH_METADATA, "w") as f:
        json.dump(hash_metadata, f, indent=2)


def record_hash(platform, bt, h):
    hash_metadata.setdefault(platform, {}).setdefault(bt, {})
    if h not in hash_metadata[platform][bt]:
        hash_metadata[platform][bt][h] = datetime.now(timezone.utc).isoformat()


def get_hash_ts(platform, bt, h):
    try:
        ts = hash_metadata.get(platform, {}).get(bt, {}).get(h)
        return datetime.fromisoformat(ts) if ts else None
    except:
        return None


def get_resolver(platform, bt):
    key = (platform, bt)
    if key in resolver_cache:
        return resolver_cache[key]

    inv_bt_dict = inverted_data.get(platform, {}).get(bt, {})
    res = dict(inv_bt_dict)

    # Check if recent enough to fetch API
    bt_latest = max((get_minor(v) for v in inv_bt_dict.values()), default=0)
    global_latest = max(
        (
            get_minor(v)
            for b in inverted_data.get(platform, {}).values()
            for v in b.values()
        ),
        default=0,
    )

    if bt_latest >= (global_latest - RECENT_VERSION_WINDOW):
        lookup = normalize_binary(bt, platform)
        for suffix in CLIENT_CHANNELS:
            js = fetch(f"{CLIENTSETTINGS_BASE}/{lookup}{suffix}")
            print(js, lookup, suffix)
            if js and js.get("version") and js.get("clientVersionUpload"):
                v, h = js["version"], js["clientVersionUpload"]
                full_h = h if h.startswith("version-") else "version-" + h
                if full_h not in res:
                    res[full_h] = v
                    inv_bt_dict[full_h] = v
                    record_hash(platform, bt, full_h)

    resolver_cache[key] = res
    return res


# --- INIT ---
ensure_dirs()
load_metadata()

# Preload Inverted JSONs
for plat in DEPLOY_HISTORY_URLS:
    inv_dir = os.path.join(PATHS["inverted"], plat)
    if os.path.exists(inv_dir):
        for f in os.listdir(inv_dir):
            if f.endswith(".json"):
                try:
                    with open(os.path.join(inv_dir, f)) as fh:
                        inverted_data.setdefault(plat, {}).setdefault(
                            f[:-5], {}
                        ).update(json.load(fh))
                except:
                    pass

# Github Hash
content = fetch(GH_WINSTUDIO64_URL, True)
if content:
    lines = content.strip().splitlines()
    if len(lines) >= 2:
        s64_ver, s64_hash = lines[0].strip(), lines[1].strip()
        d = inverted_data.setdefault("Windows", {}).setdefault("Studio64", {})
        print(f"{s64_ver} {s64_hash} WindowsStudio64 Github")
        if s64_hash not in d:
            d[s64_hash] = s64_ver
            record_hash("Windows", "Studio64", s64_hash)
    else:
        print("Could not parse Github version file.")
else:
    print("Could not fetch WindowsStudio64 Github version.")

# --- MAIN PROCESSING ---
for platform, url in DEPLOY_HISTORY_URLS.items():
    txt = fetch(url, True)
    if not txt:
        continue

    inv_plat_data = inverted_data.setdefault(platform, {})
    lines = txt.split("\n")
    output_lines = [""] * len(lines)
    hidden_groups = {}

    # Pass 1: Parse & Collect
    for i, line in enumerate(lines):
        if not line.strip():
            output_lines[i] = line
            continue
        m = DEPLOY_PATTERN.search(line)
        if not m:
            output_lines[i] = line.rstrip("\n")
            continue

        bt, status, date_str, raw_v = m.groups()
        v = normalize_version(raw_v)
        dt_utc = parse_date_utc(date_str)
        inv_bt = inv_plat_data.setdefault(bt, {})

        if status != "version-hidden":
            inv_bt[status] = v
            output_lines[i] = line.rstrip("\n")
        else:
            hidden_groups.setdefault((bt, v), []).append(
                {"idx": i, "dt": dt_utc, "line": line}
            )

    # Pass 2: Resolve Hidden
    for (bt, v), entries in hidden_groups.items():
        candidates = [h for h, ver in get_resolver(platform, bt).items() if ver == v]
        assignments = []

        for entry in entries:
            if not entry["dt"]:
                continue
            for h in candidates:
                ts = get_hash_ts(platform, bt, h)
                if ts:
                    assignments.append(
                        {
                            "entry": entry,
                            "hash": h,
                            "diff": abs((entry["dt"] - ts).total_seconds()),
                        }
                    )

        assignments.sort(key=lambda x: x["diff"])

        usage = {}
        limit = 2 if bt in ("WindowsPlayer", "Studio64") else 1  # 2 because Luobu

        for assign in assignments:
            h = assign["hash"]
            if usage.get(h, 0) >= limit:
                continue
            if output_lines[assign["entry"]["idx"]] == "":
                output_lines[assign["entry"]["idx"]] = (
                    assign["entry"]["line"].replace("version-hidden", h, 1).rstrip("\n")
                )
                usage[h] = usage.get(h, 0) + 1
                inv_plat_data.setdefault(bt, {})[h] = v

    # Fill remaining
    for i, line in enumerate(output_lines):
        if line == "":
            output_lines[i] = lines[i].rstrip("\n")

    # Save DH
    path_txt = os.path.join(
        PATHS["mac"] if platform == "Mac" else BASE_DIR, "DeployHistory.txt"
    )
    with open(path_txt, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(output_lines))

save_metadata()

# --- WRITE JSONS ---
# Build Normal Data
data = {}
for plat, bins in inverted_data.items():
    for bt, hashes in bins.items():
        for h, v in hashes.items():
            data.setdefault(plat, {}).setdefault(bt, {})[v] = h


# Writer Helper
def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, separators=(",", ": "), ensure_ascii=False)


# Write Normal
for plat, bins in data.items():
    for bt, vers in bins.items():
        sorted_v = dict(sorted(vers.items(), key=lambda x: version_key(x[0])))
        write_json(os.path.join(PATHS["output"], plat, f"{bt}.json"), sorted_v)

# Write Inverted
for plat, bins in inverted_data.items():
    for bt, hashes in bins.items():
        grouped = {}
        for h, v in hashes.items():
            grouped.setdefault(v, []).append(h)

        ordered = {}
        for v in sorted(grouped.keys(), key=version_key):
            for h in grouped[v]:
                ordered[h] = v

        write_json(os.path.join(PATHS["inverted"], plat, f"{bt}.json"), ordered)
