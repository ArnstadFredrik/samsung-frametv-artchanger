"""Config flow to set up the Samsung Frame TV Art Changer integration."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .config import parse_tv_ips
from .const import (
    CONF_AUTOMATION_TOKEN,
    CONF_MEDIA_DIR,
    CONF_TV_IPS,
    DEFAULT_MEDIA_SUBDIR,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class FrameArtConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Samsung Frame TV Art Changer."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return FrameArtOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        errors: Dict[str, str] = {}

        if user_input is not None:
            tv_ips = parse_tv_ips(user_input.get(CONF_TV_IPS))
            if not tv_ips:
                errors[CONF_TV_IPS] = "invalid_tv_ips"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Samsung Frame TV Art Changer",
                    data={
                        CONF_TV_IPS: ",".join(tv_ips),
                        CONF_AUTOMATION_TOKEN: str(user_input.get(CONF_AUTOMATION_TOKEN) or ""),
                        CONF_MEDIA_DIR: str(user_input.get(CONF_MEDIA_DIR) or ""),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_TV_IPS, default=""): str,
                vol.Optional(CONF_AUTOMATION_TOKEN, default=""): str,
                vol.Optional(CONF_MEDIA_DIR, default=""): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "media_dir_example": f"~/{DEFAULT_MEDIA_SUBDIR} (empty = <config>/{DEFAULT_MEDIA_SUBDIR})",
            },
        )


class FrameArtOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow: edit TV addresses and the automation token."""

    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        if user_input is not None:
            tv_ips = parse_tv_ips(user_input.get(CONF_TV_IPS))
            if not tv_ips:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._build_schema(),
                    errors={CONF_TV_IPS: "invalid_tv_ips"},
                )
            return self.async_create_entry(
                title="",
                data={
                    CONF_TV_IPS: ",".join(tv_ips),
                    CONF_AUTOMATION_TOKEN: str(user_input.get(CONF_AUTOMATION_TOKEN) or ""),
                    CONF_MEDIA_DIR: str(user_input.get(CONF_MEDIA_DIR) or ""),
                },
            )

        return self.async_show_form(step_id="init", data_schema=self._build_schema())

    def _build_schema(self):
        data = self.config_entry.data
        return vol.Schema(
            {
                vol.Required(CONF_TV_IPS, default=data.get(CONF_TV_IPS, "")): str,
                vol.Optional(CONF_AUTOMATION_TOKEN, default=data.get(CONF_AUTOMATION_TOKEN, "")): str,
                vol.Optional(CONF_MEDIA_DIR, default=data.get(CONF_MEDIA_DIR, "")): str,
            }
        )
