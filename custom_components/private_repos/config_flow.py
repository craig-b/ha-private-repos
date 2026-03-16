"""Config flow for Private Repos integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    ACCOUNT_TYPE_ORG,
    ACCOUNT_TYPE_USER,
    CONF_ACCOUNT_TYPE,
    CONF_GITHUB_PAT,
    CONF_GITHUB_USER,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .github_api import GitHubAPI, GitHubAuthError, GitHubAPIError


USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCOUNT_TYPE, default=ACCOUNT_TYPE_ORG): vol.In(
            {ACCOUNT_TYPE_ORG: "Organization", ACCOUNT_TYPE_USER: "User"}
        ),
        vol.Required(CONF_GITHUB_USER): str,
        vol.Required(CONF_GITHUB_PAT): str,
    }
)

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_GITHUB_PAT): str,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=30, max=1440)
        ),
    }
)


class PrivateReposConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Private Repos."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            unique_id = f"{user_input[CONF_ACCOUNT_TYPE]}/{user_input[CONF_GITHUB_USER]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            error = await self._validate_credentials(
                user_input[CONF_GITHUB_USER],
                user_input[CONF_GITHUB_PAT],
                user_input[CONF_ACCOUNT_TYPE],
            )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=user_input[CONF_GITHUB_USER],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth trigger."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth confirmation."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            error = await self._validate_credentials(
                reauth_entry.data[CONF_GITHUB_USER],
                user_input[CONF_GITHUB_PAT],
                reauth_entry.data[CONF_ACCOUNT_TYPE],
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_GITHUB_PAT: user_input[CONF_GITHUB_PAT]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={
                "github_user": reauth_entry.data[CONF_GITHUB_USER],
            },
        )

    async def _validate_credentials(
        self, github_user: str, pat: str, account_type: str
    ) -> str | None:
        """Validate GitHub credentials. Returns error key or None."""
        session = async_get_clientsession(self.hass)
        api = GitHubAPI(session, github_user, pat, account_type)
        try:
            await api.list_repos(page=1)
        except GitHubAuthError:
            return "invalid_auth"
        except GitHubAPIError:
            return "cannot_connect"
        except Exception:  # noqa: BLE001
            return "unknown"
        return None

    @staticmethod
    def async_get_options_flow(
        config_entry,
    ) -> PrivateReposOptionsFlow:
        """Create the options flow."""
        return PrivateReposOptionsFlow()


class PrivateReposOptionsFlow(OptionsFlowWithReload):
    """Handle options flow for Private Repos."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
