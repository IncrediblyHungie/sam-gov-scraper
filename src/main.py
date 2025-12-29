"""
SAM.gov Federal Contract Scraper with Attachment Download

The only Apify actor that downloads actual RFP documents, SOWs, and attachments
from federal contract opportunities.
"""

import asyncio
import io
import zipfile
from datetime import datetime, timedelta
from typing import Optional

import httpx
from apify import Actor


# SAM.gov API endpoints
SAM_API_BASE = "https://api.sam.gov/opportunities/v2"
SAM_ATTACHMENT_BASE = "https://api.sam.gov/opportunities/v1/noauth"


async def main():
    async with Actor:
        # Get input
        actor_input = await Actor.get_input() or {}

        api_key = actor_input.get('apiKey')
        if not api_key:
            Actor.log.error("SAM.gov API key is required!")
            return

        keywords = actor_input.get('keywords', '')
        naics_codes = actor_input.get('naicsCodes', ['541511', '541512', '541519'])
        posted_within_days = actor_input.get('postedWithinDays', 30)
        set_aside_types = actor_input.get('setAsideTypes', [])
        states = actor_input.get('states', [])
        download_attachments = actor_input.get('downloadAttachments', True)
        extract_text = actor_input.get('extractText', False)
        max_opportunities = actor_input.get('maxOpportunities', 100)

        Actor.log.info(f"Starting SAM.gov scrape with {len(naics_codes)} NAICS codes")
        Actor.log.info(f"Download attachments: {download_attachments}")

        # Calculate date range
        posted_from = (datetime.utcnow() - timedelta(days=posted_within_days)).strftime("%m/%d/%Y")
        posted_to = datetime.utcnow().strftime("%m/%d/%Y")

        opportunities_fetched = 0

        async with httpx.AsyncClient(timeout=60.0) as client:
            for naics_code in naics_codes:
                if opportunities_fetched >= max_opportunities:
                    break

                Actor.log.info(f"Fetching opportunities for NAICS {naics_code}")

                # Build search params
                params = {
                    "api_key": api_key,
                    "postedFrom": posted_from,
                    "postedTo": posted_to,
                    "limit": min(100, max_opportunities - opportunities_fetched),
                    "offset": 0,
                }

                if naics_code:
                    params["ncode"] = naics_code

                if keywords:
                    params["title"] = keywords

                if set_aside_types:
                    params["typeOfSetAside"] = ",".join(set_aside_types)

                if states:
                    params["state"] = ",".join(states)

                try:
                    # Fetch opportunities
                    response = await client.get(f"{SAM_API_BASE}/search", params=params)
                    response.raise_for_status()
                    data = response.json()

                    opportunities = data.get("opportunitiesData", [])
                    Actor.log.info(f"Found {len(opportunities)} opportunities for NAICS {naics_code}")

                    for opp in opportunities:
                        if opportunities_fetched >= max_opportunities:
                            break

                        # Process opportunity
                        opportunity_data = await process_opportunity(
                            client, opp, api_key,
                            download_attachments, extract_text
                        )

                        # Push to dataset
                        await Actor.push_data(opportunity_data)
                        opportunities_fetched += 1

                        if opportunities_fetched % 10 == 0:
                            Actor.log.info(f"Processed {opportunities_fetched} opportunities")

                except httpx.HTTPError as e:
                    Actor.log.error(f"HTTP error for NAICS {naics_code}: {e}")
                    continue
                except Exception as e:
                    Actor.log.error(f"Error for NAICS {naics_code}: {e}")
                    continue

        Actor.log.info(f"Scrape complete! Total opportunities: {opportunities_fetched}")


