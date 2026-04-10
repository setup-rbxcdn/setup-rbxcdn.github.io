import re, json, os, requests

# --- CONFIG ---

BASE_DIR = ""

# Paths
PATHS = {
    "output": os.path.join(BASE_DIR, "version-history"),
    "inverted": os.path.join(BASE_DIR, "version-history-inverted"),
    "mac": os.path.join(BASE_DIR, "mac"),
}

# Deploy history endpoints
DEPLOY_HISTORY_URLS = {
    "Windows": "https://setup.rbxcdn.com/DeployHistory.txt",
    "Mac": "https://setup.rbxcdn.com/mac/DeployHistory.txt",
}

# ClientSettings endpoints
CLIENTSETTINGS_BASE = "https://clientsettingscdn.roblox.com/v2/client-version"

CLIENT_CHANNELS = [
    "",  # default
    "/channel/zbeta",
    "/channel/zliveforbeta",
]

# Regex
DEPLOY_PATTERN = re.compile(
    r"New (\w+) version-([a-f0-9]+|hidden).*?file ver(?:s)?ion:\s*([0-9,\s]+)",
    re.I,
)

# --- Ensure dirs exist ---
for path in PATHS.values():
    os.makedirs(path, exist_ok=True)

# --- Data stores ---
inverted_data = {}  # hash -> version (SOURCE OF TRUTH)
resolver_cache = {}  # (platform, bt) -> hash->version


# --- Slot rules ---
def get_slot_limit(bt):
    return 2 if bt in ("WindowsPlayer", "Studio64") else 1  # 2 because Luobu


# --- Utils ---
def fetch(url, as_text=False):
    try:
        r = requests.get(url, timeout=10)
        return r.text if as_text else r.json()
    except:
        return None


def normalize_binary(bt, platform):
    if bt.startswith("Studio"):
        return platform + bt
    if platform == "Mac" and bt == "Client":
        return "MacPlayer"
    return bt


def normalize_version(v):
    parts = [x.strip() for x in v.split(",") if x.strip()]
    if parts and parts[0].isdigit() and int(parts[0]) > 2000:
        parts[0] = "0"
    return ".".join(parts)


def version_key(v):
    return tuple(int(x) if x.isdigit() else 0 for x in v.split("."))


# --- PRELOAD ---
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
    else:
        hist_dir = os.path.join(PATHS["output"], platform)
        if os.path.exists(hist_dir):
            for file in os.listdir(hist_dir):
                if not file.endswith(".json"):
                    continue
                bt = file[:-5]
                path = os.path.join(hist_dir, file)
                try:
                    with open(path, "r") as f:
                        normal_versions = json.load(f)
                except:
                    continue

                inv_bt = inv_plat_data.setdefault(bt, {})
                for v, h in normal_versions.items():
                    inv_bt[h] = v


# --- Resolver ---
def get_resolver(platform, bt):
    key = (platform, bt)
    if key in resolver_cache:
        return resolver_cache[key]

    inv_bt_dict = inverted_data.get(platform, {}).get(bt, {})
    inv_resolver = dict(inv_bt_dict)

    lookup = normalize_binary(bt, platform)

    for suffix in CLIENT_CHANNELS:
        url = f"{CLIENTSETTINGS_BASE}/{lookup}{suffix}"
        js = fetch(url)
        if not js:
            continue

        print(url, js)

        v = js.get("version")
        h = js.get("clientVersionUpload")

        if v and h:
            full_hash = h if h.startswith("version-") else "version-" + h
            inv_resolver[full_hash] = v
            inv_bt_dict[full_hash] = v

    resolver_cache[key] = inv_resolver
    return inv_resolver


# --- MAIN ---
for platform, url in DEPLOY_HISTORY_URLS.items():
    txt = fetch(url, True)
    if not txt:
        continue

    inv_plat_data = inverted_data.setdefault(platform, {})

    lines = txt.split("\n")
    output_lines = []

    # Track usage per hash for hidden slots
    usage = {}

    for line in lines:
        m = DEPLOY_PATTERN.search(line)
        if not m:
            output_lines.append(line.rstrip("\n"))
            continue

        bt, h, raw_v = m.groups()
        v = normalize_version(raw_v)

        inv_bt_dict = inv_plat_data.setdefault(bt, {})
        inv_resolver = get_resolver(platform, bt)

        # explicit hash
        if h != "hidden":
            full_hash = h if h.startswith("version-") else "version-" + h
            inv_bt_dict[full_hash] = v
            inv_resolver[full_hash] = v

        # hidden resolution
        if h == "hidden":
            candidates = [hash_ for hash_, ver in inv_resolver.items() if ver == v]

            for hash_ in candidates:
                inv_bt_dict[hash_] = v

            limit = get_slot_limit(bt)
            for hash_ in candidates:
                key = (bt, v, hash_)
                used = usage.get(key, 0)
                if used < limit:
                    line = line.replace("version-hidden", hash_)
                    usage[key] = used + 1
                    break

        output_lines.append(line.rstrip("\n"))

    # write DeployHistory.txt
    path_txt = os.path.join(
        PATHS["mac"] if platform == "Mac" else BASE_DIR, "DeployHistory.txt"
    )

    with open(path_txt, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(output_lines))

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
        os.makedirs(os.path.dirname(path), exist_ok=True)

        sorted_versions = dict(
            sorted(versions.items(), key=lambda x: version_key(x[0]))
        )

        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                sorted_versions, f, indent=2, separators=(",", ": "), ensure_ascii=False
            )

# --- Write INVERTED JSON ---
for platform, binaries in inverted_data.items():
    for bt, hashes in binaries.items():
        path = os.path.join(PATHS["inverted"], platform, f"{bt}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        grouped = {}
        for h, v in hashes.items():
            grouped.setdefault(v, []).append(h)

        sorted_versions = sorted(grouped.keys(), key=version_key)

        ordered = {}
        for v in sorted_versions:
            for h in grouped[v]:
                ordered[h] = v

        with open(path, "w", encoding="utf-8") as f:
            json.dump(ordered, f, indent=2, separators=(",", ": "), ensure_ascii=False)
