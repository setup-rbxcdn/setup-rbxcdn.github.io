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


# --- Resolver builder (lazy) ---
def get_resolver(platform, bt):
    key = (platform, bt)
    if key in resolver_cache:
        return resolver_cache[key]

    resolver = {}

    # 1. Load GH-pages JSON (historical)
    path = os.path.join(OUTPUT_DIR, platform, f"{bt}.json")
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                resolver.update(json.load(f))
        except:
            pass

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
            resolver[v] = h

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

        # --- Resolve hidden inline ---
        if h == "hidden":
            resolved = resolver.get(v)
            if resolved:
                line = line.replace("version-hidden", resolved)
                h = resolved.replace("version-", "")

        # --- Store if known ---
        if h != "hidden":
            full_hash = "version-" + h
            bt_dict[v] = full_hash

            # update resolver dynamically (important)
            resolver[v] = full_hash

        output_lines.append(line)

    # write DeployHistory (already resolved)
    path_txt = os.path.join(
        MAC_DIR if platform == "Mac" else BASE_DIR, "DeployHistory.txt"
    )
    with open(path_txt, "w") as f:
        f.write("".join(output_lines))


# --- Write JSON output ---
for platform, binaries in data.items():
    for bt, versions in binaries.items():
        path = os.path.join(OUTPUT_DIR, platform, f"{bt}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w") as f:
            json.dump(
                dict(sorted(versions.items(), key=lambda x: version_key(x[0]))),
                f,
                indent=2,
            )
