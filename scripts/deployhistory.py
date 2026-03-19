import re, json, os, requests

# --- Paths ---
BASE_DIR = "output"
OUTPUT_DIR = os.path.join(BASE_DIR, "version-history")
MAC_DIR = os.path.join(BASE_DIR, "mac")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MAC_DIR, exist_ok=True)

# --- DeployHistory URLs ---
FILES = {
    "Windows": "https://setup.rbxcdn.com/DeployHistory.txt",
    "Mac": "https://setup.rbxcdn.com/mac/DeployHistory.txt",
}

pattern = re.compile(
    r"New (\w+) version-([a-f0-9]+|hidden).*?file version:\s*([0-9,\s]+)", re.I
)

data = {}


def fetch(url, astext=None):
    try:
        return (
            requests.get(url, timeout=10).text
            if astext
            else requests.get(url, timeout=10).json()
        )
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


for platform, url in FILES.items():
    txt = fetch(url, True)
    if not txt:
        continue
    data.setdefault(platform, {})

    # Save original DeployHistory.txt
    path_txt = os.path.join(
        MAC_DIR if platform == "Mac" else BASE_DIR, "DeployHistory.txt"
    )
    with open(path_txt, "w") as f:
        f.write(txt)

    for line in txt.splitlines():
        m = pattern.search(line)
        if not m or m.group(2) == "hidden":
            continue
        bt, version_hash, file_version_raw = m.groups()
        v = normalize_version(file_version_raw)
        data[platform].setdefault(bt, {})[v] = f"version-{version_hash}"

# --- Enrich with clientsettings ---
for platform, binaries in data.items():
    for bt, versions in binaries.items():
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
            if v and h and v not in versions:
                versions[v] = h


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

# --- Replace version-hidden in DeployHistory ---
for platform, url in FILES.items():
    path_txt = os.path.join(
        MAC_DIR if platform == "Mac" else BASE_DIR, "DeployHistory.txt"
    )

    with open(path_txt, "r") as f:
        lines = f.readlines()

    updated_lines = []
    for line in lines:
        m = pattern.search(line)
        if not m:
            updated_lines.append(line)
            continue
        bt, version_hash, file_version_raw = m.groups()
        v = normalize_version(file_version_raw)
        replacement_hash = data[platform].get(bt).get(v)
        if version_hash == "hidden" and replacement_hash:
            line = line.replace("version-hidden", replacement_hash + " ")
        updated_lines.append(line)

    with open(path_txt, "w") as f:
        f.write("".join(updated_lines))
