from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
from hubspot.crm.objects import ApiException
from hubspot.crm.owners import (
    CollectionResponsePublicOwnerForwardPaging,
    ForwardPaging,
    NextPage,
    PublicOwner,
)

from app.clients.hubspot_client import HubSpotClient, HubSpotClientError


def make_client(include_associations: bool = True, page_size: int = 100) -> Any:
    """Builds a HubSpotClient with a mocked SDK client, bypassing the real
    network-capable HubSpot() constructor. Returns Any (not HubSpotClient)
    since the internal `_client` is deliberately replaced with a
    MagicMock - typing this as HubSpotClient would make every call site
    a pyright error, as `_client`'s declared type is the real SDK class.
    """
    client = HubSpotClient.__new__(HubSpotClient)
    client._client = MagicMock()
    client._auth = MagicMock(
        base_url="https://api.hubapi.com", get_headers=lambda: {"Authorization": "x"}
    )
    client._page_size = page_size
    client._include_associations = include_associations
    return client


def make_record(record_id: str, properties: dict | None = None):
    """A stand-in for an SDK model instance, matching the .to_dict()
    contract iter_objects relies on."""
    record = MagicMock()
    record.to_dict.return_value = {"id": record_id, "properties": properties or {}}
    return record


class TestIterObjectsStandard:
    def test_single_page(self):
        client = make_client()
        page = MagicMock(results=[make_record("1")], paging=None)
        client._client.crm.objects.basic_api.get_page.return_value = page

        results = list(client.iter_objects("contacts", ["email"]))

        assert results == [(None, [{"id": "1", "properties": {}}])]

    def test_pagination_follows_cursor(self):
        client = make_client()
        page1 = MagicMock(
            results=[make_record("1")],
            paging=MagicMock(next=MagicMock(after="cursor_a")),
        )
        page2 = MagicMock(results=[make_record("2")], paging=None)
        client._client.crm.objects.basic_api.get_page.side_effect = [page1, page2]

        results = list(client.iter_objects("contacts", ["email"]))

        assert [r[0] for r in results] == ["cursor_a", None]
        calls = client._client.crm.objects.basic_api.get_page.call_args_list
        assert calls[0].kwargs["after"] is None
        assert calls[1].kwargs["after"] == "cursor_a"

    def test_empty_page_stops_without_yielding(self):
        client = make_client()
        page = MagicMock(results=[], paging=None)
        client._client.crm.objects.basic_api.get_page.return_value = page

        results = list(client.iter_objects("contacts", ["email"]))

        assert results == []

    def test_include_associations_false_overrides_requested_associations(self):
        client = make_client(include_associations=False)
        client._client.crm.objects.basic_api.get_page.return_value = MagicMock(
            results=[], paging=None
        )

        list(client.iter_objects("contacts", ["email"], associations=["companies"]))

        call_kwargs = client._client.crm.objects.basic_api.get_page.call_args.kwargs
        assert call_kwargs["associations"] == []

    def test_api_exception_wrapped_in_hubspot_client_error(self):
        client = make_client()
        client._client.crm.objects.basic_api.get_page.side_effect = ApiException(
            status=500, reason="server error"
        )

        with pytest.raises(HubSpotClientError):
            list(client.iter_objects("contacts", ["email"]))


class TestIterObjectsIncremental:
    def test_uses_search_api_when_last_modified_after_ms_set(self):
        client = make_client()
        client._client.crm.objects.search_api.do_search.return_value = MagicMock(
            results=[make_record("1")], paging=None
        )

        list(client.iter_objects("contacts", ["email"], last_modified_after_ms=12345))

        assert client._client.crm.objects.search_api.do_search.called
        assert not client._client.crm.objects.basic_api.get_page.called
        request = client._client.crm.objects.search_api.do_search.call_args.kwargs[
            "public_object_search_request"
        ]
        assert request.filter_groups[0].filters[0].value == "12345"


class TestIterOwners:
    def test_reshapes_owner_into_id_properties_shape(self):
        client = make_client()
        owner = PublicOwner(
            id="1",
            email="a@x.com",
            first_name="A",
            last_name="B",
            user_id=42,
            created_at=datetime(2020, 1, 1, tzinfo=UTC),
            updated_at=None,
            archived=False,
            teams=[],
        )
        client._client.crm.owners.owners_api.get_page.return_value = (
            CollectionResponsePublicOwnerForwardPaging(results=[owner], paging=None)
        )

        results = list(client.iter_owners())

        assert results == [
            (
                None,
                [
                    {
                        "id": "1",
                        "properties": {
                            "email": "a@x.com",
                            "firstName": "A",
                            "lastName": "B",
                            "userId": 42,
                            "createdAt": "2020-01-01T00:00:00+00:00",
                            "updatedAt": None,
                            "archived": False,
                        },
                    }
                ],
            )
        ]

    def test_pagination_follows_cursor(self):
        client = make_client()
        owner1 = PublicOwner(id="1", email="a@x.com", archived=False, teams=[])
        owner2 = PublicOwner(id="2", email="b@x.com", archived=False, teams=[])
        page1 = CollectionResponsePublicOwnerForwardPaging(
            results=[owner1], paging=ForwardPaging(next=NextPage(after="cursor_a"))
        )
        page2 = CollectionResponsePublicOwnerForwardPaging(
            results=[owner2], paging=None
        )
        client._client.crm.owners.owners_api.get_page.side_effect = [page1, page2]

        results = list(client.iter_owners())

        assert [r[0] for r in results] == ["cursor_a", None]


