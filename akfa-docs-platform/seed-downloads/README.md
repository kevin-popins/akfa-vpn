# AKFA Docs Seed Downloads

Put initial public client downloads in this directory and describe them in
`downloads.manifest.json`.

The installer copies manifest entries into `DOWNLOADS_DIR`, normally
`/opt/akfa-downloads`, using each entry's stable `filename`. Existing files are
not overwritten during update unless `OVERWRITE_SEED_DOWNLOADS=yes` is set.

Large binaries may be better stored with Git LFS or release assets, but the
manifest should stay in git so public article links remain stable.

