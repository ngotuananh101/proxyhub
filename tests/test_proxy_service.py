
from app.models.proxy import Proxy, ProxyStatus
from app.services.proxy_service import import_proxies, parse_proxy_line, select_random_proxy


class TestParseProxyLine:
    def test_http_with_auth(self):
        result = parse_proxy_line("http://user:pass@1.2.3.4:8080")
        assert result == {
            "scheme": "http",
            "host": "1.2.3.4",
            "port": 8080,
            "username": "user",
            "password": "pass",
        }

    def test_http_without_auth(self):
        result = parse_proxy_line("http://5.6.7.8:3128")
        assert result == {
            "scheme": "http",
            "host": "5.6.7.8",
            "port": 3128,
            "username": None,
            "password": None,
        }

    def test_https(self):
        result = parse_proxy_line("https://10.0.0.1:443")
        assert result["scheme"] == "https"

    def test_socks5_parsed_but_not_gateway_supported(self):
        result = parse_proxy_line("socks5://1.2.3.4:1080")
        assert result["scheme"] == "socks5"

    def test_invalid_scheme(self):
        assert parse_proxy_line("ftp://1.2.3.4:21") is None

    def test_missing_port(self):
        assert parse_proxy_line("http://1.2.3.4") is None

    def test_empty_line(self):
        assert parse_proxy_line("") is None
        assert parse_proxy_line("   ") is None

    def test_garbage(self):
        assert parse_proxy_line("not a url at all") is None


class TestImportProxies:
    def test_import_multiple(self, session):
        text = "http://1.1.1.1:80\nhttp://2.2.2.2:80\nhttp://3.3.3.3:80"
        result = import_proxies(session, text)
        assert result.imported == 3
        assert result.duplicates == 0
        assert len(result.invalid) == 0

    def test_import_with_duplicates(self, session):
        text = "http://1.1.1.1:80\nhttp://1.1.1.1:80"
        result = import_proxies(session, text)
        assert result.imported == 1
        assert result.duplicates == 1

    def test_import_with_invalid_lines(self, session):
        text = "http://1.1.1.1:80\ngarbage\nhttp://2.2.2.2:80"
        result = import_proxies(session, text)
        assert result.imported == 2
        assert len(result.invalid) == 1
        assert result.invalid[0].line == "garbage"


class TestSelectRandomProxy:
    def test_select_excludes_dead(self, session):
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.DEAD))
        session.add(Proxy(scheme="http", host="2.2.2.2", port=80, status=ProxyStatus.ALIVE))
        session.commit()
        proxy = select_random_proxy(session)
        assert proxy is not None
        assert proxy.host == "2.2.2.2"

    def test_select_excludes_unknown(self, session):
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.UNKNOWN))
        session.commit()
        proxy = select_random_proxy(session)
        assert proxy is None

    def test_select_excludes_socks5(self, session):
        session.add(Proxy(scheme="socks5", host="1.1.1.1", port=1080, status=ProxyStatus.ALIVE))
        session.commit()
        proxy = select_random_proxy(session)
        assert proxy is None

    def test_select_empty_pool(self, session):
        assert select_random_proxy(session) is None

    def test_select_with_tenant_id_filter(self, session):
        # tenant 1 proxies
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.ALIVE, tenant_id=1))
        # tenant 2 proxies
        session.add(Proxy(scheme="http", host="2.2.2.2", port=80, status=ProxyStatus.ALIVE, tenant_id=2))
        session.add(Proxy(scheme="http", host="3.3.3.3", port=80, status=ProxyStatus.ALIVE, tenant_id=2))
        # unscoped proxy (tenant_id=None)
        session.add(Proxy(scheme="http", host="4.4.4.4", port=80, status=ProxyStatus.ALIVE))
        session.commit()

        # Without tenant_id, all alive proxies are eligible
        proxy = select_random_proxy(session)
        assert proxy is not None
        assert proxy.tenant_id in (1, 2, None)

        # With tenant_id=1, only 1.1.1.1 is eligible
        proxy = select_random_proxy(session, tenant_id=1)
        assert proxy is not None
        assert proxy.host == "1.1.1.1"

        # With tenant_id=2, only 2.2.2.2 or 3.3.3.3 are eligible
        proxy = select_random_proxy(session, tenant_id=2)
        assert proxy is not None
        assert proxy.host in ("2.2.2.2", "3.3.3.3")

    def test_select_with_tenant_id_no_matches(self, session):
        # No proxies for tenant 999
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.ALIVE, tenant_id=1))
        session.commit()

        assert select_random_proxy(session, tenant_id=999) is None
