"""Config flow to configure ShoppingList component."""
import logging

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
import voluptuous as vol

from .bring import BringApi
from .const import DOMAIN  # pylint: disable=unused-import

_LOGGER = logging.getLogger(__name__)

CONF_LOCALE = "locale"
CONF_LIST_NAME = "list_name"

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_LOCALE, default="en-EN"): str,
    }
)


class ShoppingListFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for ShoppingList component."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self) -> None:
        self._username = None
        self._password = None
        self._locale = None
        self._list_name = None

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
            return True

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        # Check if already configured
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input.get(CONF_USERNAME))
            self._abort_if_unique_id_configured()
            if await self.async_validate_input(user_input):
                self._username = user_input.get(CONF_USERNAME)
                self._password = user_input.get(CONF_PASSWORD)
                self._locale = user_input.get(CONF_LOCALE)
                return await self.async_step_list()

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_list(self, user_input=None):
        """Handle the second step"""
        errors = {}

        if user_input is not None:
            self._list_name = user_input.get(CONF_LIST_NAME)
            return self.async_create_entry(
                title="Shopping List",
                data={
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_LOCALE: self._locale,
                    CONF_LIST_NAME: self._list_name,
                },
            )

        lists = []
        async with BringApi(self._username, self._password) as client:
            await client.login()
            await client.get_lists()
            lists = [_list.get("name") for _list in client.lists]

        return self.async_show_form(
            step_id="list",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LIST_NAME, default=lists[0]): vol.In(lists),
                }
            ),
            errors=errors,
        )

    async_step_import = async_step_user


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for TaHoma."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

        if self.options.get(CONF_LOCALE) is None:
            self.options[CONF_LOCALE] = self.config_entry.data[CONF_LOCALE]

        if self.options.get(CONF_LIST_NAME) is None:
            self.options[CONF_LIST_NAME] = self.config_entry.data[CONF_LIST_NAME]

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
