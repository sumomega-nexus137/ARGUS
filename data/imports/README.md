# data/imports — drop-in location for real data

* `validation/<area_id>/<dataset_id>/` — historical validation masks (see `validation/README.md`).
* Tabular imports (resources, facilities, observations, road events) are uploaded through the UI
  (Data & input → Imports) or `POST /api/areas/{area}/imports?import_type=…`; templates are served at
  `/api/imports/templates/{type}.csv`.

Contents of this folder (except the READMEs) are git-ignored. Contracts: `docs/DATA_CONTRACTS.md`.
