"""Support to manage a shopping list."""
import logging
import uuid

import voluptuous as vol

from .bring import BringApi

from homeassistant import config_entries
from homeassistant.components import http, websocket_api
from homeassistant.components.http.data_validator import RequestDataValidator
from homeassistant.const import HTTP_BAD_REQUEST, HTTP_NOT_FOUND
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.util.json import load_json, save_json

from .const import DOMAIN

ATTR_NAME = "name"

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = vol.Schema({DOMAIN: {}}, extra=vol.ALLOW_EXTRA)
EVENT = "shopping_list_updated"
ITEM_UPDATE_SCHEMA = vol.Schema({"complete": bool, ATTR_NAME: str})
PERSISTENCE = ".shopping_list.json"

SERVICE_ADD_ITEM = "add_item"
SERVICE_COMPLETE_ITEM = "complete_item"
SERVICE_SYNC_BRING = "sync_bring"

SERVICE_ITEM_SCHEMA = vol.Schema({vol.Required(ATTR_NAME): vol.Any(None, cv.string)})

WS_TYPE_SHOPPING_LIST_ITEMS = "shopping_list/items"
WS_TYPE_SHOPPING_LIST_ADD_ITEM = "shopping_list/items/add"
WS_TYPE_SHOPPING_LIST_UPDATE_ITEM = "shopping_list/items/update"
WS_TYPE_SHOPPING_LIST_CLEAR_ITEMS = "shopping_list/items/clear"

SCHEMA_WEBSOCKET_ITEMS = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
    {vol.Required("type"): WS_TYPE_SHOPPING_LIST_ITEMS}
)

SCHEMA_WEBSOCKET_ADD_ITEM = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
    {vol.Required("type"): WS_TYPE_SHOPPING_LIST_ADD_ITEM, vol.Required("name"): str}
)

SCHEMA_WEBSOCKET_UPDATE_ITEM = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
    {
        vol.Required("type"): WS_TYPE_SHOPPING_LIST_UPDATE_ITEM,
        vol.Required("item_id"): str,
        vol.Optional("name"): str,
        vol.Optional("complete"): bool,
    }
)

SCHEMA_WEBSOCKET_CLEAR_ITEMS = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
    {vol.Required("type"): WS_TYPE_SHOPPING_LIST_CLEAR_ITEMS}
)


async def async_setup(hass, config):
    """Initialize the shopping list."""

    if DOMAIN not in config:
        return True

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_IMPORT}
        )
    )

    return True


async def async_setup_entry(hass, config_entry):
    """Set up shopping list from config flow."""

    async def add_item_service(call):
        """Add an item with `name`."""
        data = hass.data[DOMAIN]
        name = call.data.get(ATTR_NAME)
        if name is not None:
            await data.async_add(name)

    async def complete_item_service(call):
        """Mark the item provided via `name` as completed."""
        data = hass.data[DOMAIN]
        name = call.data.get(ATTR_NAME)
        if name is None:
            return
        try:
            item = [item for item in data.items if item["name"] == name][0]
        except IndexError:
            _LOGGER.error("Removing of item failed: %s cannot be found", name)
        else:
            await data.async_update(item["id"], {"name": name, "complete": True})

    async def sync_bring_service(call):
        """Sync with Bring List"""
        data = hass.data[DOMAIN]
        data.sync_bring()

    data = hass.data[DOMAIN] = ShoppingData(hass)
    await data.async_load()

    hass.services.async_register(
        DOMAIN, SERVICE_ADD_ITEM, add_item_service, schema=SERVICE_ITEM_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_COMPLETE_ITEM, complete_item_service, schema=SERVICE_ITEM_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SYNC_BRING, sync_bring_service, schema={}
    )

    hass.http.register_view(ShoppingListView)
    hass.http.register_view(CreateShoppingListItemView)
    hass.http.register_view(UpdateShoppingListItemView)
    hass.http.register_view(ClearCompletedItemsView)

    hass.components.frontend.async_register_built_in_panel(
        "shopping-list", "shopping_list", "mdi:cart"
    )

    hass.components.websocket_api.async_register_command(
        WS_TYPE_SHOPPING_LIST_ITEMS, websocket_handle_items, SCHEMA_WEBSOCKET_ITEMS
    )
    hass.components.websocket_api.async_register_command(
        WS_TYPE_SHOPPING_LIST_ADD_ITEM, websocket_handle_add, SCHEMA_WEBSOCKET_ADD_ITEM
    )
    hass.components.websocket_api.async_register_command(
        WS_TYPE_SHOPPING_LIST_UPDATE_ITEM,
        websocket_handle_update,
        SCHEMA_WEBSOCKET_UPDATE_ITEM,
    )
    hass.components.websocket_api.async_register_command(
        WS_TYPE_SHOPPING_LIST_CLEAR_ITEMS,
        websocket_handle_clear,
        SCHEMA_WEBSOCKET_CLEAR_ITEMS,
    )

    return True


