import re, json, os, requests

# --- Paths ---
BASE_DIR = "output"
OUTPUT_DIR = os.path.join(BASE_DIR, "version-history")
MAC_DIR = os.path.join(BASE_DIR, "mac")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MAC_DIR, exist_ok=True)

FILES = {
    "Windows": "https://setup.rbxcdn.com/DeployHistory.txt",
    "Mac": "https://setup.rbxcdn.com/mac/DeployHistory.txt",
}

pattern = re.compile(
    r"New (\w+) version-([a-f0-9]+|hidden).*?file ver(?:s)?ion:\s*([0-9,\s]+)",
    re.I,
)

data = {}
resolver_cache = {}  # (platform, bt) -> {version: hash}


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


# --- PRELOAD EXISTING JSON (CRITICAL: prevents deletions) ---
for platform in FILES.keys():
    plat_dir = os.path.join(OUTPUT_DIR, platform)
    if not os.path.exists(plat_dir):
        continue

    plat_data = data.setdefault(platform, {})

    for file in os.listdir(plat_dir):
        if not file.endswith(".json"):
            continue

        bt = file[:-5]
        path = os.path.join(plat_dir, file)

        try:
            with open(path, "r") as f:
                existing = json.load(f)
        except:
            continue

        bt_dict = plat_data.setdefault(bt, {})
        bt_dict.update(existing)


# --- Resolver builder (lazy) ---
def get_resolver(platform, bt):
    key = (platform, bt)
    if key in resolver_cache:
        return resolver_cache[key]

    resolver = {}

    # 1. Load from preloaded JSON (persistent memory)
    existing_bt = data.get(platform, {}).get(bt, {})
    resolver.update(existing_bt)

    # 2. Fetch clientsettings (latest)
    lookup = normalize_binary(bt, platform)
    for url in [
        f"https://clientsettings.roblox.com/v2/client-version/{lookup}",
        f"https://clientsettings.roblox.com/v2/client-version/{lookup}/channel/zbeta",
    ]:
        js = fetch(url)
        if not js:
            continue

        v = js.get("version")
        h = js.get("clientVersionUpload")
        if v and h:
            resolver[v] = h if h.startswith("version-") else "version-" + h

    resolver_cache[key] = resolver
    return resolver


# --- MAIN ---
for platform, url in FILES.items():
    txt = fetch(url, True)
    if not txt:
        continue

    plat_data = data.setdefault(platform, {})
    output_lines = []

    for line in txt.splitlines(True):
        m = pattern.search(line)
        if not m:
            output_lines.append(line)
            continue

        bt, h, raw_v = m.groups()
        v = normalize_version(raw_v)

        bt_dict = plat_data.setdefault(bt, {})
        resolver = get_resolver(platform, bt)

        existing_hash = resolver.get(v) or bt_dict.get(v)

        # --- Resolve hidden safely (NO REGRESSION) ---
        if h == "hidden":
            if existing_hash:
                line = line.replace("version-hidden", existing_hash)
                h = existing_hash.replace("version-", "")

        # --- Store safely (append-only) ---
        if h != "hidden":
            full_hash = h if h.startswith("version-") else "version-" + h

            # only add if new OR same (never overwrite different)
            if v not in bt_dict or bt_dict[v] == full_hash:
                bt_dict[v] = full_hash
                resolver[v] = full_hash

        output_lines.append(line)

    # --- Write DeployHistory ---
    path_txt = os.path.join(
        MAC_DIR if platform == "Mac" else BASE_DIR, "DeployHistory.txt"
    )
    with open(path_txt, "w", encoding="utf-8") as f:
        f.write("".join(output_lines))


# --- Write JSON output (stable + append-only) ---
for platform, binaries in data.items():
    for bt, versions in binaries.items():
        path = os.path.join(OUTPUT_DIR, platform, f"{bt}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        sorted_versions = dict(
            sorted(versions.items(), key=lambda x: version_key(x[0]))
        )

        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                sorted_versions,
                f,
                indent=2,
                separators=(",", ": "),
                ensure_ascii=False,
            )
