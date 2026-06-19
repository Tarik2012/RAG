import json
from unittest.mock import patch

import pytest
from django.urls import reverse


pytestmark = pytest.mark.django_db


def test_agent_view_returns_500_on_server_error(client, user):
    url = reverse("documents:agent")

    client.force_login(user)

    with patch("documents.views._build_agent_service", side_effect=Exception("boom")):
        response = client.post(
            url,
            data=json.dumps({"question": "hola"}),
            content_type="application/json",
        )

    assert response.status_code == 500
    assert "error" in response.json()
