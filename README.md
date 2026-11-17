# Bellevue building stock explorer

Research inventory and GIS explorer for Bellevue, Washington's building decarbonization study.

## Get the map

Open **Actions → Build building inventory**. The workflow runs on a push to main, and can also be run manually. Download **bellevue-building-explorer**, extract the ZIP, and open **index.html** in a browser. The HTML embeds the retrieved data; no local server is needed. Internet access is needed for Leaflet and OpenStreetMap tiles. This repository does not automatically enable GitHub Pages or publish a live site.

The artifact includes:
- Interactive map with building-use, construction-era, address/parcel, and permit-keyword filters.
- Building footprint GeoJSON.
- Assessor inventory JSON and CSV when Assessor records can be retrieved and matched.
- Parcel-associated permit records for inventoried Assessor properties, with project descriptions and status.
- A source report with retrieval dates, source availability, counts, schema and warnings.

A successful workflow can still produce a **partial inventory**. Read source_report.json and the map's Sources & methods panel. Unavailable Assessor data leaves footprints explicitly unclassified. No synthetic buildings, energy measurements, fuel assumptions or compliance results are used.

## Data sources

1. **City of Bellevue Buildings**: https://services1.arcgis.com/EYzEZbDhXZjURPbP/arcgis/rest/services/Buildings/FeatureServer/0
2. **City of Bellevue Parcels**: https://services1.arcgis.com/EYzEZbDhXZjURPbP/arcgis/rest/services/City_of_Bellevue_Parcels/FeatureServer
3. **City Limits**: https://services1.arcgis.com/EYzEZbDhXZjURPbP/arcgis/rest/services/City_Limits/FeatureServer
4. **Bellevue Permits** (unfiltered service, not active-status-only view): https://services1.arcgis.com/EYzEZbDhXZjURPbP/arcgis/rest/services/Bellevue_Permits/FeatureServer/0
5. **King County Assessor downloads**: https://info.kingcounty.gov/assessor/DataDownload/default.aspx
6. **Commerce Clean Buildings portal and public dashboard link**: https://www.commerce.wa.gov/cbps/portal/

The builder discovers the public Assessor download links after the site's public-use acknowledgement and attempts commercial-building, apartment-complex and building-section downloads. It never authenticates to restricted GIS or Commerce accounts. Failure is recorded rather than replaced with fabricated attributes.

For a local build, official Assessor CSV files can be placed at inputs/commercial.csv, inputs/apartments.csv and inputs/sections.csv. These local inputs are gitignored. Only the named official datasets are supported; schema checks stop unexpected data. The public commercial ZIP includes building, section and feature CSVs; the importer selects the building and section members separately. Raw download headers differ from the GIS catalog: Address maps to the inventory address, NbrUnits supplies apartment-complex units, and Bellevue ParcelAFN is the county PIN (LISParcelI is an internal ID).

## Commerce data

Building-level compliance and benchmarking submissions are not assumed to be available in the public dashboard. This project does not scrape protected portals.

inputs/commerce_template.csv shows the optional input format. Supply inputs/commerce.csv locally with a reviewed inventory_id crosswalk (parcel PIN + ":" + Assessor building number). Rows must have a unique, existing inventory_id. It is intentionally not a loose address or parcel-only join. Document the source/release date and reporting year. The build includes only supplied results and never marks missing reports noncompliant. Do not commit restricted or unreleased records to this public repository.

## Methods and present limits

- ArcGIS retrieval first obtains all object IDs, downloads batches, and verifies the count. The city boundary is required; failed boundary retrieval stops the build.
- Only footprints intersecting the city boundary are mapped. Parcel boundaries support geographic selection of Assessor records; boundary-straddling parcels need review.
- Parcel identifiers are strings with leading zeros. Assessor inventory keys combine PIN and building number, with duplicate detection.
- A footprint receives a parcel association at >=90% area overlap, with no competing parcel >=10%. The area ratio uses geographic coordinates solely for local overlap matching, not floor-area measurement.
- A footprint inherits use only when all linked parcel records agree on the category. This is a parcel association, not a verified match to one assessed building.
- Assessor sections help flag mixed-use buildings. Parking stays separate.
- Apartment-complex unit counts remain at parcel/complex scope and are not summed across buildings.
- Permit evidence is associated at parcel level. Keywords flag heat pump/HVAC/boiler/furnace/water heating/electrification/solar/insulation work for review; neither issuance nor a keyword proves completed installation.
- The permit overlay places a marker at an associated footprint center, explicitly labelled approximate. It does not claim precise equipment or permit coordinates.
- Heating system is not universally heating fuel. Missing fuel and energy data remain null.
- State coverage/tier is not inferred from unadjusted Assessor gross area.
- Condominium complexes, small multifamily (2–3 units), campuses, aggregated buildings and ambiguous footprint matches require further reconciliation. This is not yet a certified complete commercial/multifamily stock.
- Floor area is not summed across footprint joins, which could duplicate building records. Filtered CSV deduplicates inventory IDs.
- Permit source history is whatever the live service returns; source-report metadata and retrieved records must be inspected before claiming a 1998–present history.

## Run locally

Requires Python 3.11+.

    pip install -r requirements.txt
    python -m unittest discover -s tests -v
    python scripts/build_inventory.py

Open output/index.html. Optional source failures are visible in the artifact; failure of the required boundary or building layer stops the workflow.

## Development

No API keys or credentials are embedded. Workflow permissions are read-only; outputs are workflow artifacts, not automatic commits. There is no recurring schedule. Any later public deployment should be based on an inspected build.
