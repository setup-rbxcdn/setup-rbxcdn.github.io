import re, json, os, requests
from datetime import datetime, timezone, timedelta

# --- CONFIG ---

BASE_DIR = "."

# Paths
PATHS = {
    "output": os.path.join(BASE_DIR, "version-history"),
    "inverted": os.path.join(BASE_DIR, "version-history-inverted"),
    "mac": os.path.join(BASE_DIR, "mac"),
}

# Metadata path for storing first-seen timestamps
PATH_METADATA = os.path.join(BASE_DIR, "hash-metadata.json")

# Deploy history endpoints
DEPLOY_HISTORY_URLS = {
    "Windows": "https://setup.rbxcdn.com/DeployHistory.txt",
    "Mac": "https://setup.rbxcdn.com/mac/DeployHistory.txt",
}

GH_WINSTUDIO64_VERSION_URL = "https://raw.githubusercontent.com/Roblox/creator-docs/refs/heads/main/content/en-us/reference/engine/STUDIO_VERSION"

# ClientSettings endpoints
CLIENTSETTINGS_BASE = "https://clientsettingscdn.roblox.com/v2/client-version"

CLIENT_CHANNELS = [
    "",  # default
    "/channel/zbeta",
    "/channel/zliveforbeta",
]

# Regex
DEPLOY_PATTERN = re.compile(
    r"New (\w+) (version-[a-f0-9]+|version-hidden) at ([\d/]+ [\d:]+ [AP]M),.*?file ver(?:s)?ion:\s*([0-9,\s]+)",
    re.I,
)

RECENT_VERSION_WINDOW = 10

# DeployHistory is NY Time (UTC-5)
DEPLOY_HISTORY_TZ_OFFSET = timedelta(hours=-5)


# --- Ensure dirs exist ---
for path in list(PATHS.values()) + [os.path.dirname(PATH_METADATA)]:
    if path:
        os.makedirs(path, exist_ok=True)

# --- Data stores ---
inverted_data = {}  # platform -> binary -> { hash: version }
resolver_cache = {}  # (platform, bt) -> { hash: version }
hash_metadata = {}  # platform -> binary -> { hash: "ISO8601_timestamp" }


# --- Slot rules ---
def get_slot_limit(bt):
    return 2 if bt in ("WindowsPlayer", "Studio64") else 1  # 2 because Luobu


# --- Utils ---
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


def get_version_minor(v):
    try:
        return int(v.split(".")[1])
    except:
        return 0


def parse_deploy_date_to_utc(date_str):
    try:
        dt_naive = datetime.strptime(date_str.strip(), "%m/%d/%Y %I:%M:%S %p")
        tz_fixed = timezone(DEPLOY_HISTORY_TZ_OFFSET)
        dt_local = dt_naive.replace(tzinfo=tz_fixed)
        dt_utc = dt_local.astimezone(timezone.utc)
        return dt_utc
    except Exception as e:
        print(f"Date parse error: {e} for '{date_str}'")
        return None


def load_metadata():
    global hash_metadata
    if os.path.exists(PATH_METADATA):
        try:
            with open(PATH_METADATA, "r") as f:
                hash_metadata = json.load(f)
        except:
            hash_metadata = {}
    else:
        hash_metadata = {}


def save_metadata():
    with open(PATH_METADATA, "w") as f:
        json.dump(hash_metadata, f, indent=2)


def record_hash_first_seen(platform, bt, hash_val):
    if platform not in hash_metadata:
        hash_metadata[platform] = {}
    if bt not in hash_metadata[platform]:
        hash_metadata[platform][bt] = {}

    if hash_val not in hash_metadata[platform][bt]:
        hash_metadata[platform][bt][hash_val] = datetime.now(timezone.utc).isoformat()


def get_hash_timestamp(platform, bt, hash_val):
    try:
        ts_str = hash_metadata.get(platform, {}).get(bt, {}).get(hash_val)
        if ts_str:
            return datetime.fromisoformat(ts_str)
    except:
        pass
    return None


def get_global_latest_minor(platform):
    plat = inverted_data.get(platform, {})
    minors = []
    for bt_dict in plat.values():
        for v in bt_dict.values():
            minors.append(get_version_minor(v))
    return max(minors) if minors else 0


def get_bt_latest_minor(inv_bt_dict):
    if not inv_bt_dict:
        return 0
    return max(get_version_minor(v) for v in inv_bt_dict.values())


def fetch_gh_winstudio64_version():
    content = fetch(GH_WINSTUDIO64_VERSION_URL, as_text=True)
    if not content:
        return None, None
    lines = content.strip().splitlines()
    if len(lines) < 2:
        return None, None
    return lines[0].strip(), lines[1].strip()


# --- PRELOAD ---
load_metadata()

for platform in DEPLOY_HISTORY_URLS.keys():
    inv_plat_data = inverted_data.setdefault(platform, {})
    inv_dir = os.path.join(PATHS["inverted"], platform)

    if os.path.exists(inv_dir):
        for file in os.listdir(inv_dir):
            if not file.endswith(".json"):
                continue
            bt = file[:-5]
            path = os.path.join(inv_dir, file)
            try:
                with open(path, "r") as f:
                    inv_bt = json.load(f)
            except:
                continue
            inv_plat_data.setdefault(bt, {}).update(inv_bt)

# Github Studio64 Hash
s64_ver, s64_hash = fetch_gh_winstudio64_version()
if s64_ver and s64_hash:
    win_data = inverted_data.setdefault("Windows", {})
    s64_dict = win_data.setdefault("Studio64", {})
    print(f"{s64_ver} {s64_hash} WindowsStudio64 Github")
    if s64_hash not in s64_dict:
        s64_dict[s64_hash] = s64_ver
        record_hash_first_seen("Windows", "Studio64", s64_hash)
