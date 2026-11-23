from unittest.mock import ANY, MagicMock, patch

from certbot_dns_yandex360.authenticator import Yandex360DNSAuthenticator


def test_setup_credentials_creates_helper():
    auth = object.__new__(Yandex360DNSAuthenticator)

    mock_credentials = MagicMock()
    mock_credentials.conf.side_effect = lambda key: {
        "oauth_token": "dummy_token",
        "org_id": "42",
    }[key]

    with (
        patch.object(auth, "_configure_credentials", return_value=mock_credentials) as mock_configure,
        patch(
            "certbot_dns_yandex360.authenticator.Yandex360Helper",
            autospec=True,
        ) as mock_helper,
    ):
        auth._setup_credentials()

        mock_configure.assert_called_once_with(
            "credentials",
            ANY,
            {
                "oauth_token": "Yandex OAuth token with directory:manage_dns",
                "org_id": "Yandex 360 organization ID",
            },
        )
        mock_helper.assert_called_once_with(oauth_token="dummy_token", org_id="42")
        assert auth.yandex360_helper is mock_helper.return_value
