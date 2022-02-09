"""Support to manage a shopping list."""
from http import HTTPStatus
import logging

from homeassistant import config_entries
from homeassistant.components import http, websocket_api
from homeassistant.components.http.data_validator import RequestDataValidator
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME
)
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client
import homeassistant.helpers.config_validation as cv
from homeassistant.util.json import load_json, save_json
import voluptuous as vol

from .bring import BringApi
from .const import DOMAIN

ATTR_NAME = "name"

CONF_LOCALE = "locale"
CONF_LIST_NAME = "list_name"

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = vol.Schema({DOMAIN: {}}, extra=vol.ALLOW_EXTRA)

EVENT = "shopping_list_updated"
ITEM_UPDATE_SCHEMA = vol.Schema({"complete": bool, ATTR_NAME: str})
PERSISTENCE = ".shopping_list.json"

SERVICE_ADD_ITEM = "add_item"
SERVICE_COMPLETE_ITEM = "complete_item"
SERVICE_BRING_SYNC = "bring_sync"
SERVICE_BRING_SELECT_LIST = "bring_select_list"
SERVICE_REMOVE_COMPLETED_ITEMS = "remove_completed_items"

SERVICE_ITEM_SCHEMA = vol.Schema({vol.Required(ATTR_NAME): vol.Any(None, cv.string)})
SERVICE_BRING_SELECT_LIST_SCHEMA = vol.Schema({vol.Required(ATTR_NAME): str})

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


