# Roblox DeployHistory Mapper & Archiver

This project fetches and processes Roblox **DeployHistory.txt** files for the Windows and Mac platforms, resolves hidden version hashes using the clientsettings API & Archives of it, and writes both normal and inverted JSON histories. Binaries that have no DeployHistory (currently `WebClientApp`) are tracked straight from the clientsettings API into the same JSON layout, plus `hash-metadata.json`.

## Mappings

| Source URL                                       | Published URL                                          |
| ------------------------------------------------ | ------------------------------------------------------ |
| `https://setup.rbxcdn.com/DeployHistory.txt`     | `https://setup-rbxcdn.github.io/DeployHistory.txt`     |
| `https://setup.rbxcdn.com/mac/DeployHistory.txt` | `https://setup-rbxcdn.github.io/mac/DeployHistory.txt` |

> **Note:** The published URLs are a direct mapping of the fetched DeployHistory files.

## Clientsettings-only binaries

`WebClientApp` has no `DeployHistory.txt`, so it is polled directly from
`https://clientsettingscdn.roblox.com/v2/client-version/WebClientApp` (default,
`zbeta` and `zliveforbeta` channels, like every other binary) and only
contributes JSON histories and hash metadata:

* `version-history/Web/WebClientApp.json`
* `version-history-inverted/Web/WebClientApp.json`
* `hash-metadata.json` -> `Web` -> `WebClientApp`

## Features

* **Hidden hash resolution**:
  Lines with `version-hidden` are replaced with the actual hash if it exists in the clientsettings API.

* **Supports duplicates**:
  Using **inverted-version-history** allows multiple hashes for the same file version (e.g., `0.715.1.7151119`), unlike standard version-history which overwrites duplicates.

* **Slot rules**:
  Some binaries like `WindowsPlayer` and `Studio64` allow multiple occurrences of the same version hash.

* **Lazy resolver**:
  Clientsettings API calls are made only when needed, and results are cached for efficiency.

* **JSON outputs**:

  * Normal: `version -> hash`
  * Inverted: `hash -> version` (ordered by version, allows duplicates)

* **Hash metadata**:
  `hash-metadata.json` records when each hash was first seen (`platform -> binary -> hash -> UTC timestamp`) and feeds hidden-hash timestamp matching.

* **Clientsettings-only tracking**:
  Binaries without a DeployHistory are polled through the same channel list and written only to the JSON histories and `hash-metadata.json`.

## Directory Structure

```
project-root/
├─ version-history-inverted/   # Inverted JSON outputs
│  ├─ Windows/
│  ├─ Mac/
│  └─ Web/
├─ version-history/   # JSON outputs
│  ├─ Windows/
│  ├─ Mac/
│  └─ Web/
├─ hash-metadata.json           # First-seen timestamps per hash
├─ mac/DeployHistory.txt        # Latest DeployHistory.txt for Mac
├─ DeployHistory.txt            # Latest DeployHistory.txt for Windows
└─ scripts/deployhistory.py     # Main script
```

> **Tip:** Prefer using `version-history-inverted` over `version-history` to retain all discovered hashes for a given version.

## Usage

1. Run the deployhistory script:

```bash
python scripts/deployhistory.py
```

2. Outputs:

* `DeployHistory.txt` for Windows/Mac
* `version-history` JSON files (version -> hash), including the clientsettings-only `Web/WebClientApp.json`
* `version-history-inverted` JSON files (hash -> version)
* `hash-metadata.json` (first-seen timestamps per hash)

## Notes

* The script automatically creates missing directories.
* Hidden hashes from `DeployHistory.txt` or clientsettings API will always be included in the inverted JSON.
* `WebClientApp` has no DeployHistory and therefore no history file; it only appears in the JSON histories and `hash-metadata.json`.
* Timestamps in `hash-metadata.json` are UTC.
* Normal JSON (`version -> hash`) may overwrite duplicates, so **use inverted JSON** if duplicates matter.

