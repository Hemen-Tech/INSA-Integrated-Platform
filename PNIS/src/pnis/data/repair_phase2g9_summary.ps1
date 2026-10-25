
$ErrorActionPreference = "Stop"

$processed = Join-Path (Get-Location) "data\processed"
$summaryPath = Join-Path $processed "phase2g9_artifact_consistency_summary.csv"
$auditPath = Join-Path $processed "phase2g9_artifact_consistency_audit.txt"
$issuesPath = Join-Path $processed "phase2g9_artifact_consistency_issues.csv"

$inputs = @(
    "phase2g1_candidate_road_proximity_register.csv",
    "phase2g2_access_review_register.csv",
    "phase2g4_candidate_road_access_review_register_v2.csv",
    "phase2g5_candidate_access_risk_register_v2.csv",
    "phase2g6_field_verification_worklist.csv",
    "phase2g6_evidence_register.csv",
    "phase2g7_field_observation_register.csv",
    "phase2g8_candidate_review_checklist.csv"
)

$summary = [System.Collections.Generic.List[object]]::new()
$issues = [System.Collections.Generic.List[object]]::new()
$loaded = @{}

foreach ($file in $inputs) {
    $path = Join-Path $processed $file

    if (-not (Test-Path -LiteralPath $path)) {
        $issues.Add([PSCustomObject]@{
            File = $file
            Issue = "INPUT_FILE_MISSING"
            Details = $path
        })
        continue
    }

    $rows = @(Import-Csv -LiteralPath $path)
    $loaded[$file] = $rows

    if ($rows.Count -eq 0) {
        $issues.Add([PSCustomObject]@{
            File = $file
            Issue = "INPUT_EMPTY"
            Details = "No data rows were imported."
        })
    }

    $ids = @(
        $rows | ForEach-Object {
            if ($null -ne $_.PSObject.Properties["candidate_record_id"]) {
                ([string]$_.candidate_record_id).Trim()
            } else {
                ""
            }
        }
    )

    $nonblank = @($ids | Where-Object { $_ -ne "" })
    $unique = @($nonblank | Sort-Object -Unique)
    $duplicateRows = $nonblank.Count - $unique.Count
    $blankCount = $ids.Count - $nonblank.Count

    $summary.Add([PSCustomObject]@{
        File = $file
        Rows = $rows.Count
        UniqueIDs = $unique.Count
        BlankIDs = $blankCount
        DuplicateIDRows = $duplicateRows
    })

    if ($rows.Count -ne 255) {
        $issues.Add([PSCustomObject]@{
            File = $file
            Issue = "ROW_COUNT_NOT_255"
            Details = "Found $($rows.Count) rows."
        })
    }

    if ($blankCount -gt 0) {
        $issues.Add([PSCustomObject]@{
            File = $file
            Issue = "BLANK_CANDIDATE_ID"
            Details = "$blankCount blank IDs."
        })
    }

    if ($duplicateRows -gt 0) {
        $issues.Add([PSCustomObject]@{
            File = $file
            Issue = "DUPLICATE_CANDIDATE_ID"
            Details = "$duplicateRows duplicate ID rows."
        })
    }

    foreach ($row in $rows) {
        foreach ($column in @("routing_eligible", "phase2g3_routing_eligible")) {
            if ($row.PSObject.Properties.Name -contains $column) {
                $value = ([string]$row.$column).Trim().ToUpperInvariant()

                if ($value -notin @("NO", "FALSE", "0")) {
                    $issues.Add([PSCustomObject]@{
                        File = $file
                        Issue = "ROUTING_SAFEGUARD_REQUIRES_REVIEW"
                        Details = "Column $column has value '$value' for candidate '$($row.candidate_record_id)'."
                    })
                }
            }
        }
    }
}

# Compare candidate IDs against the Phase 2G.6 worklist.
$baselineFile = "phase2g6_field_verification_worklist.csv"

