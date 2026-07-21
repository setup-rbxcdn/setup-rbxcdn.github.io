import re
import requests

INCLUDE_STUDIO = False  # set True to include binaries with "studio" in the name

URLS = {
    "Windows": "https://setup-rbxcdn.github.io/DeployHistory.txt",
    "Mac": "https://setup-rbxcdn.github.io/mac/DeployHistory.txt",
}

# Captures: binary type, version-hidden marker, file version numbers
HIDDEN_PATTERN = re.compile(
    r"New (\w+) version-hidden at [\d/]+ [\d:]+ [AP]M, file version:\s*([0-9,\s]+)",
    re.I,
)


def fetch(url):
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"Fetch error {url}: {e}")
        return None


def normalize_file_version(raw):
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return ".".join(parts)


def main():
    seen = set()  # (platform, bt, file_version) to dedupe across both files

    for platform, url in URLS.items():
        text = fetch(url)
        if not text:
            continue

        for line in text.splitlines():
            m = HIDDEN_PATTERN.search(line)
            if not m:
                continue

            bt, raw_ver = m.groups()

            if not INCLUDE_STUDIO and "studio" in bt.lower():
                continue

            file_ver = normalize_file_version(raw_ver)
            key = (platform, bt, file_ver)

            if key in seen:
                continue
            seen.add(key)

            print(f"{bt} version-hidden {file_ver}")


if __name__ == "__main__":
    main()