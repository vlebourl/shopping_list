"""Config flow to configure ShoppingList component."""
import logging

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
import voluptuous as vol

from .bring import BringApi
from .const import DOMAIN  # pylint: disable=unused-import

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
)

CONF_LOCALE = "locale"
CONF_LIST_NAME = "list_name"


class ShoppingListFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for ShoppingList component."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Handle the flow."""
        return OptionsFlowHandler(config_entry)

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


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for TaHoma."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

        if self.options.get(CONF_LOCALE) is None:
            self.options[CONF_LOCALE] = "en-EN"

        if self.options.get(CONF_LIST_NAME) is None:
            self.options[CONF_LIST_NAME] = ""

    async def async_step_init(self, user_input=None):
        """Manage the Bring options."""
        return await self.async_step_locale_and_list()

    async def async_step_locale_and_list(self, user_input=None):
        """Manage the options regarding interval updates."""
        if user_input is not None:
            self.options[CONF_LOCALE] = user_input[CONF_LOCALE]
            self.options[CONF_LIST_NAME] = user_input[CONF_LIST_NAME]
            return self.async_create_entry(title="", data=self.options)

        username = self.config_entry.data.get("username")
        password = self.config_entry.data.get("password")
        lists = []
        async with BringApi(username, password) as client:
            await client.login()
            await client.get_lists()
            lists = [_list.get("name") for _list in client.lists]

        return self.async_show_form(
            step_id="locale_and_list",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_LOCALE, default=self.options.get(CONF_LOCALE)
                    ): str,
                    vol.Optional(CONF_LIST_NAME, default=lists[0]): vol.In(lists),
                }
            ),
        )
