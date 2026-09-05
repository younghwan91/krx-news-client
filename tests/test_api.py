from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_news(client):
    resp = await client.get("/api/v1/news")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data


@pytest.mark.asyncio
async def test_list_news_with_source(client):
    resp = await client.get("/api/v1/news?source=toss")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_search_news(client):
    resp = await client.get("/api/v1/news/search?q=삼성전자")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_list_disclosures(client):
    resp = await client.get("/api/v1/disclosure")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_disclosures_by_ticker(client):
    resp = await client.get("/api/v1/disclosure/005930")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_crawler_status(client):
    resp = await client.get("/api/v1/status")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_invalid_page(client):
    resp = await client.get("/api/v1/news?page=0")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_requires_query(client):
    resp = await client.get("/api/v1/news/search")
    assert resp.status_code == 422
