"""Config flow to configure ShoppingList component."""
import logging

from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from .bring import BringApi
import voluptuous as vol

from .const import DOMAIN  # pylint: disable=unused-import

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
)


class ShoppingListFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for ShoppingList component."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_validate_input(self, user_input):
        """Validate user credentials."""
        username = user_input.get(CONF_USERNAME)
        password = user_input.get(CONF_PASSWORD)

        async with BringApi(username, password) as client:
            await client.login()
            return self.async_create_entry(title="Shopping List", data=user_input)

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        # Check if already configured
        errors = {}
        
        if user_input is not None:
            await self.async_set_unique_id(user_input.get(CONF_USERNAME))
            self._abort_if_unique_id_configured()
            return await self.async_validate_input(user_input)

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async_step_import = async_step_user
