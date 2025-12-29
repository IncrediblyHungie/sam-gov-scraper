# SAM.gov Federal Contract Scraper with Attachments

The **only** Apify actor that downloads actual RFP documents, SOWs, and attachments from federal contract opportunities on SAM.gov.

## Features

- **Full Opportunity Data**: Title, description, deadlines, agency, NAICS, set-asides, contacts
- **Attachment Download**: Downloads all RFPs, SOWs, pricing templates, and other documents
- **PDF Text Extraction**: Optionally extract text from PDFs for searching/analysis
- **Flexible Filtering**: Filter by NAICS codes, keywords, set-aside types, states
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
| `apiKey` | string | Yes | - | Your SAM.gov API key |
| `keywords` | string | No | - | Search keywords |
| `naicsCodes` | array | No | ["541511", "541512", "541519"] | NAICS codes to filter |
| `postedWithinDays` | integer | No | 30 | Days to look back |
| `setAsideTypes` | array | No | [] | Set-aside filters (8A, HUBZone, etc.) |
| `states` | array | No | [] | State filters (CA, TX, VA, etc.) |
| `downloadAttachments` | boolean | No | true | Download RFPs and documents |
| `extractText` | boolean | No | false | Extract text from PDFs |
| `maxOpportunities` | integer | No | 100 | Maximum results |

## Getting a SAM.gov API Key

1. Go to [SAM.gov](https://sam.gov)
2. Create an account or sign in
3. Navigate to your profile settings
4. Generate a public API key
5. Use it in the `apiKey` input field

## Output Example

```json
{
    "noticeId": "abc123",
    "solicitationNumber": "W912HQ-24-R-0001",
    "title": "IT Support Services",
    "description": "Seeking IT support for...",
    "type": "Solicitation",
    "postedDate": "2024-01-15",
    "responseDeadline": "2024-02-15T14:00:00-05:00",
    "naicsCode": "541512",
    "setAsideType": "SBA",
    "agencyName": "Department of Defense",
    "contacts": [
        {
            "name": "John Smith",
            "email": "john.smith@agency.gov",
            "phone": "555-123-4567"
        }
    ],
    "attachments": [
        {
            "filename": "RFP_IT_Support.pdf",
            "type": "application/pdf",
            "size": 1234567,
            "storageKey": "abc123/RFP_IT_Support.pdf"
        }
    ],
    "samGovLink": "https://sam.gov/opp/abc123/view"
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

## Set-Aside Types

| Code | Description |
|------|-------------|
| SBA | Small Business Set-Aside |
| 8A | 8(a) Program |
| HUBZone | HUBZone Program |
| SDVOSBC | Service-Disabled Veteran-Owned |
| WOSB | Women-Owned Small Business |
| EDWOSB | Economically Disadvantaged WOSB |

## License

MIT License
