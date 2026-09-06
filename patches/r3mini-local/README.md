# R3 Mini compatibility patches

The authoritative selected-source lock is
[`../r3mini-sources/sources.json`](../r3mini-sources/sources.json).
It records upstream URLs, exact commits and SHA-256 hashes of the complete
local patches, including new files. Do not add nested package directories as
Git links to the top-level repository.

From a fresh top-level checkout, run:

```sh
python3 scripts/r3mini-prepare.py --bootstrap --restore-config
```

This fetches missing pinned sources, checks existing revisions, reapplies
compatibility patches, indexes the selected feeds without updating their
branches, installs their package links and checks the saved profile. It never
resets existing work. On an already prepared tree, omit `--bootstrap`.

After reviewing deliberate source updates, regenerate the selected-source
patches with `python3 scripts/r3mini-sources.py snapshot`. Source archives and
ARM64 prebuilt downloads remain described by their package recipes and hashes;
they are not embedded in this commit.

The older topical patches in `../r3mini/` are audit references and are already
included in the complete source patches. Do not apply both sets.

`../r3mini-unselected/` preserves fixes made during investigation to UA-Mask,
UA3F, the competing modem manager and the unused standalone Onliner checkout.
These sources are excluded from the saved profile and are not fetched or
installed by the default bootstrap. Their manifest records the matching base
revisions if they need separate review later.
