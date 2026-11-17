# Bellevue building stock: first populated baseline

Built November 16, 2026 (Pacific time). [Verified workflow run](https://github.com/jakesy11/cob_buildings/actions/runs/43990613579).

[Download the map and data package](https://github.com/jakesy11/cob_buildings/actions/runs/43990613579/artifacts/14287047217). Extract the ZIP and open index.html. This is a downloadable interactive map, not a deployed public website. Workflow artifacts are retained for 30 days; the repository workflow can rebuild them.

## Retrieved and linked results

| Assessor category | Assessor records | Associated mapped footprints | Reported gross floor area, sq ft |
|---|---:|---:|---:|
| Commercial / institutional | 1,870 | 2,786 | 81,648,685 |
| Multifamily | 279 | 1,902 | 17,754,069 |
| Mixed-use | 84 | 296 | 16,541,293 |
| Parking | 32 | 14 | 10,946,128 |
| Residential requiring review | 22 | 18 | 83,562 |

There are 2,287 Assessor inventory records. The default commercial/multifamily/mixed-use map selection displays 4,984 footprints. A footprint is not equivalent to an assessed building: some Assessor records aggregate several buildings, while some physical structures cannot be confidently linked. The full reference layer contains 50,570 footprints intersecting Bellevue, including 45,554 without a linked commercial/apartment classification. Unclassified footprints are not automatically commercial; many are outside the study's target uses.

The map has parcel associations to 2,179 distinct inventory IDs. Another 108 records remain in the exported inventory without a confident footprint association. Parcels that straddle city boundaries also require review.

Reported gross floor area is taken from Assessor records and is not a calculation of state covered floor area, conditioned floor area, or usable residential space. It has not been adjusted for parking and should not be used directly to assign state compliance tiers.

## Permit and attribute coverage

- 182,327 source permit records match parcels with inventory records. These are records, not a deduplicated count of completed retrofits.
- 2,254 inventory records have an address; 33 lack one.
- 347 records carry apartment-complex/parcel unit information. These values must not be added across building records.
- 93 records have no recorded heating-system category. Heating fuel remains unknown throughout the commercial baseline because system descriptions do not consistently establish fuel.
- No Commerce building-level energy results or compliance submissions have been obtained. There are zero imported EUI results.

## Source findings that affected implementation

| Source field or file | Interpretation |
|---|---|
| Bellevue ParcelAFN | County parcel identifier used to join sources |
| Bellevue LISParcelI | Internal city identifier; not used as a county parcel number |
| County Address | Address field in the raw commercial CSV |
| County NbrUnits | Apartment-complex unit count in the raw CSV |
| Commercial Building.zip | Contains EXTR_CommBldg.csv, EXTR_CommBldgSection.csv and EXTR_CommBldgFeature.csv |
| Building sections | Supports identification of multiple uses in assessed buildings |
| Bellevue permit PARCELNUMBER | Parcel association only; individual building association remains unverified |
| Permit keyword flag | Evidence for review, not proof that installation was completed |

The pipeline verifies ArcGIS batch IDs against the initial ID list. It includes a footprint-to-parcel association only when at least 90% of the footprint overlaps one parcel and no competing parcel overlaps 10% or more. A footprint receives a use category only when linked Assessor records agree. Exact building-to-footprint matching remains unverified.

## Validation

Six record-integrity tests passed. JavaScript syntax passed. Chromium checks passed for rendering, empty and known-address searches, reset, source dialog, footprint popups, CSV download, and mobile controls. These are functional checks, not a visual design review or certification of source completeness.

## Work still required for a complete study inventory

1. Reconcile condominium complexes and small multifamily properties using the additional public Assessor tables; they are not fully covered by the commercial/apartment baseline.
2. Review ambiguous, aggregated, boundary-straddling and unmatched building records and footprints.
3. Obtain an appropriate Commerce building-level export and establish a reviewed crosswalk to Assessor building records before importing compliance or energy attributes.
4. Review permit completion evidence and individual-building applicability before treating a project as an installed measure.
5. Confirm lifecycle status, recent demolitions/new construction, affordable housing status, equipment/fuel and other missing study attributes through additional sources.

Source snapshots and details are included in source_report.json inside the package. This baseline supports exploration and data reconciliation; it is not yet a complete inventory of every commercial and multifamily building in Bellevue.
