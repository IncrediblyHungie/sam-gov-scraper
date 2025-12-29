# SAM.gov Federal Contract Scraper with Attachments

The **only** Apify actor that downloads actual RFP documents, SOWs, and attachments from federal contract opportunities on SAM.gov.

**NO API KEY REQUIRED** - Uses SAM.gov's internal API endpoints.

## Features

- **No API Key Needed**: Works out of the box, no SAM.gov registration required
- **Full Opportunity Data**: Title, description, deadlines, agency, NAICS, contacts, set-asides
- **Attachment Download**: Downloads all RFPs, SOWs, pricing templates, and other documents
- **PDF Text Extraction**: Optionally extract text from PDFs for searching/analysis
- **Flexible Filtering**: Filter by NAICS codes, keywords, set-aside types, states, opportunity types
- **Bulk Export**: Export to JSON, CSV, or Excel

## Why This Actor?

Other SAM.gov scrapers only give you metadata. This actor downloads the **actual documents** that contain:
- Detailed requirements and specifications
- Pricing templates and rate structures
- Statement of Work (SOW) details
- Evaluation criteria
- Contract terms and conditions

## Input Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `keywords` | string | No | - | Search keywords |
| `naicsCodes` | array | No | [] | NAICS codes to filter |
| `postedWithinDays` | integer | No | 30 | Days to look back |
| `setAsideTypes` | array | No | [] | Set-aside filters (SBA, 8A, HUBZone, etc.) |
| `states` | array | No | [] | State filters (CA, TX, VA, etc.) |
| `opportunityTypes` | array | No | [] | Type filters (o, k, p, r, s, g) |
| `downloadAttachments` | boolean | No | true | Download RFPs and documents |
| `extractText` | boolean | No | false | Extract text from PDFs |
| `maxOpportunities` | integer | No | 100 | Maximum results |

## Output Example

```json
{
    "opportunityId": "abc123def456",
    "solicitationNumber": "W912HQ-24-R-0001",
    "title": "IT Support Services",
    "description": "<p>Seeking IT support for...</p>",
    "type": "Solicitation",
    "typeCode": "o",
    "postedDate": "2024-01-15T12:00:00+00:00",
    "responseDeadline": "2024-02-15T14:00:00-05:00",
    "responseTimeZone": "America/New_York",
    "naicsCode": "541512",
    "pscCode": "D301",
    "setAsideType": "SBA",
    "setAsideDescription": "Total Small Business Set-Aside",
    "agencyName": "DEPT OF DEFENSE",
    "subAgencyName": "DEPT OF THE ARMY",
    "officeName": "W6QK ACC-APG",
    "placeOfPerformance": {
        "city": "ABERDEEN PROVING GROUND",
        "state": "Maryland",
        "stateCode": "MD",
        "country": "UNITED STATES",
        "countryCode": "USA"
    },
    "contacts": [
        {
            "name": "John Smith",
            "email": "john.smith@army.mil",
            "phone": "555-123-4567",
            "type": "primary"
        }
    ],
    "attachments": [
        {
            "filename": "RFP_IT_Support.pdf",
            "type": ".pdf",
            "size": 1234567,
            "resourceId": "xyz789",
            "storageKey": "abc123def456/RFP_IT_Support.pdf",
            "downloadedSize": 1234567
        }
    ],
    "samGovLink": "https://sam.gov/opp/abc123def456/view"
}
```

## NAICS Codes Reference

| Code | Description |
|------|-------------|
| 541511 | Custom Computer Programming Services |
| 541512 | Computer Systems Design Services |
| 541519 | Other Computer Related Services |
| 518210 | Data Processing & Hosting |
| 541690 | Scientific & Technical Consulting |
| 541330 | Engineering Services |

## Opportunity Type Codes

| Code | Description |
|------|-------------|
| o | Solicitation |
| k | Combined Synopsis/Solicitation |
| p | Presolicitation |
| r | Sources Sought |
| s | Special Notice |
| g | Sale of Surplus Property |

## Set-Aside Types

| Code | Description |
|------|-------------|
| SBA | Total Small Business Set-Aside |
| 8A | 8(a) Set-Aside |
| HUBZone | HUBZone Set-Aside |
| SDVOSBC | Service-Disabled Veteran-Owned Small Business |
| WOSB | Women-Owned Small Business |
| EDWOSB | Economically Disadvantaged WOSB |

## Accessing Downloaded Files

All downloaded attachments are stored in the actor's key-value store. The `storageKey` field in each attachment contains the path to access the file.

To download files after the run:
1. Go to your run's Key-Value Store in the Apify Console
2. Find files by their `storageKey` (format: `{opportunityId}/{filename}`)
3. Download individually or export all

## Technical Details

This actor uses SAM.gov's internal API endpoints (the same ones used by their website):

- **Search**: `https://sam.gov/api/prod/sgs/v1/search/`
- **Details**: `https://sam.gov/api/prod/opps/v2/opportunities/{id}`
- **Attachments**: `https://sam.gov/api/prod/opps/v3/opportunities/{id}/resources`
- **Download**: `https://sam.gov/api/prod/opps/v3/opportunities/resources/files/{resourceId}/download`

No authentication is required for these endpoints.

## Rate Limiting

The actor includes built-in delays (0.5s between opportunities) to be respectful of SAM.gov's servers. For large scrapes, consider running during off-peak hours.

## License

MIT License
