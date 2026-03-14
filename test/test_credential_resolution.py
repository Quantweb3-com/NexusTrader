"""Tests for multi-source credential resolution in BasicConfig (v0.3.6)."""

import warnings


class TestBasicConfigDirect:
    """Direct pass — highest priority, backward-compatible."""

    def test_direct_pass(self):
        from nexustrader.config import BasicConfig

        cfg = BasicConfig(api_key="ak", secret="sk", testnet=True)
        assert cfg.api_key == "ak"
        assert cfg.secret == "sk"
        assert cfg.testnet is True
        assert cfg.passphrase is None

    def test_direct_pass_with_passphrase(self):
        from nexustrader.config import BasicConfig

        cfg = BasicConfig(api_key="ak", secret="sk", passphrase="pp")
        assert cfg.passphrase == "pp"

    def test_no_credentials(self):
        from nexustrader.config import BasicConfig

        cfg = BasicConfig(testnet=True)
        assert cfg.api_key is None
        assert cfg.secret is None
        assert cfg.passphrase is None


class TestBasicConfigFromEnv:
    """from_env() — reads plain environment variables."""

    def test_from_env_basic(self, monkeypatch):
        from nexustrader.config import BasicConfig

        monkeypatch.setenv("MYEX_API_KEY", "env_ak")
        monkeypatch.setenv("MYEX_SECRET", "env_sk")

        cfg = BasicConfig.from_env("MYEX", testnet=True)
        assert cfg.api_key == "env_ak"
        assert cfg.secret == "env_sk"
        assert cfg.testnet is True
        assert cfg.passphrase is None

    def test_from_env_with_passphrase(self, monkeypatch):
        from nexustrader.config import BasicConfig

        monkeypatch.setenv("OKX_DEMO_API_KEY", "ak")
        monkeypatch.setenv("OKX_DEMO_SECRET", "sk")
        monkeypatch.setenv("OKX_DEMO_PASSPHRASE", "pp")

        cfg = BasicConfig.from_env("OKX_DEMO")
        assert cfg.api_key == "ak"
        assert cfg.secret == "sk"
        assert cfg.passphrase == "pp"

    def test_from_env_missing_vars(self):
        from nexustrader.config import BasicConfig

        cfg = BasicConfig.from_env("NONEXISTENT_EXCHANGE_XYZ")
        assert cfg.api_key is None
        assert cfg.secret is None
        assert cfg.passphrase is None

    def test_from_env_custom_var_names(self, monkeypatch):
        from nexustrader.config import BasicConfig

        monkeypatch.setenv("MY_CUSTOM_KEY", "ck")
        monkeypatch.setenv("MY_CUSTOM_SEC", "cs")

        cfg = BasicConfig.from_env(
            "X",
            api_key_var="MY_CUSTOM_KEY",
            secret_var="MY_CUSTOM_SEC",
            testnet=True,
        )
        assert cfg.api_key == "ck"
        assert cfg.secret == "cs"

    def test_from_env_case_insensitive_prefix(self, monkeypatch):
        from nexustrader.config import BasicConfig

        monkeypatch.setenv("BINANCE_API_KEY", "ak")
        monkeypatch.setenv("BINANCE_SECRET", "sk")

        cfg = BasicConfig.from_env("binance")
        assert cfg.api_key == "ak"
        assert cfg.secret == "sk"


class TestBasicConfigSettingsKey:
    """settings_key — auto-resolve from Dynaconf settings."""

    def test_settings_key_resolves(self, monkeypatch):
        from nexustrader.config import BasicConfig

        monkeypatch.setenv("NEXUS_TESTEXCH__DEMO__API_KEY", "resolved_ak")
        monkeypatch.setenv("NEXUS_TESTEXCH__DEMO__SECRET", "resolved_sk")

        from nexustrader.constants import settings
        settings.reload()

        cfg = BasicConfig(settings_key="TESTEXCH.DEMO", testnet=True)
        assert cfg.api_key == "resolved_ak"
        assert cfg.secret == "resolved_sk"
        assert cfg.testnet is True

    def test_settings_key_with_passphrase(self, monkeypatch):
        from nexustrader.config import BasicConfig

        monkeypatch.setenv("NEXUS_TESTEXCH2__LIVE__API_KEY", "ak2")
        monkeypatch.setenv("NEXUS_TESTEXCH2__LIVE__SECRET", "sk2")
        monkeypatch.setenv("NEXUS_TESTEXCH2__LIVE__PASSPHRASE", "pp2")

        from nexustrader.constants import settings
        settings.reload()

        cfg = BasicConfig(settings_key="TESTEXCH2.LIVE")
        assert cfg.api_key == "ak2"
        assert cfg.secret == "sk2"
        assert cfg.passphrase == "pp2"

    def test_settings_key_direct_overrides(self, monkeypatch):
        """Directly passed values take precedence over settings_key resolution."""
        from nexustrader.config import BasicConfig

        monkeypatch.setenv("NEXUS_TESTEXCH3__X__API_KEY", "settings_ak")
        monkeypatch.setenv("NEXUS_TESTEXCH3__X__SECRET", "settings_sk")

        from nexustrader.constants import settings
        settings.reload()

        cfg = BasicConfig(
            api_key="direct_ak",
            settings_key="TESTEXCH3.X",
        )
        assert cfg.api_key == "direct_ak"
        assert cfg.secret == "settings_sk"

    def test_settings_key_invalid_warns(self):
        from nexustrader.config import BasicConfig

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = BasicConfig(settings_key="NONEXISTENT.PATH.HERE")
            assert len(w) == 1
            assert "Could not resolve credentials" in str(w[0].message)
            assert cfg.api_key is None
            assert cfg.secret is None


class TestConstantsLazyValidation:
    """constants.py no longer raises FileNotFoundError at import time."""

    def test_settings_importable(self):
        from nexustrader.constants import settings
        assert settings is not None

    def test_settings_supports_get(self):
        from nexustrader.constants import settings
        val = settings.get("NONEXISTENT_KEY_12345", "default")
        assert val == "default"
