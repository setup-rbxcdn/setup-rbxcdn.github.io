# Roblox DeployHistory Mapper & Archiver

This project fetches and processes Roblox **DeployHistory.txt** files for Windows and Mac platforms, resolves hidden version hashes using the clientsettings API & Archives of it, and writes both normal and inverted JSON histories.

## Mappings

| Source URL                                       | Published URL                                          |
| ------------------------------------------------ | ------------------------------------------------------ |
| `https://setup.rbxcdn.com/DeployHistory.txt`     | `https://setup-rbxcdn.github.io/DeployHistory.txt`     |
| `https://setup.rbxcdn.com/mac/DeployHistory.txt` | `https://setup-rbxcdn.github.io/mac/DeployHistory.txt` |

> **Note:** The published URLs are a direct mapping of the fetched DeployHistory files.

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

## Directory Structure

```
project-root/
├─ version-history-inverted/   # Inverted JSON outputs
│  ├─ Windows/
│  └─ Mac/
├─ version-history/   # JSON outputs
│  ├─ Windows/
│  └─ Mac/
├─ mac/DeployHistory.txt       # Latest DeployHistory.txt for Mac
├─ DeployHistory.txt           # Latest DeployHistory.txt for Windows
└─ scripts/deployhistory.py    # Main script
```

> **Tip:** Prefer using `version-history-inverted` over `version-history` to retain all discovered hashes for a given version.

## Usage

1. Run the deployhistory:

```bash
python deployhistory.py
```

2. Outputs:

* `DeployHistory.txt` for Windows/Mac
* `version-history` JSON files (version -> hash)
* `version-history-inverted` JSON files (hash -> version)

## Notes

* The script automatically creates missing directories.
* Hidden hashes from `DeployHistory.txt` or clientsettings API will always be included in the inverted JSON.
* Normal JSON (`version -> hash`) may overwrite duplicates, so **use inverted JSON** if duplicates matter.