if ($loaded.ContainsKey($baselineFile)) {
    $baselineIDs = @(
        $loaded[$baselineFile] |
        ForEach-Object { ([string]$_.candidate_record_id).Trim() } |
        Where-Object { $_ -ne "" } |
        Sort-Object -Unique
    )

    foreach ($file in $loaded.Keys) {
        $otherIDs = @(
            $loaded[$file] |
            ForEach-Object { ([string]$_.candidate_record_id).Trim() } |
            Where-Object { $_ -ne "" } |
            Sort-Object -Unique
        )

        $missing = @($baselineIDs | Where-Object { $_ -notin $otherIDs })
        $extra = @($otherIDs | Where-Object { $_ -notin $baselineIDs })

        if ($missing.Count -gt 0 -or $extra.Count -gt 0) {
            $issues.Add([PSCustomObject]@{
                File = $file
                Issue = "CANDIDATE_ID_SET_MISMATCH"
                Details = "Missing from file: $($missing.Count); extra in file: $($extra.Count)."
            })
        }
    }
}

# Recount field observations; this is descriptive, not a routing approval.
$observationCount = 0
$observationFile = "phase2g7_field_observation_register.csv"

if ($loaded.ContainsKey($observationFile)) {
    foreach ($row in $loaded[$observationFile]) {
        $visitDate = ""
        $observer = ""

        if ($row.PSObject.Properties.Name -contains "field_visit_date") {
            $visitDate = ([string]$row.field_visit_date).Trim()
        }

        if ($row.PSObject.Properties.Name -contains "observer_name") {
            $observer = ([string]$row.observer_name).Trim()
        }

        if ($visitDate -ne "" -or $observer -ne "") {
            $observationCount++
        }
    }
}

# Always write a complete summary in the declared input order.
$summary | Export-Csv -LiteralPath $summaryPath -NoTypeInformation -Encoding UTF8

if ($issues.Count -gt 0) {
    $issues | Export-Csv -LiteralPath $issuesPath -NoTypeInformation -Encoding UTF8
} else {
    @([PSCustomObject]@{
        File = ""
        Issue = ""
        Details = ""
    }) | Export-Csv -LiteralPath $issuesPath -NoTypeInformation -Encoding UTF8
}

$lines = @(
    "PNIS PHASE 2G.9 - ARTIFACT CONSISTENCY AUDIT",
    "Generated UTC: $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))",
    "Expected candidate population: 255",
    "Successfully loaded input files: $($loaded.Count) of $($inputs.Count)",
    "Summary rows written: $($summary.Count)",
    "Field observation records with visit date or observer entered: $observationCount",
    "Issue records: $($issues.Count)",
    "",
    "INPUT SUMMARY",
    "------------------------------------------------------------"
)

foreach ($item in $summary) {
    $lines += "$($item.File) | rows=$($item.Rows) | unique_ids=$($item.UniqueIDs) | blank_ids=$($item.BlankIDs) | duplicate_id_rows=$($item.DuplicateIDRows)"
}

$lines += "------------------------------------------------------------"

if ($issues.Count -eq 0 -and $loaded.Count -eq $inputs.Count -and $summary.Count -eq $inputs.Count) {
    $lines += "Status: PASS - all eight inputs summarized; defined checks found no issues."
} else {
    $lines += "Status: REVIEW REQUIRED - inspect the issues CSV and missing input/summary rows."
}

$lines += ""
$lines += "LIMITATION: This audit does not establish real-world facility access or approve routing."
$lines | Set-Content -LiteralPath $auditPath -Encoding UTF8

Write-Host ""
Write-Host "PHASE 2G.9 SUMMARY REPAIR FINISHED"
Write-Host "Inputs loaded: $($loaded.Count) / $($inputs.Count)"
Write-Host "Summary rows: $($summary.Count) / $($inputs.Count)"
Write-Host "Issues found: $($issues.Count)"
Write-Host "Summary: $summaryPath"
Write-Host "Audit: $auditPath"
Write-Host "Issues: $issuesPath"
