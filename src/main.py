"""
SAM.gov Federal Contract Scraper with Attachment Download

The only Apify actor that downloads actual RFP documents, SOWs, and attachments
from federal contract opportunities - NO API KEY REQUIRED.

Uses SAM.gov's internal API endpoints.
"""

import asyncio
import io
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode

import httpx
from apify import Actor


# SAM.gov internal API endpoints (no API key required)
SAM_SEARCH_URL = "https://sam.gov/api/prod/sgs/v1/search/"
SAM_DETAILS_URL = "https://sam.gov/api/prod/opps/v2/opportunities"
SAM_RESOURCES_URL = "https://sam.gov/api/prod/opps/v3/opportunities"
SAM_DOWNLOAD_URL = "https://sam.gov/api/prod/opps/v3/opportunities/resources/files"

# Common headers
HEADERS = {
    "Accept": "application/hal+json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


async def main():
    async with Actor:
        # Get input
        actor_input = await Actor.get_input() or {}

        keywords = actor_input.get('keywords', '')
        naics_codes = actor_input.get('naicsCodes', [])
        posted_within_days = actor_input.get('postedWithinDays', 30)
        set_aside_types = actor_input.get('setAsideTypes', [])
        states = actor_input.get('states', [])
        opportunity_types = actor_input.get('opportunityTypes', [])
        download_attachments = actor_input.get('downloadAttachments', True)
        extract_text = actor_input.get('extractText', False)
        max_opportunities = actor_input.get('maxOpportunities', 100)

        Actor.log.info("Starting SAM.gov scrape (NO API KEY REQUIRED)")
        Actor.log.info(f"Keywords: {keywords or 'None'}")
        Actor.log.info(f"NAICS codes: {naics_codes or 'All'}")
        Actor.log.info(f"Download attachments: {download_attachments}")

        opportunities_fetched = 0
        seen_ids = set()

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            page = 0
            page_size = 25

            while opportunities_fetched < max_opportunities:
                Actor.log.info(f"Fetching page {page + 1}...")

                # Build search query
                opportunities = await search_opportunities(
                    client,
                    keywords=keywords,
                    naics_codes=naics_codes,
                    posted_within_days=posted_within_days,
                    set_aside_types=set_aside_types,
                    states=states,
                    opportunity_types=opportunity_types,
                    page=page,
                    page_size=page_size,
                )

                if not opportunities:
                    Actor.log.info("No more opportunities found")
                    break

                for opp in opportunities:
                    if opportunities_fetched >= max_opportunities:
                        break

                    opp_id = opp.get("_id")
                    if opp_id in seen_ids:
                        continue
                    seen_ids.add(opp_id)

                    # Get full details and attachments
                    opportunity_data = await process_opportunity(
                        client, opp, download_attachments, extract_text
                    )

                    # Push to dataset
                    await Actor.push_data(opportunity_data)
                    opportunities_fetched += 1

                    if opportunities_fetched % 10 == 0:
                        Actor.log.info(f"Processed {opportunities_fetched} opportunities")

                page += 1
                await asyncio.sleep(0.5)  # Be nice to SAM.gov

        Actor.log.info(f"Scrape complete! Total opportunities: {opportunities_fetched}")


async def search_opportunities(
    client: httpx.AsyncClient,
    keywords: str = "",
    naics_codes: List[str] = None,
    posted_within_days: int = 30,
    set_aside_types: List[str] = None,
    states: List[str] = None,
    opportunity_types: List[str] = None,
    page: int = 0,
    page_size: int = 25,
) -> List[Dict[str, Any]]:
    """Search SAM.gov opportunities using internal API."""

    # Build query parameters
    params = {
        "random": int(datetime.utcnow().timestamp()),
        "index": "opp",
        "page": page,
        "mode": "search",
        "sort": "-modifiedDate",
        "size": page_size,
        "is_active": "true",
    }

    # Add keyword search
    if keywords:
        params["q"] = keywords

    # Add NAICS filter
    if naics_codes:
        params["naics"] = ",".join(naics_codes)

    # Add posted date filter
    if posted_within_days:
        from_date = (datetime.utcnow() - timedelta(days=posted_within_days)).strftime("%m/%d/%Y")
        params["postedFrom"] = from_date

    # Add set-aside filter
    if set_aside_types:
        params["typeOfSetAside"] = ",".join(set_aside_types)

    # Add state filter
    if states:
        params["state"] = ",".join(states)

    # Add opportunity type filter (o=solicitation, k=combined, p=presolicitation, etc.)
    if opportunity_types:
        params["opp_type"] = ",".join(opportunity_types)

    try:
        response = await client.get(SAM_SEARCH_URL, params=params, headers=HEADERS)
        response.raise_for_status()
        data = response.json()

        results = data.get("_embedded", {}).get("results", [])
        Actor.log.info(f"Found {len(results)} opportunities on page {page + 1}")
        return results

    except httpx.HTTPError as e:
        Actor.log.error(f"Search error: {e}")
        return []


async def process_opportunity(
    client: httpx.AsyncClient,
    opp: Dict[str, Any],
    download_attachments: bool,
    extract_text: bool,
) -> Dict[str, Any]:
    """Process a single opportunity and optionally download attachments."""

    opp_id = opp.get("_id", "")

    # Extract basic data from search result
    org_hierarchy = opp.get("organizationHierarchy", [])
    agency_name = org_hierarchy[0].get("name") if org_hierarchy else None
    sub_agency_name = org_hierarchy[1].get("name") if len(org_hierarchy) > 1 else None
    office_name = org_hierarchy[-1].get("name") if org_hierarchy else None

    # Get description
    descriptions = opp.get("descriptions", [])
    description = descriptions[0].get("content", "") if descriptions else ""

    # Build opportunity record
    opportunity_data = {
        "opportunityId": opp_id,
        "solicitationNumber": opp.get("solicitationNumber"),
        "title": opp.get("title"),
        "description": description,
        "type": opp.get("type", {}).get("value"),
        "typeCode": opp.get("type", {}).get("code"),
        "postedDate": opp.get("publishDate"),
        "modifiedDate": opp.get("modifiedDate"),
        "responseDeadline": opp.get("responseDate"),
        "responseTimeZone": opp.get("responseTimeZone"),
        "isActive": opp.get("isActive"),
        "isCanceled": opp.get("isCanceled"),
        "agencyName": agency_name,
        "subAgencyName": sub_agency_name,
        "officeName": office_name,
        "samGovLink": f"https://sam.gov/opp/{opp_id}/view",
        "attachments": [],
        "attachmentTexts": [],
        "scrapedAt": datetime.utcnow().isoformat(),
    }

    # Get detailed data
    details = await get_opportunity_details(client, opp_id)
    if details:
        data2 = details.get("data2", {})

        # NAICS codes
        naics_list = data2.get("naics", [])
        if naics_list:
            primary_naics = naics_list[0].get("code", [])
            opportunity_data["naicsCode"] = primary_naics[0] if primary_naics else None

        # Classification/PSC code
        opportunity_data["pscCode"] = data2.get("classificationCode")

        # Set-aside
        set_aside = data2.get("typeOfSetAside")
        if set_aside:
            opportunity_data["setAsideType"] = set_aside.get("code")
            opportunity_data["setAsideDescription"] = set_aside.get("value")

        # Place of performance
        pop = data2.get("placeOfPerformance", {})
        opportunity_data["placeOfPerformance"] = {
            "city": pop.get("city", {}).get("name"),
            "state": pop.get("state", {}).get("name"),
            "stateCode": pop.get("state", {}).get("code"),
            "country": pop.get("country", {}).get("name"),
            "countryCode": pop.get("country", {}).get("code"),
        }

        # Contacts
        contacts = []
        for contact in data2.get("pointOfContact", []):
            contacts.append({
                "name": contact.get("fullName"),
                "email": contact.get("email"),
                "phone": contact.get("phone"),
                "fax": contact.get("fax"),
                "title": contact.get("title"),
                "type": contact.get("type"),
            })
        opportunity_data["contacts"] = contacts

        # Award info if available
        award = data2.get("award", {})
        if award:
            opportunity_data["award"] = {
                "amount": award.get("amount"),
                "awardee": award.get("awardee", {}).get("name"),
                "awardeeUei": award.get("awardee", {}).get("ueiSAM"),
            }

    # Download attachments if enabled
    if download_attachments:
        attachments = await get_and_download_attachments(
            client, opp_id, extract_text
        )
        opportunity_data["attachments"] = attachments.get("files", [])
        if extract_text:
            opportunity_data["attachmentTexts"] = attachments.get("texts", [])

    return opportunity_data


async def get_opportunity_details(
    client: httpx.AsyncClient,
    opp_id: str,
) -> Optional[Dict[str, Any]]:
    """Get full opportunity details."""
    try:
        url = f"{SAM_DETAILS_URL}/{opp_id}"
        response = await client.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        Actor.log.warning(f"Failed to get details for {opp_id}: {e}")
        return None


async def get_and_download_attachments(
    client: httpx.AsyncClient,
    opp_id: str,
    extract_text: bool,
) -> Dict[str, Any]:
    """Get attachment list and download files."""

    result = {
        "files": [],
        "texts": [],
    }

    try:
        # Get attachment metadata
        url = f"{SAM_RESOURCES_URL}/{opp_id}/resources"
        response = await client.get(url, headers=HEADERS)

        if response.status_code != 200:
            return result

        data = response.json()
        attachment_lists = data.get("_embedded", {}).get("opportunityAttachmentList", [])

        if not attachment_lists:
            return result

        # Process all attachment lists (usually just one)
        for att_list in attachment_lists:
            attachments = att_list.get("attachments", [])

            for attachment in attachments:
                if attachment.get("deletedFlag") == "1":
                    continue

                resource_id = attachment.get("resourceId")
                filename = attachment.get("name", "unknown")
                file_type = attachment.get("mimeType", "")
                file_size = attachment.get("size", 0)
                access_level = attachment.get("accessLevel", "public")

                if not resource_id:
                    continue

                # Skip non-public files
                if access_level != "public":
                    Actor.log.info(f"Skipping non-public file: {filename}")
                    continue

                file_info = {
                    "filename": filename,
                    "type": file_type,
                    "size": file_size,
                    "resourceId": resource_id,
                    "accessLevel": access_level,
                    "postedDate": attachment.get("postedDate"),
                }

                # Download the file
                try:
                    download_url = f"{SAM_DOWNLOAD_URL}/{resource_id}/download"
                    file_response = await client.get(download_url, headers=HEADERS)

                    if file_response.status_code == 200:
                        file_content = file_response.content

                        # Store file in key-value store
                        store = await Actor.open_key_value_store()
                        file_key = f"{opp_id}/{filename}"
                        await store.set_value(file_key, file_content)
                        file_info["storageKey"] = file_key
                        file_info["downloadedSize"] = len(file_content)

                        Actor.log.info(f"Downloaded: {filename} ({len(file_content)} bytes)")

                        # Extract text if enabled and it's a PDF
                        if extract_text and filename.lower().endswith('.pdf'):
                            text = extract_pdf_text(file_content)
                            if text:
                                result["texts"].append({
                                    "filename": filename,
                                    "text": text[:50000],  # Limit text length
                                })

                except Exception as e:
                    Actor.log.warning(f"Failed to download {filename}: {e}")
                    file_info["downloadError"] = str(e)

                result["files"].append(file_info)

        Actor.log.info(f"Processed {len(result['files'])} attachments for {opp_id}")

    except Exception as e:
        Actor.log.warning(f"Failed to get attachments for {opp_id}: {e}")

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
