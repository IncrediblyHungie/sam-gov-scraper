"""
SAM.gov Federal Contract Scraper with Attachment Download

The only Apify actor that downloads actual RFP documents, SOWs, and attachments
from federal contract opportunities - NO API KEY REQUIRED.

Uses SAM.gov's internal API endpoints with Playwright browser for reliable downloads.
"""

import asyncio
import io
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode

import httpx
from apify import Actor
from playwright.async_api import async_playwright, Browser


# SAM.gov internal API endpoints (no API key required)
SAM_SEARCH_URL = "https://sam.gov/api/prod/sgs/v1/search/"
SAM_DETAILS_URL = "https://sam.gov/api/prod/opps/v2/opportunities"
SAM_RESOURCES_URL = "https://sam.gov/api/prod/opps/v3/opportunities"
SAM_DOWNLOAD_URL = "https://sam.gov/api/prod/opps/v3/opportunities/resources/files"

# JSON API headers
JSON_HEADERS = {
    "Accept": "application/hal+json, application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://sam.gov/search/",
    "Origin": "https://sam.gov",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def safe_get(obj: Any, *keys, default=None) -> Any:
    """Safely get nested dictionary values."""
    for key in keys:
        if obj is None or not isinstance(obj, dict):
            return default
        obj = obj.get(key)
    return obj if obj is not None else default


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
        Actor.log.info(f"Set-aside types: {set_aside_types or 'All'}")
        Actor.log.info(f"States: {states or 'All'}")
        Actor.log.info(f"Posted within: {posted_within_days} days")
        Actor.log.info(f"Download attachments: {download_attachments}")
        Actor.log.info(f"Max opportunities: {max_opportunities}")

        # Initialize Playwright browser for downloads
        browser = None
        browser_context = None
        if download_attachments:
            try:
                playwright = await async_playwright().start()
                browser = await playwright.chromium.launch(headless=True)
                browser_context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    accept_downloads=True,
                )
                Actor.log.info("Playwright browser initialized for downloads")
            except Exception as e:
                Actor.log.warning(f"Failed to initialize Playwright: {e}. Downloads may fail.")

        opportunities_fetched = 0
        seen_ids = set()

        try:
            # Create HTTP client with longer timeout
            async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
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
                        try:
                            opportunity_data = await process_opportunity(
                                client, opp, download_attachments, extract_text, browser_context
                            )

                            # Push to dataset
                            await Actor.push_data(opportunity_data)
                            opportunities_fetched += 1

                            if opportunities_fetched % 10 == 0:
                                Actor.log.info(f"Processed {opportunities_fetched} opportunities")
                        except Exception as e:
                            Actor.log.warning(f"Failed to process opportunity {opp_id}: {e}")
                            continue

                    page += 1
                    await asyncio.sleep(0.5)  # Be nice to SAM.gov

            Actor.log.info(f"Scrape complete! Total opportunities: {opportunities_fetched}")
        finally:
            if browser_context:
                await browser_context.close()
            if browser:
                await browser.close()


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
        "random": int(datetime.now(timezone.utc).timestamp()),
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
        from_date = (datetime.now(timezone.utc) - timedelta(days=posted_within_days)).strftime("%m/%d/%Y")
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
        response = await client.get(SAM_SEARCH_URL, params=params, headers=JSON_HEADERS)
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
    browser_context=None,
) -> Dict[str, Any]:
    """Process a single opportunity and optionally download attachments."""

    opp_id = opp.get("_id", "")

    # Extract basic data from search result
    org_hierarchy = opp.get("organizationHierarchy", []) or []
    agency_name = org_hierarchy[0].get("name") if org_hierarchy else None
    sub_agency_name = org_hierarchy[1].get("name") if len(org_hierarchy) > 1 else None
    office_name = org_hierarchy[-1].get("name") if org_hierarchy else None

    # Get description
    descriptions = opp.get("descriptions", []) or []
    description = descriptions[0].get("content", "") if descriptions else ""

    # Build opportunity record
    opportunity_data = {
        "opportunityId": opp_id,
        "solicitationNumber": opp.get("solicitationNumber"),
        "title": opp.get("title"),
        "description": description,
        "type": safe_get(opp, "type", "value"),
        "typeCode": safe_get(opp, "type", "code"),
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
        "scrapedAt": datetime.now(timezone.utc).isoformat(),
    }

    # Get detailed data
    details = await get_opportunity_details(client, opp_id)
    if details:
        data2 = details.get("data2", {}) or {}

        # NAICS codes
        naics_list = data2.get("naics", []) or []
        if naics_list:
            primary_naics = naics_list[0].get("code", []) or []
            opportunity_data["naicsCode"] = primary_naics[0] if primary_naics else None

        # Classification/PSC code
        opportunity_data["pscCode"] = data2.get("classificationCode")

        # Set-aside
        set_aside = data2.get("typeOfSetAside")
        if set_aside and isinstance(set_aside, dict):
            opportunity_data["setAsideType"] = set_aside.get("code")
            opportunity_data["setAsideDescription"] = set_aside.get("value")

        # Place of performance - handle None values safely
        pop = data2.get("placeOfPerformance") or {}
        opportunity_data["placeOfPerformance"] = {
            "city": safe_get(pop, "city", "name"),
            "state": safe_get(pop, "state", "name"),
            "stateCode": safe_get(pop, "state", "code"),
            "country": safe_get(pop, "country", "name"),
            "countryCode": safe_get(pop, "country", "code"),
        }

        # Contacts
        contacts = []
        for contact in (data2.get("pointOfContact") or []):
            if contact:
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
        award = data2.get("award")
        if award and isinstance(award, dict):
            awardee = award.get("awardee") or {}
            opportunity_data["award"] = {
                "amount": award.get("amount"),
                "awardee": awardee.get("name") if isinstance(awardee, dict) else None,
                "awardeeUei": awardee.get("ueiSAM") if isinstance(awardee, dict) else None,
            }

    # Get attachments if enabled
    if download_attachments:
        attachments = await get_and_download_attachments(
            client, opp_id, extract_text, browser_context
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
        response = await client.get(url, headers=JSON_HEADERS)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        Actor.log.warning(f"Failed to get details for {opp_id}: {e}")
        return None


async def get_and_download_attachments(
    client: httpx.AsyncClient,
    opp_id: str,
    extract_text: bool,
    browser_context=None,
) -> Dict[str, Any]:
    """Get attachment list and optionally download files using Playwright."""

    result = {
        "files": [],
        "texts": [],
    }

    try:
        # Get attachment metadata
        url = f"{SAM_RESOURCES_URL}/{opp_id}/resources"
        response = await client.get(url, headers=JSON_HEADERS)

        if response.status_code != 200:
            return result

        data = response.json()
        attachment_lists = data.get("_embedded", {}).get("opportunityAttachmentList", [])

        if not attachment_lists:
            return result

        # Process all attachment lists (usually just one)
        for att_list in attachment_lists:
            attachments = att_list.get("attachments", []) or []

            for attachment in attachments:
                if not attachment:
                    continue
                if attachment.get("deletedFlag") == "1":
                    continue

                resource_id = attachment.get("resourceId")
                filename = attachment.get("name", "unknown")
                file_type = attachment.get("mimeType", "")
                file_size = attachment.get("size", 0)
                access_level = attachment.get("accessLevel", "public")

                if not resource_id:
                    continue

                # Build download URL (always include for manual download fallback)
                download_url = f"https://sam.gov/api/prod/opps/v3/opportunities/resources/files/{resource_id}/download"

                file_info = {
                    "filename": filename,
                    "type": file_type,
                    "size": file_size,
                    "resourceId": resource_id,
                    "accessLevel": access_level,
                    "postedDate": attachment.get("postedDate"),
                    "downloadUrl": download_url,
                }

                # Skip non-public files
                if access_level != "public":
                    Actor.log.info(f"Skipping non-public file: {filename}")
                    file_info["downloadError"] = "Non-public access level"
                    result["files"].append(file_info)
                    continue

                # Attempt download using Playwright browser
                download_success = False

                if browser_context:
                    try:
                        # Create a new page for this download
                        page = await browser_context.new_page()

                        try:
                            # First navigate to the opportunity page to establish session
                            await page.goto(f"https://sam.gov/opp/{opp_id}/view", wait_until="domcontentloaded", timeout=30000)
                            await asyncio.sleep(1)  # Wait for any JS to execute

                            # Now try to download the file
                            async with page.expect_download(timeout=60000) as download_info:
                                await page.goto(download_url)

                            download = await download_info.value

                            # Save to temp path and read content
                            temp_path = await download.path()
                            if temp_path:
                                with open(temp_path, "rb") as f:
                                    file_content = f.read()

                                if len(file_content) > 0:
                                    # Store file in key-value store
                                    store = await Actor.open_key_value_store()
                                    safe_filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
                                    file_key = f"{opp_id}/{safe_filename}"
                                    await store.set_value(file_key, file_content)
                                    file_info["storageKey"] = file_key
                                    file_info["downloadedSize"] = len(file_content)

                                    Actor.log.info(f"Downloaded: {filename} ({len(file_content):,} bytes)")

                                    # Extract text if enabled and it's a PDF
                                    if extract_text and filename.lower().endswith('.pdf'):
                                        text = extract_pdf_text(file_content)
                                        if text:
                                            result["texts"].append({
                                                "filename": filename,
                                                "text": text[:50000],
                                            })

                                    download_success = True
                        except Exception as e:
                            Actor.log.debug(f"Playwright download failed for {filename}: {e}")
                        finally:
                            await page.close()

                    except Exception as e:
                        Actor.log.debug(f"Playwright error for {filename}: {e}")

                if not download_success:
                    # Download failed, but we still provide the URL for manual download
                    file_info["downloadError"] = "Download blocked. Use downloadUrl to fetch manually from browser."
                    Actor.log.warning(f"Could not download {filename} - URL provided in output")

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