else:
    print("Could not fetch WindowsStudio64 Github version.")


# --- Resolver ---
def get_resolver(platform, bt):
    key = (platform, bt)
    if key in resolver_cache:
        return resolver_cache[key]

    inv_bt_dict = inverted_data.get(platform, {}).get(bt, {})
    inv_resolver = dict(inv_bt_dict)

    global_latest = get_global_latest_minor(platform)
    bt_latest = get_bt_latest_minor(inv_bt_dict)

    if bt_latest < (global_latest - RECENT_VERSION_WINDOW):
        resolver_cache[key] = inv_resolver
        return inv_resolver

    lookup = normalize_binary(bt, platform)

    for suffix in CLIENT_CHANNELS:
        url = f"{CLIENTSETTINGS_BASE}/{lookup}{suffix}"
        js = fetch(url)
        if not js:
            continue

        print(js, lookup, suffix)

        v = js.get("version")
        h = js.get("clientVersionUpload")

        if v and h:
            full_hash = h if h.startswith("version-") else "version-" + h
            # Only add if new to prevent API rotation from overwriting stable history
            if full_hash not in inv_resolver:
                inv_resolver[full_hash] = v
                inv_bt_dict[full_hash] = v
                record_hash_first_seen(platform, bt, full_hash)

    resolver_cache[key] = inv_resolver
    return inv_resolver


# --- MAIN ---
for platform, url in DEPLOY_HISTORY_URLS.items():
    txt = fetch(url, True)
    if not txt:
        continue

    inv_plat_data = inverted_data.setdefault(platform, {})
    lines = txt.split("\n")
    output_lines = [""] * len(lines)

    # Structure to hold hidden line info for global optimization
    # Key: (bt, version) -> List of { index, dt, line_text }
    hidden_groups = {}

    # First Pass: Parse all lines, handle explicit hashes, collect hidden lines
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
        line_dt_utc = parse_deploy_date_to_utc(date_str)

        inv_bt_dict = inv_plat_data.setdefault(bt, {})

        if status != "version-hidden":
            # Explicit hash
            h = status
            inv_bt_dict[h] = v
            output_lines[i] = line.rstrip("\n")
        else:
            # Hidden hash - collect for second pass
            key = (bt, v)
            if key not in hidden_groups:
                hidden_groups[key] = []
            hidden_groups[key].append({"index": i, "dt": line_dt_utc, "line": line})

    # Second Pass: Global Optimization for Hidden Lines
    for (bt, v), hidden_entries in hidden_groups.items():
        # Get all known hashes for this BT and Version
        inv_resolver = get_resolver(platform, bt)
        candidates = [h for h, ver in inv_resolver.items() if ver == v]

        # Generate all possible assignments: (hidden_entry, hash, time_diff)
        possible_assignments = []

        for entry in hidden_entries:
            if entry["dt"] is None:
                continue
            for h in candidates:
                h_ts = get_hash_timestamp(platform, bt, h)
                if h_ts is None:
                    continue
                diff = abs((entry["dt"] - h_ts).total_seconds())
                possible_assignments.append({"entry": entry, "hash": h, "diff": diff})

        # Sort assignments by time difference (closest match first)
        possible_assignments.sort(key=lambda x: x["diff"])

        # Track usage per hash for slot limiting
        usage_counts = {}
        limit = get_slot_limit(bt)

        # Assign hashes
        for assignment in possible_assignments:
            entry = assignment["entry"]
            h = assignment["hash"]

            # Check slot limit
            current_usage = usage_counts.get(h, 0)
            if current_usage >= limit:
                continue

            # Check if entry already assigned
            if output_lines[entry["index"]] == "":
                # Assign
                new_line = entry["line"].replace("version-hidden", h, 1)
                output_lines[entry["index"]] = new_line.rstrip("\n")

                # Update usage
                usage_counts[h] = current_usage + 1

                # Update STRICT BT dict
                inv_plat_data.setdefault(bt, {})[h] = v

    # Fill any remaining unassigned hidden lines
    for i, line in enumerate(output_lines):
        if line == "":
            output_lines[i] = lines[i].rstrip("\n")

    # Save updated DeployHistory
    path_txt = os.path.join(
        PATHS["mac"] if platform == "Mac" else BASE_DIR, "DeployHistory.txt"
    )

    new_dh_content = "\n".join(output_lines)
    with open(path_txt, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_dh_content)

save_metadata()

# --- Build normal data ---
data = {}
for platform, binaries in inverted_data.items():
    for bt, hashes in binaries.items():
        for h, v in hashes.items():
            data.setdefault(platform, {}).setdefault(bt, {})[v] = h

# --- Write NORMAL JSON ---
for platform, binaries in data.items():
    for bt, versions in binaries.items():
        path = os.path.join(PATHS["output"], platform, f"{bt}.json")
        sorted_versions = dict(
            sorted(versions.items(), key=lambda x: version_key(x[0]))
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                sorted_versions, f, indent=2, separators=(",", ": "), ensure_ascii=False
            )

# --- Write INVERTED JSON ---
for platform, binaries in inverted_data.items():
    for bt, hashes in binaries.items():
        path = os.path.join(PATHS["inverted"], platform, f"{bt}.json")

        grouped = {}
        for h, v in hashes.items():
            grouped.setdefault(v, []).append(h)

        sorted_versions = sorted(grouped.keys(), key=version_key)
        ordered = {}
        for v in sorted_versions:
            for h in grouped[v]:
                ordered[h] = v

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ordered, f, indent=2, separators=(",", ": "), ensure_ascii=False)