class TestIterEngagements:
    def test_reshapes_engagement_into_id_properties_associations_shape(self):
        client = make_client()
        response = MagicMock()
        response.json.return_value = {
            "results": [
                {
                    "engagement": {
                        "id": 8404576745,
                        "type": "TASK",
                        "createdAt": 1598011090516,
                        "lastUpdated": 1598011091674,
                        "ownerId": 49628444,
                        "timestamp": 1598409000000,
                    },
                    "associations": {
                        "contactIds": [458774],
                        "companyIds": [],
                        "dealIds": [],
                    },
                    "metadata": {"body": "hello"},
                }
            ],
            "hasMore": False,
            "offset": 195105719,
        }
        response.raise_for_status.return_value = None

        with patch("app.clients.hubspot_client.requests.get", return_value=response):
            results = list(client.iter_engagements())

        assert results == [
            (
                None,
                [
                    {
                        "id": "8404576745",
                        "properties": {
                            "type": "TASK",
                            "createdAt": 1598011090516,
                            "lastUpdated": 1598011091674,
                            "ownerId": 49628444,
                            "timestamp": 1598409000000,
                            "metadata": '{"body": "hello"}',
                        },
                        "associations": {
                            "contacts": ["458774"],
                            "companies": [],
                            "deals": [],
                        },
                    }
                ],
            )
        ]

    def test_pagination_uses_offset(self):
        client = make_client()
        page1 = MagicMock()
        page1.json.return_value = {
            "results": [{"engagement": {"id": 1}, "associations": {}, "metadata": {}}],
            "hasMore": True,
            "offset": 100,
        }
        page1.raise_for_status.return_value = None
        page2 = MagicMock()
        page2.json.return_value = {
            "results": [{"engagement": {"id": 2}, "associations": {}, "metadata": {}}],
            "hasMore": False,
            "offset": 200,
        }
        page2.raise_for_status.return_value = None

        with patch(
            "app.clients.hubspot_client.requests.get", side_effect=[page1, page2]
        ) as mock_get:
            results = list(client.iter_engagements())

        assert [r[0] for r in results] == ["100", None]
        assert mock_get.call_args_list[0].kwargs["params"] == {"limit": 100}
        assert mock_get.call_args_list[1].kwargs["params"] == {
            "limit": 100,
            "offset": 100,
        }

    def test_resumes_from_given_offset(self):
        client = make_client()
        response = MagicMock()
        response.json.return_value = {"results": [], "hasMore": False, "offset": 999}
        response.raise_for_status.return_value = None

        with patch(
            "app.clients.hubspot_client.requests.get", return_value=response
        ) as mock_get:
            list(client.iter_engagements(after="500"))

        assert mock_get.call_args.kwargs["params"]["offset"] == 500

    def test_request_exception_wrapped_in_hubspot_client_error(self):
        client = make_client()
        with (
            patch(
                "app.clients.hubspot_client.requests.get",
                side_effect=requests.RequestException("timeout"),
            ),
            pytest.raises(HubSpotClientError),
        ):
            list(client.iter_engagements())


class TestPing:
    def test_true_when_cached_auth_is_fresh(self):
        client = make_client()
        client._auth.is_authenticated.return_value = True

        assert client.ping() is True
        client._auth.validate.assert_not_called()

    def test_falls_back_to_validate_when_cache_stale(self):
        client = make_client()
        client._auth.is_authenticated.return_value = False
        client._auth.validate.return_value = True

        assert client.ping() is True
        client._auth.validate.assert_called_once()

    def test_false_when_validate_raises(self):
        client = make_client()
        client._auth.is_authenticated.return_value = False
        client._auth.validate.side_effect = Exception("token invalid")

        assert client.ping() is False


class TestGetPortalInfo:
    def test_returns_json_body(self):
        client = make_client()
        response = MagicMock(status_code=200)
        response.json.return_value = {"portalId": 123}
        response.raise_for_status.return_value = None

        with patch("app.clients.hubspot_client.requests.get", return_value=response):
            result = client.get_portal_info()

        assert result == {"portalId": 123}

    def test_request_exception_wrapped(self):
        client = make_client()
        with (
            patch(
                "app.clients.hubspot_client.requests.get",
                side_effect=requests.RequestException("down"),
            ),
            pytest.raises(HubSpotClientError),
        ):
            client.get_portal_info()


class TestGetApiUsage:
    def test_returns_first_result(self):
        client = make_client()
        response = MagicMock(status_code=200)
        response.json.return_value = {"results": [{"usageLimit": 250000}]}
        response.raise_for_status.return_value = None

        with patch("app.clients.hubspot_client.requests.get", return_value=response):
            result = client.get_api_usage()

        assert result == {"usageLimit": 250000}

    def test_empty_results_raises_hubspot_client_error(self):
        client = make_client()
        response = MagicMock(status_code=200)
        response.json.return_value = {"results": []}
        response.raise_for_status.return_value = None

        with patch("app.clients.hubspot_client.requests.get", return_value=response):
            with pytest.raises(HubSpotClientError):
                client.get_api_usage()
