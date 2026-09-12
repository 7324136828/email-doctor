from app.services.mailbox_download import provider_for_email, resolve_imap, since_date_str


def test_known_provider_mapping():
    assert resolve_imap("person@live.cn") == ("outlook.office365.com", 993)
    assert resolve_imap("person@foxmail.com") == ("imap.qq.com", 993)
    assert resolve_imap("person@pm.me") == ("127.0.0.1", 1143)
    assert provider_for_email("person@yahoo.com") == "credentials"


def test_unknown_domain_defaults_to_imap_subdomain():
    assert resolve_imap("person@example.org") == ("imap.example.org", 993)
    assert len(since_date_str(7).split("-")) == 3
