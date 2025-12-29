#!/usr/bin/env python3
"""
Local test script for SAM.gov scraper.
Tests the core functionality without the Apify runtime.
"""

import asyncio
import json
from datetime import datetime, timedelta

import httpx

# SAM.gov API endpoints
SAM_API_BASE = "https://api.sam.gov/opportunities/v2"
SAM_ATTACHMENT_BASE = "https://api.sam.gov/opportunities/v1/noauth"

# Get API key from BidKing config
import sys
sys.path.insert(0, '/home/peteylinux/Projects/BidKing')

try:
    from app.config import settings
    API_KEY = settings.sam_gov_api_key
except:
    API_KEY = None


async def test_search():
    """Test basic opportunity search."""
    print("\n" + "="*60)
    print("TEST 1: Basic Opportunity Search")
    print("="*60)

    if not API_KEY:
        print("ERROR: No API key found. Set SAM_GOV_API_KEY or check BidKing config.")
        return None

    posted_from = (datetime.utcnow() - timedelta(days=7)).strftime("%m/%d/%Y")
    posted_to = datetime.utcnow().strftime("%m/%d/%Y")

    params = {
        "api_key": API_KEY,
        "postedFrom": posted_from,
        "postedTo": posted_to,
        "ncode": "541511",  # Custom Computer Programming
        "limit": 5,
        "offset": 0,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{SAM_API_BASE}/search", params=params)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            opportunities = data.get("opportunitiesData", [])
            print(f"Found {len(opportunities)} opportunities")

            if opportunities:
                opp = opportunities[0]
                print(f"\nFirst opportunity:")
                print(f"  Notice ID: {opp.get('noticeId')}")
                print(f"  Title: {opp.get('title', '')[:80]}")
                print(f"  Type: {opp.get('type')}")
                print(f"  Posted: {opp.get('postedDate')}")
                print(f"  Deadline: {opp.get('responseDeadLine')}")
                print(f"  Agency: {opp.get('fullParentPathName', '')[:50]}")
                return opp.get('noticeId')
        else:
            print(f"Error: {response.text[:500]}")
            return None


async def test_attachments(notice_id: str):
    """Test attachment metadata retrieval."""
    print("\n" + "="*60)
    print(f"TEST 2: Attachment Metadata for {notice_id}")
    print("="*60)

    if not notice_id:
        print("Skipping - no notice ID")
        return

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try to get attachment metadata
        metadata_url = f"{SAM_ATTACHMENT_BASE}/download/metadata/{notice_id}"
        response = await client.get(
            metadata_url,
            params={"api_key": API_KEY}
        )
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            attachments = data.get("opportunityAttachmentList", [])
            print(f"Found {len(attachments)} attachments")

            for att in attachments[:5]:
                print(f"\n  Attachment:")
                print(f"    Name: {att.get('name')}")
                print(f"    Type: {att.get('type')}")
                print(f"    Resource ID: {att.get('resourceId')}")

            return attachments
        else:
            print(f"No attachments or error: {response.status_code}")
            # Try getting the full opportunity details
            print("\nTrying full opportunity details...")
            detail_url = f"{SAM_API_BASE}/search"
            detail_params = {
                "api_key": API_KEY,
                "noticeId": notice_id,
                "limit": 1,
            }
            detail_response = await client.get(detail_url, params=detail_params)
            if detail_response.status_code == 200:
                detail_data = detail_response.json()
                opps = detail_data.get("opportunitiesData", [])
                if opps:
                    print(f"Opportunity has resourceLinks: {opps[0].get('resourceLinks', [])}")
            return []


async def test_download_attachment(notice_id: str, resource_id: str, filename: str):
    """Test downloading a single attachment."""
    print("\n" + "="*60)
    print(f"TEST 3: Download Attachment {filename}")
    print("="*60)

    if not notice_id or not resource_id:
        print("Skipping - no notice ID or resource ID")
        return

    async with httpx.AsyncClient(timeout=60.0) as client:
        download_url = f"{SAM_ATTACHMENT_BASE}/download/{notice_id}/{resource_id}"
        response = await client.get(
            download_url,
            params={"api_key": API_KEY}
        )
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            content = response.content
            print(f"Downloaded {len(content)} bytes")
            print(f"Content-Type: {response.headers.get('content-type')}")

            # Save to local file for inspection
            with open(f"/tmp/{filename}", "wb") as f:
                f.write(content)
            print(f"Saved to /tmp/{filename}")
            return True
        else:
            print(f"Failed: {response.status_code}")
            return False


async def main():
    print("\n" + "="*60)
    print("SAM.gov Scraper Local Test")
    print("="*60)

    if not API_KEY:
        print("\nERROR: No API key configured!")
        print("Set the SAM_GOV_API_KEY environment variable or configure BidKing.")
        return

    print(f"\nUsing API key: {API_KEY[:10]}...{API_KEY[-4:]}")

    # Test 1: Search
    notice_id = await test_search()

    # Test 2: Get attachments
    if notice_id:
        attachments = await test_attachments(notice_id)

        # Test 3: Download first attachment
        if attachments:
            first = attachments[0]
            await test_download_attachment(
                notice_id,
                first.get('resourceId'),
                first.get('name', 'test_file')
            )

    print("\n" + "="*60)
    print("Tests complete!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