async def async_options_updated(hass, entry):
    """Triggered by config entry options updates."""
    locale = entry.options[CONF_LOCALE]
    list_name = entry.options[CONF_LIST_NAME]
    data = hass.data[DOMAIN]
    if data.bring.language != locale:
        bring_data = BringData(
            entry.data.get("username"),
            entry.data.get("password"),
            locale,
            data.bring.api.session,
        )
        await bring_data.api.login()
        await bring_data.load_catalog()
        data.bring = bring_data
    await data.switch_list(list_name)


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

    async def bring_sync_service(call):
        """Sync with Bring List"""
        await hass.data[DOMAIN].sync_bring()

    async def bring_select_list_service(call):
        """Select which Bring List HA should synchronize with"""
        data = hass.data[DOMAIN]
        name = call.data.get(ATTR_NAME)

        await data.switch_list(name)

    async def remove_completed_items_service(call):
        """Remove completed Items"""
        await hass.data[DOMAIN].async_clear_completed()

    config_entry.add_update_listener(async_options_updated)

    username = config_entry.data.get(CONF_USERNAME)
    password = config_entry.data.get(CONF_PASSWORD)
    language = config_entry.data.get(CONF_LOCALE)
    list_name = config_entry.options.get(CONF_LIST_NAME)

    session = aiohttp_client.async_create_clientsession(hass)
    bring_data = BringData(username, password, language, session)
    await bring_data.api.login()
    await bring_data.load_catalog()

    data = hass.data[DOMAIN] = ShoppingData(
        hass, username, password, language, bring_data
    )
    await data.async_load()
    if list_name:
        await data.switch_list(list_name)

    hass.services.async_register(
        DOMAIN, SERVICE_ADD_ITEM, add_item_service, schema=SERVICE_ITEM_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_COMPLETE_ITEM, complete_item_service, schema=SERVICE_ITEM_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_BRING_SYNC, bring_sync_service, schema={}
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_BRING_SELECT_LIST,
        bring_select_list_service,
        schema=SERVICE_BRING_SELECT_LIST_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_COMPLETED_ITEMS,
        remove_completed_items_service,
        schema={},
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


class ShoppingItem:
    """Class to hold a Shopping List item."""

    def __init__(self, item):
        self.name = item["name"]
        self.id = item["id"]
        self.specification = item["specification"]
        self.complete = item["complete"]

    def __str__(self):
        return str(vars(self))

    def __repr__(self) -> str:
        return str(self)

    def to_ha(self):
        specification = ""
        if len(self.specification) > 0:
            specification = f" [{self.specification}]"
        return {
            "name": self.name + specification,
            "id": self.id,
            "complete": self.complete,
        }

    def to_bring(self):
        return {"name": self.name, "specification": self.specification}


class BringData:
    """Class to hold a Bring shopping list data."""

    def __init__(self, username, password, language, session) -> None:
        self.api = BringApi(username, password, session)
        self.language = language
        self.catalog = {}
        self.purchase_list = []
        self.recent_list = []

    @staticmethod
    def bring_to_shopping(bitm, item_map, complete):
        name = bitm["name"]
        for key, itm in item_map.items():
            if bitm["name"] == itm.name and bitm["specification"] == itm.specification:
                name = key
                break
        return ShoppingItem(
            {
                "name": bitm["name"],
                "id": name,
                "specification": bitm["specification"],
                "complete": complete,
            }
        )

    async def load_catalog(self):
        catalog = await self.api.load_translations(self.language)
        self.catalog = {v: k for k, v in catalog.items()}

    async def update_lists(self, map):
        lists = await self.api.get_items(self.language)
        self.purchase_list = [
            self.bring_to_shopping(itm, map, False) for itm in lists["purchase"]
        ]
        self.recent_list = [
            self.bring_to_shopping(itm, map, True) for itm in lists["recently"]
        ]

    def convert_name(self, name):
        if self.catalog.get(name):
            return self.catalog.get(name)
        return name

    async def purchase_item(self, item: ShoppingItem):
        await self.api.purchase_item(self.convert_name(item.name), item.specification)

    async def recent_item(self, item: ShoppingItem):
        await self.api.recent_item(self.convert_name(item.name))

    async def remove_item(self, item: ShoppingItem):
        await self.api.remove_item(self.convert_name(item.name))


class ShoppingData:
    """Class to hold shopping list data."""

    def __init__(self, hass, username, password, language, bring_data):
        """Initialize the shopping list."""
        self.bring = bring_data
        self.hass = hass
        self.map_items = {}
        self.items = []

    @staticmethod
    def ha_to_shopping_item(item):
        name = item["name"]
        id = item["id"]
        complete = item["complete"]
        specification = ""
        if " [" in name:
            specification = name[name.index(" [") + 2 : len(name) - 1]
            name = name[0 : name.index(" [")]
        return ShoppingItem(
            {
                "name": name,
                "id": id,
                "specification": specification,
                "complete": complete,
            }
        )

    @staticmethod
    def remove(list, item):
        try:
            list.remove(item)
        except ValueError:
            pass

    def find_item(self, id):
        return next((i for i, item in enumerate(self.items) if item["id"] == id), None)

    def update_item(self, id, item):
        i = self.find_item(id)
        self.items[i] = item.to_ha()
        self.items = [
            i for n, i in enumerate(self.items) if i not in self.items[n + 1 :]
        ]

    async def async_add(self, name):
        """Add a shopping list item."""
        specification = ""
        if " [" in name:
            specification = name[name.index(" [") + 2 : len(name) - 1]
            name = name[0 : name.index(" [")]
        item = ShoppingItem(
            {
                "name": name,
                "id": f"{name}",
                "specification": specification,
                "complete": False,
            }
        )
        self.items.append(item.to_ha())
        await self.bring.purchase_item(item)
        self.map_items[item.id] = item
        await self.sync_bring()
        await self.hass.async_add_executor_job(self.save)
        return item.to_ha()

    async def async_update(self, item_id, info):
        """Update a shopping list item."""
        item = self.map_items.get(item_id)
        if item is None:
            raise KeyError
        info = ITEM_UPDATE_SCHEMA(info)
        key = list(info.keys())[0]
        value = info[key]

        if key == "complete":
            item.complete = value
        elif key == "name":
            name = value
            specification = ""
            if " [" in name:
                specification = name[name.index(" [") + 2 : len(name) - 1]
                name = name[0 : name.index(" [")]
            await self.bring.remove_item(item)
            item.name = name
            item.specification = specification
            item.id = name
            self.map_items.pop(item_id)
            self.map_items[item.name] = item

        if item.complete:
            await self.bring.recent_item(item)
        else:
            await self.bring.purchase_item(item)
        self.update_item(item_id, item)
        await self.sync_bring()
        await self.hass.async_add_executor_job(self.save)
        return item.to_ha()

    async def async_clear_completed(self):
        """Clear completed items."""
        to_remove = []
        for key, itm in self.map_items.items():
            if itm.complete:
                await self.bring.remove_item(itm)
                self.remove(self.bring.recent_list, itm)
                self.remove(self.items, itm.to_ha())
                to_remove.append(key)
        for key in to_remove:
            self.map_items.pop(key)
        await self.sync_bring()
        await self.hass.async_add_executor_job(self.save)

    async def switch_list(self, list_name):
        self.map_items = {}
        await self.bring.api.select_list(list_name)
        await self.sync_bring()

    async def sync_bring(self):
        await self.bring.update_lists(self.map_items)

        for itm in self.bring.purchase_list + self.bring.recent_list:
            self.map_items[itm.id] = itm

        self.items = [itm.to_ha() for k, itm in self.map_items.items()]

    async def async_load(self):
        """Load items."""

        def load():
            """Load the items synchronously."""
            return load_json(self.hass.config.path(PERSISTENCE), default=[])

        self.items = await self.hass.async_add_executor_job(load)
        for itm in self.items:
            self.map_items[itm["id"]] = self.ha_to_shopping_item(itm)
        await self.sync_bring()

    def save(self):
        """Save the items."""
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
            return self.json_message("Item not found", HTTPStatus.NOT_FOUND)
        except vol.Invalid:
            return self.json_message("Item not found", HTTPStatus.BAD_REQUEST)


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
