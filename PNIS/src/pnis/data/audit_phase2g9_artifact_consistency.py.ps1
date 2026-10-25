
$ErrorActionPreference = "Stop"
Set-Location "C:\Users\tadesse.yilma\projects\PNIS"

$processed = ".\data\processed"

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

$expected = 255
$loaded = @{}
$results = @()
$issues = @()

foreach ($file in $inputs) {
    $path = Join-Path $processed $file

    if (!(Test-Path $path)) {
        $issues += [PSCustomObject]@{
            File = $file
            Issue = "MISSING_FILE"
            Details = "Expected input file was not found."
        }
        continue
    }

    $rows = @(Import-Csv $path)
    $loaded[$file] = $rows

    if ($rows.Count -eq 0) {
        $issues += [PSCustomObject]@{
            File = $file
            Issue = "EMPTY_FILE"
            Details = "CSV has no data rows."
        }
        continue
    }

    $columns = @($rows[0].PSObject.Properties.Name)

    if ($columns -notcontains "candidate_record_id") {
        $issues += [PSCustomObject]@{
            File = $file
            Issue = "MISSING_ID_COLUMN"
            Details = "candidate_record_id column is absent."
        }
        continue
    }

    $ids = @($rows | ForEach-Object {
        ([string]$_.candidate_record_id).Trim()
    })

    $nonblank = @($ids | Where-Object { $_ -ne "" })
    $unique = @($nonblank | Sort-Object -Unique)

    $results += [PSCustomObject]@{
        File = $file
        Rows = $rows.Count
        UniqueIDs = $unique.Count
        BlankIDs = $ids.Count - $nonblank.Count
        DuplicateIDRows = $nonblank.Count - $unique.Count
        Expected255Rows = ($rows.Count -eq $expected)
        Expected255UniqueIDs = ($unique.Count -eq $expected)
    }

    if ($rows.Count -ne $expected) {
        $issues += [PSCustomObject]@{
            File = $file
            Issue = "ROW_COUNT_MISMATCH"
            Details = "Expected $expected rows; found $($rows.Count)."
        }
    }

    if ($unique.Count -ne $expected -or $ids.Count -ne $nonblank.Count) {
        $issues += [PSCustomObject]@{
            File = $file
            Issue = "ID_QUALITY"
            Details = "Unique or nonblank candidate IDs do not equal 255."
        }
    }
}

# Compare candidate ID sets across every successfully loaded register.
$baselineFile = "phase2g6_field_verification_worklist.csv"
$baselineIDs = @()

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
            $issues += [PSCustomObject]@{
                File = $file
                Issue = "CANDIDATE_ID_SET_MISMATCH"
                Details = "Missing from file: $($missing.Count); extra in file: $($extra.Count)."
            }
        }
    }
}

# Check routing safeguards wherever an explicit routing column exists.
foreach ($file in $loaded.Keys) {
    foreach ($row in $loaded[$file]) {
        foreach ($column in @("routing_eligible", "phase2g3_routing_eligible")) {
            if ($row.PSObject.Properties.Name -contains $column) {
                $value = ([string]$row.$column).Trim().ToUpperInvariant()

                if ($value -notin @("NO", "FALSE", "0", "")) {
                    $issues += [PSCustomObject]@{
                        File = $file
                        Issue = "ROUTING_SAFEGUARD_REVIEW"
                        Details = "Candidate $($row.candidate_record_id): $column=$value"
                    }
                }
            }
        }
    }
}

# Count completed field observations; blank/pending records are not failures.
$observationFile = "phase2g7_field_observation_register.csv"
$observationCount = 0

if ($loaded.ContainsKey($observationFile)) {
    $obs = $loaded[$observationFile]

    foreach ($row in $obs) {
        $visitDate = ([string]$row.field_visit_date).Trim()
        $observer = ([string]$row.observer_name_or_id).Trim()

        if ($visitDate -ne "" -or $observer -ne "") {
            $observationCount++
        }
    }
}

$summaryPath = Join-Path $processed "phase2g9_artifact_consistency_summary.csv"
$issuesPath = Join-Path $processed "phase2g9_artifact_consistency_issues.csv"
$auditPath = Join-Path $processed "phase2g9_artifact_consistency_audit.txt"

$results | Export-Csv $summaryPath -NoTypeInformation -Encoding UTF8

if ($issues.Count -gt 0) {
    $issues | Export-Csv $issuesPath -NoTypeInformation -Encoding UTF8
} else {
    @([PSCustomObject]@{
        File = ""
        Issue = "NONE"
        Details = "No consistency issues detected by these checks."
    }) | Export-Csv $issuesPath -NoTypeInformation -Encoding UTF8
}

$failed = @($issues | Where-Object {
    $_.Issue -ne "NONE"
}).Count

$lines = @(
    "PNIS PHASE 2G.9 - ARTIFACT CONSISTENCY AUDIT"
    "============================================================"
    "Generated UTC: $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))"
    "Expected candidate population: $expected"
    "Successfully loaded input files: $($loaded.Count) of $($inputs.Count)"
    "Field observation records with visit date or observer entered: $observationCount"
    "Issue records: $failed"
    ""
    "INPUT SUMMARY"
    "------------------------------------------------------------"
)

foreach ($item in $results) {
    $lines += "$($item.File) | rows=$($item.Rows) | unique_ids=$($item.UniqueIDs) | blank_ids=$($item.BlankIDs) | duplicate_id_rows=$($item.DuplicateIDRows)"
}

$lines += ""
$lines += "INTERPRETATION"
$lines += "------------------------------------------------------------"

if ($failed -eq 0 -and $loaded.Count -eq $inputs.Count) {
    $lines += "Status: PASS - no issues detected by the defined checks."
} else {
    $lines += "Status: REVIEW REQUIRED - inspect the issues CSV."
}

$lines += "This audit does not establish real-world facility access or approve routing."
$lines += "Existing input files were read only; audit outputs use new Phase 2G.9 filenames."

$lines | Set-Content $auditPath -Encoding UTF8

Write-Host ""
Write-Host "PHASE 2G.9 AUDIT FINISHED"
Write-Host "Inputs loaded: $($loaded.Count) / $($inputs.Count)"
Write-Host "Issues found: $failed"
Write-Host "Observation records with visit date or observer: $observationCount"
Write-Host $summaryPath
Write-Host $issuesPath
Write-Host $auditPath
