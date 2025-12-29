#!/usr/bin/env python3
"""
Local test script for SAM.gov scraper.
Tests the core functionality without the Apify runtime.
NO API KEY REQUIRED.
"""

import asyncio
import json
from datetime import datetime, timedelta

import httpx

# SAM.gov internal API endpoints
SAM_SEARCH_URL = "https://sam.gov/api/prod/sgs/v1/search/"
SAM_DETAILS_URL = "https://sam.gov/api/prod/opps/v2/opportunities"
SAM_RESOURCES_URL = "https://sam.gov/api/prod/opps/v3/opportunities"
SAM_DOWNLOAD_URL = "https://sam.gov/api/prod/opps/v3/opportunities/resources/files"

HEADERS = {
    "Accept": "application/hal+json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


async def test_search():
    """Test basic opportunity search."""
    print("\n" + "="*60)
    print("TEST 1: Basic Opportunity Search (NO API KEY)")
    print("="*60)

    params = {
        "random": int(datetime.utcnow().timestamp()),
        "index": "opp",
        "page": 0,
        "mode": "search",
        "sort": "-modifiedDate",
        "size": 5,
        "is_active": "true",
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(SAM_SEARCH_URL, params=params, headers=HEADERS)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            opportunities = data.get("_embedded", {}).get("results", [])
            print(f"Found {len(opportunities)} opportunities")

            if opportunities:
                opp = opportunities[0]
                print(f"\nFirst opportunity:")
                print(f"  ID: {opp.get('_id')}")
                print(f"  Title: {opp.get('title', '')[:80]}")
                print(f"  Type: {opp.get('type', {}).get('value')}")
                print(f"  Posted: {opp.get('publishDate')}")
                print(f"  Deadline: {opp.get('responseDate')}")

                org = opp.get('organizationHierarchy', [])
                if org:
                    print(f"  Agency: {org[0].get('name', '')[:50]}")

                return opp.get('_id')
        else:
            print(f"Error: {response.text[:500]}")
            return None


async def test_details(opp_id: str):
    """Test opportunity details retrieval."""
    print("\n" + "="*60)
    print(f"TEST 2: Opportunity Details for {opp_id}")
    print("="*60)

    if not opp_id:
        print("Skipping - no opportunity ID")
        return

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        url = f"{SAM_DETAILS_URL}/{opp_id}"
        response = await client.get(url, headers=HEADERS)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            data2 = data.get("data2", {})

            print(f"\nDetails:")
            print(f"  Title: {data2.get('title', '')[:80]}")
            print(f"  Solicitation #: {data2.get('solicitationNumber')}")

            naics = data2.get("naics", [])
            if naics:
                print(f"  NAICS: {naics[0].get('code', [])}")

            print(f"  PSC Code: {data2.get('classificationCode')}")

            contacts = data2.get("pointOfContact", [])
            if contacts:
                print(f"  Primary Contact: {contacts[0].get('fullName')}")
                print(f"  Email: {contacts[0].get('email')}")

            pop = data2.get("placeOfPerformance", {})
            if pop:
                city = pop.get("city", {}).get("name", "")
                state = pop.get("state", {}).get("name", "")
                print(f"  Location: {city}, {state}")

            return True
        else:
            print(f"Error: {response.status_code}")
            return False


async def test_attachments(opp_id: str):
    """Test attachment listing and download."""
    print("\n" + "="*60)
    print(f"TEST 3: Attachments for {opp_id}")
    print("="*60)

    if not opp_id:
        print("Skipping - no opportunity ID")
        return

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        # Get attachment list
        url = f"{SAM_RESOURCES_URL}/{opp_id}/resources"
        response = await client.get(url, headers=HEADERS)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            attachment_lists = data.get("_embedded", {}).get("opportunityAttachmentList", [])

            if not attachment_lists:
                print("No attachments found")
                return

            total_files = 0
            for att_list in attachment_lists:
                attachments = att_list.get("attachments", [])
                total_files += len(attachments)

                print(f"\nFound {len(attachments)} attachments:")
                for att in attachments[:5]:  # Show first 5
                    print(f"\n  File: {att.get('name')}")
                    print(f"    Type: {att.get('mimeType')}")
                    print(f"    Size: {att.get('size', 0):,} bytes")
                    print(f"    Resource ID: {att.get('resourceId')}")
                    print(f"    Access: {att.get('accessLevel')}")

                    # Test download for first public file
                    if att.get('accessLevel') == 'public' and att.get('resourceId'):
                        resource_id = att.get('resourceId')
                        download_url = f"{SAM_DOWNLOAD_URL}/{resource_id}/download"

                        print(f"\n    Testing download...")
                        dl_response = await client.get(download_url, headers=HEADERS)
                        if dl_response.status_code == 200:
                            print(f"    SUCCESS! Downloaded {len(dl_response.content):,} bytes")

                            # Save first file as sample
                            filename = att.get('name', 'sample_file')
                            with open(f"/tmp/{filename}", "wb") as f:
                                f.write(dl_response.content)
                            print(f"    Saved to /tmp/{filename}")
                        else:
                            print(f"    Download failed: {dl_response.status_code}")

                        break  # Only test one download

            print(f"\nTotal attachments: {total_files}")
        else:
            print(f"Error: {response.status_code}")


async def test_filtered_search():
    """Test search with filters."""
    print("\n" + "="*60)
    print("TEST 4: Filtered Search (NAICS 541511 - Computer Programming)")
    print("="*60)

    params = {
        "random": int(datetime.utcnow().timestamp()),
        "index": "opp",
        "page": 0,
        "mode": "search",
        "sort": "-modifiedDate",
        "size": 5,
        "is_active": "true",
        "naics": "541511",
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(SAM_SEARCH_URL, params=params, headers=HEADERS)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            opportunities = data.get("_embedded", {}).get("results", [])
            print(f"Found {len(opportunities)} opportunities with NAICS 541511")

            for i, opp in enumerate(opportunities[:3]):
                print(f"\n  {i+1}. {opp.get('title', '')[:60]}...")
                print(f"     Type: {opp.get('type', {}).get('value')}")
                print(f"     Deadline: {opp.get('responseDate', 'N/A')}")


async def main():
    print("\n" + "="*60)
    print("SAM.gov Scraper Local Test")
    print("NO API KEY REQUIRED")
    print("="*60)

    # Test 1: Basic search
    opp_id = await test_search()

    # Test 2: Get details
    if opp_id:
        await test_details(opp_id)

    # Test 3: Get and download attachments
    if opp_id:
        await test_attachments(opp_id)

    # Test 4: Filtered search
    await test_filtered_search()

    print("\n" + "="*60)
    print("All tests complete!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