class ShoppingData:
    """Class to hold shopping list data."""

    def __init__(self, hass):
        """Initialize the shopping list."""
        self.bring = BringApi(
            "41fdcefe-17ae-4f78-b169-faa17059ac84",
            "3eb85136-62e4-4711-b637-d136f86003f7",
        )
        self.catalog = {v: k for k, v in self.bring.loadTranslations("fr-FR").items()}
        self.hass = hass
        self.items = []

    async def async_add(self, name):
        """Add a shopping list item."""
        item = {"name": name, "id": uuid.uuid4().hex, "complete": False}
        self.items.append(item)
        if self.catalog.get(item["name"]):
            itm_name = self.catalog.get(item["name"])
        else:
            itm_name = item["name"]
        self.bring.purchase_item(itm_name, "")
        await self.hass.async_add_executor_job(self.save)
        return item

    async def async_update(self, item_id, info):
        """Update a shopping list item."""
        item = next((itm for itm in self.items if itm["id"] == item_id), None)

        if item is None:
            raise KeyError

        info = ITEM_UPDATE_SCHEMA(info)
        item.update(info)
        if self.catalog.get(item["name"]):
            itm_name = self.catalog.get(item["name"])
        else:
            itm_name = item["name"]
        if item["complete"]:
            self.bring.recent_item(itm_name)
        else:
            self.bring.purchase_item(itm_name, "")
        await self.hass.async_add_executor_job(self.save)
        return item

    async def async_clear_completed(self):
        """Clear completed items."""
        for itm in [itm for itm in self.items if itm["complete"]]:
            if self.catalog.get(itm["name"]):
                itm_name = self.catalog.get(itm["name"])
            else:
                itm_name = itm["name"]
            self.bring.remove_item(itm_name)
        self.items = [itm for itm in self.items if not itm["complete"]]
        await self.hass.async_add_executor_job(self.save)

    def sync_bring(self):
        purchase = self.bring.get_items("fr-FR")["purchase"]
        for bitm in purchase:
            item = {"name": bitm["name"], "id": bitm["name"], "complete": False}
            if item not in self.items:
                self.items.append(item)
        recently = self.bring.get_items("fr-FR")["recently"]
        for bitm in recently:
            item = {"name": bitm["name"], "id": bitm["name"], "complete": False}
            if item in self.items:
                self.items[self.items.index(item)]["complete"] = True
        for itm in self.items:
            if self.catalog.get(itm["name"]):
                itm_name = self.catalog.get(itm["name"])
            else:
                itm_name = itm["name"]
            if itm["complete"]:
                if {"name": itm_name, "specification": ""} not in recently:
                    self.bring.recent_item(itm_name)
            else:
                if {"name": itm_name, "specification": ""} not in purchase:
                    self.bring.purchase_item(itm_name, "")

    async def async_load(self):
        """Load items."""

        def load():
            """Load the items synchronously."""
            return load_json(self.hass.config.path(PERSISTENCE), default=[])

        self.items = await self.hass.async_add_executor_job(load)
        self.sync_bring()

    def save(self):
        """Save the items."""
        self.sync_bring()
        save_json(self.hass.config.path(PERSISTENCE), self.items)


class ShoppingListView(http.HomeAssistantView):
    """View to retrieve shopping list content."""

    url = "/api/shopping_list"
    name = "api:shopping_list"

    @callback
    def get(self, request):
        """Retrieve shopping list items."""
        return self.json(request.app["hass"].data[DOMAIN].items)


class UpdateShoppingListItemView(http.HomeAssistantView):
    """View to retrieve shopping list content."""

    url = "/api/shopping_list/item/{item_id}"
    name = "api:shopping_list:item:id"

    async def post(self, request, item_id):
        """Update a shopping list item."""
        data = await request.json()

        try:
            item = await request.app["hass"].data[DOMAIN].async_update(item_id, data)
            request.app["hass"].bus.async_fire(EVENT)
            return self.json(item)
        except KeyError:
            return self.json_message("Item not found", HTTP_NOT_FOUND)
        except vol.Invalid:
            return self.json_message("Item not found", HTTP_BAD_REQUEST)


class CreateShoppingListItemView(http.HomeAssistantView):
    """View to retrieve shopping list content."""

    url = "/api/shopping_list/item"
    name = "api:shopping_list:item"

    @RequestDataValidator(vol.Schema({vol.Required("name"): str}))
    async def post(self, request, data):
        """Create a new shopping list item."""
        item = await request.app["hass"].data[DOMAIN].async_add(data["name"])
        request.app["hass"].bus.async_fire(EVENT)
        return self.json(item)


class ClearCompletedItemsView(http.HomeAssistantView):
    """View to retrieve shopping list content."""

    url = "/api/shopping_list/clear_completed"
    name = "api:shopping_list:clear_completed"

    async def post(self, request):
        """Retrieve if API is running."""
        hass = request.app["hass"]
        await hass.data[DOMAIN].async_clear_completed()
        hass.bus.async_fire(EVENT)
        return self.json_message("Cleared completed items.")


@callback
def websocket_handle_items(hass, connection, msg):
    """Handle get shopping_list items."""
    connection.send_message(
        websocket_api.result_message(msg["id"], hass.data[DOMAIN].items)
    )


@websocket_api.async_response
async def websocket_handle_add(hass, connection, msg):
    """Handle add item to shopping_list."""
    item = await hass.data[DOMAIN].async_add(msg["name"])
    hass.bus.async_fire(EVENT, {"action": "add", "item": item})
    connection.send_message(websocket_api.result_message(msg["id"], item))


@websocket_api.async_response
async def websocket_handle_update(hass, connection, msg):
    """Handle update shopping_list item."""
    msg_id = msg.pop("id")
    item_id = msg.pop("item_id")
    msg.pop("type")
    data = msg

    try:
        item = await hass.data[DOMAIN].async_update(item_id, data)
        hass.bus.async_fire(EVENT, {"action": "update", "item": item})
        connection.send_message(websocket_api.result_message(msg_id, item))
    except KeyError:
        connection.send_message(
            websocket_api.error_message(msg_id, "item_not_found", "Item not found")
        )


@websocket_api.async_response
async def websocket_handle_clear(hass, connection, msg):
    """Handle clearing shopping_list items."""
    await hass.data[DOMAIN].async_clear_completed()
    hass.bus.async_fire(EVENT, {"action": "clear"})
    connection.send_message(websocket_api.result_message(msg["id"]))