async def process_opportunity(
    client: httpx.AsyncClient,
    opp: dict,
    api_key: str,
    download_attachments: bool,
    extract_text: bool
) -> dict:
    """Process a single opportunity and optionally download attachments."""

    notice_id = opp.get("noticeId", "")

    # Extract place of performance
    pop = opp.get("placeOfPerformance", {}) or {}
    pop_city = pop.get("city", {}).get("name") if isinstance(pop.get("city"), dict) else None
    pop_state = pop.get("state", {}).get("code") if isinstance(pop.get("state"), dict) else None
    pop_country = pop.get("country", {}).get("code") if isinstance(pop.get("country"), dict) else None

    # Extract contacts
    contacts = []
    for contact in opp.get("pointOfContact", []) or []:
        contacts.append({
            "name": contact.get("fullName"),
            "email": contact.get("email"),
            "phone": contact.get("phone"),
            "title": contact.get("title"),
            "type": contact.get("type"),
        })

    # Build opportunity record
    opportunity_data = {
        "noticeId": notice_id,
        "solicitationNumber": opp.get("solicitationNumber"),
        "title": opp.get("title"),
        "description": opp.get("description"),
        "type": opp.get("type"),
        "typeDescription": opp.get("baseType"),
        "postedDate": opp.get("postedDate"),
        "responseDeadline": opp.get("responseDeadLine"),
        "archiveDate": opp.get("archiveDate"),
        "naicsCode": opp.get("naicsCode"),
        "naicsDescription": None,
        "pscCode": opp.get("classificationCode"),
        "setAsideType": opp.get("typeOfSetAside"),
        "setAsideDescription": opp.get("typeOfSetAsideDescription"),
        "agencyName": opp.get("fullParentPathName", "").split(".")[0] if opp.get("fullParentPathName") else opp.get("departmentName"),
        "subAgencyName": opp.get("subtierAgencyName"),
        "officeName": opp.get("officeName"),
        "placeOfPerformance": {
            "city": pop_city,
            "state": pop_state,
            "country": pop_country,
            "zip": pop.get("zip"),
        },
        "contacts": contacts,
        "samGovLink": f"https://sam.gov/opp/{notice_id}/view",
        "attachments": [],
        "attachmentTexts": [],
        "scrapedAt": datetime.utcnow().isoformat(),
    }

    # Extract NAICS description if available
    naics_list = opp.get("naicsCodes", [])
    if naics_list and len(naics_list) > 0:
        opportunity_data["naicsDescription"] = naics_list[0].get("description")

    # Download attachments if enabled
    if download_attachments and notice_id:
        attachments = await download_opportunity_attachments(
            client, notice_id, api_key, extract_text
        )
        opportunity_data["attachments"] = attachments.get("files", [])
        if extract_text:
            opportunity_data["attachmentTexts"] = attachments.get("texts", [])

    return opportunity_data


async def download_opportunity_attachments(
    client: httpx.AsyncClient,
    notice_id: str,
    api_key: str,
    extract_text: bool
) -> dict:
    """Download all attachments for an opportunity as a ZIP."""

    result = {
        "files": [],
        "texts": [],
    }

    try:
        # First get attachment metadata
        metadata_url = f"{SAM_ATTACHMENT_BASE}/download/metadata/{notice_id}"
        metadata_response = await client.get(
            metadata_url,
            params={"api_key": api_key}
        )

        if metadata_response.status_code != 200:
            # Try alternative endpoint
            return result

        metadata = metadata_response.json()
        attachments_meta = metadata.get("opportunityAttachmentList", [])

        if not attachments_meta:
            return result

        # Download each attachment
        for attachment in attachments_meta:
            resource_id = attachment.get("resourceId")
            filename = attachment.get("name", "unknown")
            file_type = attachment.get("type", "")

            if not resource_id:
                continue

            try:
                download_url = f"{SAM_ATTACHMENT_BASE}/download/{notice_id}/{resource_id}"
                file_response = await client.get(
                    download_url,
                    params={"api_key": api_key}
                )

                if file_response.status_code == 200:
                    file_info = {
                        "filename": filename,
                        "type": file_type,
                        "size": len(file_response.content),
                        "resourceId": resource_id,
                    }
                    result["files"].append(file_info)

                    # Store file in key-value store
                    store = await Actor.open_key_value_store()
                    file_key = f"{notice_id}/{filename}"
                    await store.set_value(file_key, file_response.content)
                    file_info["storageKey"] = file_key

                    # Extract text if enabled and it's a PDF
                    if extract_text and filename.lower().endswith('.pdf'):
                        text = extract_pdf_text(file_response.content)
                        if text:
                            result["texts"].append({
                                "filename": filename,
                                "text": text[:50000],  # Limit text length
                            })

            except Exception as e:
                Actor.log.warning(f"Failed to download {filename}: {e}")
                continue

        Actor.log.info(f"Downloaded {len(result['files'])} attachments for {notice_id}")

    except Exception as e:
        Actor.log.warning(f"Failed to get attachments for {notice_id}: {e}")

    return result


def extract_pdf_text(pdf_bytes: bytes) -> Optional[str]:
    """Extract text from PDF bytes using pypdf."""
    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text_parts = []

        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)

        return "\n\n".join(text_parts)
    except Exception as e:
        Actor.log.warning(f"Failed to extract PDF text: {e}")
        return None
